"""Stage-3 verification: recompute every Application Reference number
independently from live Grist REST and compare with the Metabase cards.
Tolerance 0.1. Appends to verification-report.md.

Usage: python3 scripts/verify_application_ref.py
"""
import datetime
import os
from collections import defaultdict

from mb import Metabase, REPO_ROOT
from verify_daily_ops import grist_records, num, compare, TOL


def months_ago(epoch):
    d = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now.year * 12 + now.month) - (d.year * 12 + d.month)


def build_expected():
    flights = grist_records("Flights")
    aircraft = {a_id: f for a_id, f in
                ((rec["id"], rec["fields"]) for rec in _raw("Aircraft"))}

    def s(field, pred=lambda f: True):
        return round(sum(num(f.get(field)) for f in flights if pred(f)), 1)

    airplane = lambda f: f.get("Category_from_Aircraft") == "Airplane"
    heli = lambda f: f.get("Category_from_Aircraft") == "Helicopter"
    plift = lambda f: f.get("Category_from_Aircraft") == "Powered Lift"
    rotor = lambda f: f.get("Class_from_Aircraft") == "Rotorcraft"
    fw_turb = lambda f: airplane(f) and f.get("Engine_Category_from_Aircraft") == "Turbine"

    exp = {}
    exp["App: Total Time"] = s("Block_Time")
    exp["App: Total PIC"] = s("PIC_Time")
    exp["App: Airplane"] = s("Block_Time", airplane)
    exp["App: Rotorcraft"] = s("Block_Time", rotor)
    exp["App: Fixed-Wing Turbine"] = s("Block_Time", fw_turb)
    exp["App: Fixed-Wing Turbine PIC"] = s("PIC_Time", fw_turb)
    exp["App: Turbine (All Categories)"] = s(
        "Block_Time", lambda f: f.get("Engine_Category_from_Aircraft") == "Turbine")

    # Totals by Aircraft (keyed by aircraft name)
    per = defaultdict(lambda: defaultdict(float))
    last = {}
    for f in flights:
        ref = f.get("Aircraft")
        name = aircraft.get(ref, {}).get("Aircraft", "?")
        for fld in ["Block_Time", "PIC_Time", "SIC_Time", "Dual_Given",
                    "Dual_Received", "Night_Time", "Instrument_Time",
                    "Cross_Country_Time", "Total_Landing"]:
            per[name][fld] += num(f.get(fld))
        if f.get("Flight_Date"):
            last[name] = max(last.get(name, 0), f["Flight_Date"])
    exp["Totals by Aircraft"] = {
        name: (aircraft_attr(aircraft, name, "Category"),
               aircraft_attr(aircraft, name, "Class"),
               aircraft_attr(aircraft, name, "Engine_Category"),
               round(v["Block_Time"], 1), round(v["PIC_Time"], 1),
               round(v["SIC_Time"], 1), round(v["Dual_Given"], 1),
               round(v["Dual_Received"], 1), round(v["Night_Time"], 1),
               round(v["Instrument_Time"], 1), round(v["Cross_Country_Time"], 1),
               int(v["Total_Landing"]),
               datetime.datetime.fromtimestamp(
                   last[name], datetime.timezone.utc).strftime("%Y-%m-%d"))
        for name, v in per.items()}

    # FAA 8710 matrix (keyed by metric label)
    metrics = [
        ("Total Hours", "Block_Time", None),
        ("Instruction Received", "Dual_Received", None),
        ("Pilot in Command (PIC)", "PIC_Time", None),
        ("Second in Command (SIC)", "SIC_Time", None),
        ("Instructor (Dual Given)", "Dual_Given", None),
        ("Cross Country", "Cross_Country_Time", None),
        ("Instrument", "Instrument_Time", None),
        ("Night", "Night_Time", None),
        ("Night Takeoff/Landings", "Night_Landing", None),
        ("Night T/O Landing PIC", "Night_Landing", "PIC"),
        ("Night T/O Landing SIC", "Night_Landing", "SIC"),
    ]
    m8710 = {}
    for label, fld, pos in metrics:
        pred = (lambda f: True) if pos is None else (
            lambda f, p=pos: f.get("Flight_Position") == p)
        m8710[label] = (s(fld, lambda f: airplane(f) and pred(f)),
                        s(fld, lambda f: heli(f) and pred(f)),
                        s(fld, lambda f: plift(f) and pred(f)))
    exp["FAA 8710 — Hours by Category"] = m8710

    asel = lambda f: airplane(f) and f.get("Class_from_Aircraft") == "Single-Engine Land"
    amel = lambda f: airplane(f) and f.get("Class_from_Aircraft") == "Multi-Engine Land"
    exp["Class Hours (PIC / SIC)"] = {
        "ASEL": (s("PIC_Time", asel), s("SIC_Time", asel)),
        "AMEL": (s("PIC_Time", amel), s("SIC_Time", amel)),
        "Helicopter": (s("PIC_Time", rotor), s("SIC_Time", rotor)),
        "Powered Lift": (s("PIC_Time", plift), s("SIC_Time", plift)),
    }

    # Currency buckets per aircraft
    cur = defaultdict(lambda: [0.0] * 6)
    for f in flights:
        if not f.get("Flight_Date"):
            continue
        name = aircraft.get(f.get("Aircraft"), {}).get("Aircraft", "?")
        m = months_ago(f["Flight_Date"])
        idx = 0 if m <= 12 else 1 if m <= 24 else 2 if m <= 36 else \
            3 if m <= 48 else 4 if m <= 60 else 5
        cur[name][idx] += num(f.get("Block_Time"))
    exp["Currency — Block Hours by Recency"] = {
        name: tuple(round(x, 1) for x in v) for name, v in cur.items()}
    return exp


