"""Stage-2 verification: recompute the Efficiency dashboard numbers
INDEPENDENTLY from the LIVE Grist REST API (not the synced SQLite) and compare
them with what each Metabase card returns (unfiltered view). Tolerance 0.011
(cards round to 2 decimals). Writes its own section of verification-report.md.

Usage: python3 scripts/verify_efficiency.py
"""
import datetime
import json
import os
import urllib.request
from collections import Counter, defaultdict

from mb import Metabase, REPO_ROOT
from provision_efficiency import METRICS
from verify_daily_ops import GRIST_DOC, GRIST_URL, grist_key, grist_records, num

TOL = 0.011
SECTION = "# Efficiency verification"
FLEET = {"CR2": "CRJ200", "CR5": "CRJ550", "CR7": "CRJ7&9", "CR9": "CRJ7&9"}


def build_trips():
    aircraft = {a["id"]: a.get("Aircraft") for a in grist_records_with_id("Aircraft")}
    blk = defaultdict(Counter)
    for f in grist_records("Flights"):
        fleet = FLEET.get(aircraft.get(f.get("Aircraft")))
        if f.get("Trips") and fleet and not f.get("Deadhead"):
            blk[f["Trips"]][fleet] += num(f.get("Block_Time"))
    dps, duty = Counter(), defaultdict(float)
    for d in grist_records("Duty_Periods"):
        if d.get("Status") == "Actual" and d.get("Trips"):
            dps[d["Trips"]] += 1
            duty[d["Trips"]] += (d["Release_Time"] - d["Report_Time"]) / 3600.0
    line = {b["Month"]: b["Line_Type"] for b in grist_records("Bid_Months")}
    rsr = {(r["Fleet"], r["Data_Month"]): r for r in grist_records("RSR_Metrics")
           if r.get("Scope") == "SYS"}
    trips = []
    for t in grist_records_with_id("Trips"):
        if t.get("Status") != "Actual" or not num(t.get("TAFB")) or not dps[t["id"]]:
            continue
        fleet = (sorted(blk[t["id"]].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                 if blk[t["id"]] else None)
        trips.append({
            "month": t["Trip_Month"], "fleet": fleet,
            "line_type": line.get(t["Trip_Month"], "Unlabeled"),
            "cr": num(t.get("Actual_Credit")), "bk": num(t.get("Actual_Block")),
            "tafb": num(t.get("TAFB")), "days": num(t.get("Trip_Length")),
            "dps": dps[t["id"]], "duty": duty[t["id"]],
            "rsr": rsr.get((fleet, t["Trip_Month"]), {}),
        })
    return trips


def grist_records_with_id(table):
    """Like verify_daily_ops.grist_records, but keeps the row id (refs point at it)."""
    req = urllib.request.Request(
        f"{GRIST_URL}/api/docs/{GRIST_DOC}/tables/{table}/records")
    req.add_header("Authorization", f"Bearer {grist_key()}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return [{"id": rec["id"], **rec["fields"]} for rec in json.load(r)["records"]]


def ratio(trips, expr):
    num_key, den_key = {
        "SUM(cr) / SUM(dps)": ("cr", "dps"), "SUM(cr) / SUM(days)": ("cr", "days"),
        "SUM(bk) / SUM(dps)": ("bk", "dps"), "SUM(bk) / SUM(days)": ("bk", "days"),
        "SUM(tafb) / SUM(bk)": ("tafb", "bk"), "SUM(tafb) / SUM(cr)": ("tafb", "cr"),
        "SUM(duty) / SUM(bk)": ("duty", "bk"), "SUM(duty) / SUM(cr)": ("duty", "cr"),
    }[expr]
    den = sum(t[den_key] for t in trips)
    return sum(t[num_key] for t in trips) / den if den else None


def system(trips, col):
    vals = [t["rsr"][col] for t in trips if isinstance(t["rsr"].get(col), (int, float))]
    return sum(vals) / len(vals) if vals else None


def build_expected(trips):
    exp = {}
    rows = {}
    for label, better, expr, col in METRICS:
        you, sys_ = ratio(trips, expr), system(trips, col)
        idx = (you / sys_ if better == "Higher" else sys_ / you) if you and sys_ else None
        rows[label] = (you, sys_, idx)
    exp["Personal vs SkyWest"] = rows
    exp["Trips in View"] = len(trips)
    exp["Credit in View"] = sum(t["cr"] for t in trips)
    by_month = defaultdict(list)
    for t in trips:
        by_month[t["month"]].append(t)
    for card, i in [("Credit per Day by Month", 1),
                    ("Credit per Duty Period by Month", 0),
                    ("TAFB per Credit by Month", 5),
                    ("Duty per Credit by Month", 7)]:
        _l, _b, expr, col = METRICS[i]
        exp[card] = {m: (ratio(ts, expr), system(ts, col)) for m, ts in by_month.items()}
    return exp


def compare(expected, rows, key_cols=1, skip_cols=0):
    diffs = []
    if not isinstance(expected, dict):
        got = rows[0][0] if rows and rows[0] else None
        if got is None or abs(float(got) - float(expected)) > max(TOL, 0.051):
            diffs.append(f"expected {expected:.2f}, card returned {got}")
        return diffs
    got = {r[0]: r[key_cols + skip_cols:] for r in rows}
    for k, vals in expected.items():
        if k not in got:
            diffs.append(f"missing {k!r}")
            continue
        for i, v in enumerate(vals):
            g = got[k][i]
            if (v is None) != (g is None) or (v is not None and abs(g - v) > TOL):
                diffs.append(f"{k}[{i}]: expected {v}, got {g}")
    extra = set(got) - set(expected)
    if extra:
        diffs.append(f"unexpected keys {sorted(extra)}")
    return diffs


def main():
    mb = Metabase()
    mb.login()
    coll = next(c["id"] for c in mb.get("/api/collection")
                if c.get("name") == "Logbook" and not c.get("archived"))
    cards = {it["name"]: it["id"] for it in
             mb.get(f"/api/collection/{coll}/items?models=card")["data"]}
    trips = build_trips()
    expected = build_expected(trips)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"{SECTION} — {stamp}\n",
             f"Recomputed independently from live Grist REST ({len(trips)} trips, "
             f"tolerance {TOL}).\n", "| Card | Result |", "|------|--------|"]
    failures = 0
    for name, exp in expected.items():
        try:
            rows = mb.card_rows(cards[name])
            # the comparison table carries a 'Better' column after the key
            diffs = compare(exp, rows, skip_cols=1 if name == "Personal vs SkyWest" else 0)
        except Exception as e:  # missing card or query failure
            diffs = [f"{type(e).__name__}: {e}"]
        if diffs:
            failures += 1
            lines.append(f"| {name} | ❌ {'; '.join(diffs)} |")
            print(f"FAIL {name}: {diffs}")
        else:
            lines.append(f"| {name} | ✅ matches live Grist |")
            print(f"OK   {name}")
    lines.append(f"\n**{len(expected) - failures}/{len(expected)} cards verified.**")

    out = os.path.join(REPO_ROOT, "verification-report.md")
    existing = open(out).read() if os.path.exists(out) else ""
    idx = existing.find(SECTION)
    if idx >= 0:  # replace our section (always last) in place
        existing = existing[:idx]
    with open(out, "w") as f:
        f.write(existing.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n")
    print(f"\n{len(expected) - failures}/{len(expected)} verified -> {out}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
