"""Stage-2 verification: recompute every Daily Ops number INDEPENDENTLY from
the LIVE Grist REST API (not the synced SQLite) and compare against what each
Metabase card actually returns. Tolerance 0.1. Writes verification-report.md.

Usage: python3 scripts/verify_daily_ops.py
"""
import datetime
import json
import os
import urllib.request
from collections import defaultdict

from mb import Metabase, REPO_ROOT

GRIST_URL = "http://100.78.241.102:8484"
GRIST_DOC = open("/home/mint/Developer/homelab/migration/grist-doc.txt").read().strip()
TOL = 0.1


def grist_key():
    for line in open("/home/mint/Developer/homelab/migration/.env"):
        if line.startswith("GRIST_API_KEY="):
            return line.strip().split("=", 1)[1]
    raise RuntimeError("no GRIST_API_KEY")


def grist_records(table):
    req = urllib.request.Request(
        f"{GRIST_URL}/api/docs/{GRIST_DOC}/tables/{table}/records")
    req.add_header("Authorization", f"Bearer {grist_key()}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return [rec["fields"] for rec in json.load(r)["records"]]


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def month_of(epoch):
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).strftime("%Y-%m")


def build_expected():
    flights = grist_records("Flights")
    trips = grist_records("Trips")
    now_month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

    exp = {}
    # career tiles (legacy included)
    exp["Career: Total Time"] = round(sum(num(f.get("Block_Time")) for f in flights), 1)
    exp["Career: PIC"] = round(sum(num(f.get("PIC_Time")) for f in flights), 1)
    exp["Career: SIC"] = round(sum(num(f.get("SIC_Time")) for f in flights), 1)
    exp["Career: Night"] = round(sum(num(f.get("Night_Time")) for f in flights), 1)
    exp["Career: Instrument"] = round(sum(num(f.get("Instrument_Time")) for f in flights), 1)
    exp["Career: Cross Country"] = round(sum(num(f.get("Cross_Country_Time")) for f in flights), 1)
    exp["Career: Credit"] = round(sum(num(f.get("Credit_Time")) for f in flights), 1)
    exp["Career: Landings"] = int(sum(num(f.get("Total_Landing")) for f in flights))
    exp["Career: Flights"] = len(flights)
    exp["Passengers Adventured"] = int(sum(num(f.get("Passengers")) for f in flights
                                           if not f.get("Deadhead")))

    # current-month tiles (legacy excluded)
    cur = [f for f in flights
           if f.get("Flight_Date") and month_of(f["Flight_Date"]) == now_month
           and not f.get("Legacy_Summary")]
    exp["This Month: Block"] = round(sum(num(f.get("Block_Time")) for f in cur), 1)
    exp["This Month: Credit"] = round(sum(num(f.get("Credit_Time")) for f in cur), 1)
    exp["This Month: Flights"] = len(cur)
    exp["This Month: Landings"] = int(sum(num(f.get("Total_Landing")) for f in cur))

    # monthly P121 trend (legacy excluded)
    trend = defaultdict(lambda: [0.0, 0.0])
    for f in flights:
        if f.get("Operation") == "Part 121" and not f.get("Legacy_Summary"):
            m = f.get("Flight_Month")
            trend[m][0] += num(f.get("Block_Time"))
            trend[m][1] += num(f.get("Credit_Time"))
    exp["Monthly Block & Credit (Part 121)"] = {
        m: (round(b, 1), round(c, 1)) for m, (b, c) in trend.items()}

    # trips planned vs actual
    pb, pc = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
    tafb = defaultdict(list)
    for t in trips:
        m = t.get("Trip_Month")
        pb[m][0] += num(t.get("Planned_Block"))
        pb[m][1] += num(t.get("Actual_Block"))
        pc[m][0] += num(t.get("Planned_Credit"))
        pc[m][1] += num(t.get("Actual_Credit"))
        if isinstance(t.get("TAFB"), (int, float)):
            tafb[m].append(t["TAFB"])
    exp["Planned vs Actual Block by Month"] = {
        m: (round(p, 1), round(a, 1)) for m, (p, a) in pb.items()}
    exp["Planned vs Actual Credit by Month"] = {
        m: (round(p, 1), round(a, 1)) for m, (p, a) in pc.items()}
    exp["Avg TAFB by Month"] = {
        m: (round(sum(v) / len(v), 1),) for m, v in tafb.items()}

    # pivots (legacy included, all ops)
    for card, field in [("Block by Category x Position", "Category"),
                        ("Block by Class x Position", "Class"),
                        ("Block by Engine x Position", "Engine_Category_from_Aircraft")]:
        piv = defaultdict(lambda: [0.0, 0.0, 0.0])
        for f in flights:
            k = f.get(field)
            if not k:
                continue
            b = num(f.get("Block_Time"))
            if f.get("Flight_Position") == "PIC":
                piv[k][0] += b
            elif f.get("Flight_Position") == "SIC":
                piv[k][1] += b
            piv[k][2] += b
        exp[card] = {k: tuple(round(x, 1) for x in v) for k, v in piv.items()}
    return exp


def compare(expected, got_rows):
    """expected: scalar or {key: tuple-of-numbers}; got_rows: card result rows."""
    diffs = []
    if not isinstance(expected, dict):
        got = got_rows[0][0] if got_rows and got_rows[0] else None
        if got is None or abs(float(got) - float(expected)) > TOL:
            diffs.append(f"expected {expected}, card returned {got}")
        return diffs
    got_map = {r[0]: tuple(r[1:]) for r in got_rows}
    for k, vals in expected.items():
        if k not in got_map:
            diffs.append(f"missing key {k!r} (expected {vals})")
            continue
        for i, v in enumerate(vals):
            g = got_map[k][i]
            if g is None or abs(float(g) - float(v)) > TOL:
                diffs.append(f"{k}[{i}]: expected {v}, got {g}")
    for k in got_map:
        if k not in expected:
            diffs.append(f"unexpected key {k!r} in card output")
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
    lines.append(f"# Daily Ops verification — {stamp}\n")
    lines.append("Every card recomputed independently from live Grist REST "
                 f"(tolerance {TOL}).\n")
    lines.append("| Card | Result |")
    lines.append("|------|--------|")
    for name, exp in expected.items():
        if name not in cards:
            lines.append(f"| {name} | ❌ card not found in Metabase |")
            failures += 1
            continue
        try:
            rows = mb.card_rows(cards[name])
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
        existing = open(out).read()
        # keep only the application-reference section if present
        idx = existing.find("# Application Reference verification")
        existing = existing[idx:] if idx >= 0 else ""
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n\n" + existing)
    print(f"\n{len(expected) - failures}/{len(expected)} verified -> {out}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