def _raw(table):
    import json
    import urllib.request
    from verify_daily_ops import GRIST_URL, GRIST_DOC, grist_key
    req = urllib.request.Request(
        f"{GRIST_URL}/api/docs/{GRIST_DOC}/tables/{table}/records")
    req.add_header("Authorization", f"Bearer {grist_key()}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["records"]


def aircraft_attr(aircraft, name, attr):
    for a in aircraft.values():
        if a.get("Aircraft") == name:
            return a.get(attr)
    return None


def compare_named(expected, rows):
    """Rows keyed by first column; remaining columns compared in order.
    Numeric cells use TOL; strings compared exactly."""
    diffs = []
    got = {r[0]: tuple(r[1:]) for r in rows}
    for k, vals in expected.items():
        if k not in got:
            diffs.append(f"missing row {k!r}")
            continue
        for i, v in enumerate(vals):
            g = got[k][i]
            if isinstance(v, (int, float)):
                if g is None or abs(float(g) - float(v)) > TOL:
                    diffs.append(f"{k}[{i}]: expected {v}, got {g}")
            elif (g or None) != (v or None):
                diffs.append(f"{k}[{i}]: expected {v!r}, got {g!r}")
    for k in got:
        if k not in expected:
            diffs.append(f"unexpected row {k!r}")
    return diffs


def main():
    mb = Metabase()
    mb.login()
    coll = next(c["id"] for c in mb.get("/api/collection")
                if c.get("name") == "Logbook" and not c.get("archived"))
    items = mb.get(f"/api/collection/{coll}/items?models=card")
    cards = {it["name"]: it["id"] for it in items["data"]}

    expected = build_expected()
    lines, failures = [], 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Application Reference verification — {stamp}\n")
    lines.append("Every card recomputed independently from live Grist REST "
                 f"(tolerance {TOL}).\n")
    lines.append("| Card | Result |")
    lines.append("|------|--------|")
    for name, exp in expected.items():
        if name not in cards:
            lines.append(f"| {name} | ❌ card not found |")
            failures += 1
            continue
        try:
            rows = mb.card_rows(cards[name])
            if name in ("Totals by Aircraft", "Currency — Block Hours by Recency",
                        "FAA 8710 — Hours by Category", "Class Hours (PIC / SIC)"):
                # strip the hidden 'ord' first column where present
                if name in ("FAA 8710 — Hours by Category", "Class Hours (PIC / SIC)"):
                    rows = [r[1:] for r in rows]
                diffs = compare_named(exp, rows)
            else:
                diffs = compare(exp, rows)
        except Exception as e:
            diffs = [f"query failed: {e}"]
        if diffs:
            failures += 1
            lines.append(f"| {name} | ❌ {'; '.join(diffs)} |")
            print(f"FAIL {name}: {diffs}")
        else:
            lines.append(f"| {name} | ✅ matches live Grist |")
            print(f"OK   {name}")
    lines.append(f"\n**{len(expected) - failures}/{len(expected)} cards verified.**")

    out = os.path.join(REPO_ROOT, "verification-report.md")
    existing = ""
    if os.path.exists(out):
        content = open(out).read()
        idx = content.find("# Application Reference verification")
        existing = content[:idx] if idx >= 0 else content
    with open(out, "w") as f:
        f.write(existing.rstrip() + "\n\n" + "\n".join(lines) + "\n")
    print(f"\n{len(expected) - failures}/{len(expected)} verified -> {out}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
