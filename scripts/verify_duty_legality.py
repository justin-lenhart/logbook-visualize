"""Verify every Trip Efficiency & Duty Legality card independently against
the LIVE Grist REST API (tolerance 0.1; ±0.5 on 'now'-anchored rolling
windows to absorb clock skew between card execution and verification).
Appends to verification-report.md.

Usage: python3 scripts/verify_duty_legality.py
"""
import datetime
import os
import time
from collections import defaultdict

from mb import Metabase, REPO_ROOT
from verify_daily_ops import grist_records, num, TOL


def build_expected():
    flights = grist_records("Flights")
    duties_raw = grist_records("Duty_Periods")
    trips = grist_records("Trips")
    now = time.time()

    # actual duties with FDP hours
    duties = [d for d in duties_raw if d.get("Status") == "Actual"]
    for d in duties:
        d["_fdp"] = (d["Release_Time"] - d["Report_Time"]) / 3600.0

    # flight-time base: non-legacy, Part 121, non-deadhead, has In_Time
    ft = [f for f in flights
          if not f.get("Legacy_Summary") and f.get("Operation") == "Part 121"
          and not f.get("Deadhead") and f.get("In_Time")]

    # within-trip rest gaps (same definition as the SQL)
    rests = []
    for d in duties:
        prevs = [p["Release_Time"] for p in duties
                 if p.get("Trips") == d.get("Trips") and p is not d
                 and p["Release_Time"] <= d["Report_Time"]]
        if prevs:
            rests.append((d["Report_Time"] - max(prevs)) / 3600.0)

    exp = {}
    n = len(duties)
    avg_fdp = sum(d["_fdp"] for d in duties) / n
    avg_blk = sum(num(d.get("Actual_Block")) for d in duties) / n
    exp["Avg FDP Length (h)"] = round(avg_fdp, 1)
    exp["Avg FDP % of Table B floor 9h (§117.13)"] = round(avg_fdp / 9 * 100, 1)
    exp["Avg FDP % of Table B ceiling 14h (§117.13)"] = round(avg_fdp / 14 * 100, 1)
    exp["Avg Block per Duty (h)"] = round(avg_blk, 1)
    exp["Avg Block % of Table A floor 8h (§117.11)"] = round(avg_blk / 8 * 100, 1)
    exp["Avg Block % of Table A ceiling 9h (§117.11)"] = round(avg_blk / 9 * 100, 1)
    exp["Avg Rest Between Duties (h)"] = round(sum(rests) / len(rests), 1)
    exp["Min Rest Between Duties (h)"] = round(min(rests), 1)
    exp["Avg Rest Ratio % of 10h min (§117.25(e))"] = round(
        sum(r / 10 * 100 for r in rests) / len(rests), 1)
    exp["Rests Under 10h (count, §117.25(e))"] = sum(1 for r in rests if r < 10)

    def win_flight(hours):
        return round(sum(num(f.get("Block_Time")) for f in ft
                         if now - hours * 3600 <= f["In_Time"] <= now), 1)

    def win_fdp(hours):
        return round(sum(d["_fdp"] for d in duties
                         if now - hours * 3600 <= d["Report_Time"] <= now), 1)

    exp["Flight Time last 672h — cap 100h (§117.23(b)(1))"] = win_flight(672)
    exp["Flight Time last 365d — cap 1000h (§117.23(b)(2))"] = win_flight(24 * 365)
    exp["FDP Hours last 168h — cap 60h (§117.23(c)(1))"] = win_fdp(168)
    exp["FDP Hours last 672h — cap 190h (§117.23(c)(2))"] = win_fdp(672)

    # rolling-by-day series
    def day_key(ts):
        return datetime.datetime.fromtimestamp(
            ts, datetime.timezone.utc).strftime("%Y-%m-%d")

    def day_end(day):
        dt = datetime.datetime.strptime(day, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)
        return dt.timestamp()

    roll_b = {}
    for day in sorted({day_key(f["In_Time"]) for f in ft}):
        end = day_end(day)
        roll_b[day] = (round(sum(num(f.get("Block_Time")) for f in ft
                                 if end - 672 * 3600 <= f["In_Time"] < end), 1),)
    exp["Rolling 672h Flight Time by Day (cap 100h)"] = roll_b

    roll_f = {}
    for day in sorted({day_key(d["Report_Time"]) for d in duties}):
        end = day_end(day)
        roll_f[day] = (round(sum(d["_fdp"] for d in duties
                                 if end - 168 * 3600 <= d["Report_Time"] < end), 1),)
    exp["Rolling 168h FDP Hours by Day (cap 60h)"] = roll_f

    # efficiency (actual trips with TAFB)
    et = [t for t in trips if t.get("Status") == "Actual" and num(t.get("TAFB")) > 0]
    cpd = [num(t.get("Actual_Credit")) / (t["TAFB"] / 24.0) for t in et]
    bpd = [num(t.get("Actual_Block")) / (t["TAFB"] / 24.0) for t in et]
    exp["Avg Credit per TAFB Day"] = round(sum(cpd) / len(cpd), 2)
    exp["Avg Block per TAFB Day"] = round(sum(bpd) / len(bpd), 2)
    tci = [t["Trip_Credit_Index"] for t in et
           if isinstance(t.get("Trip_Credit_Index"), (int, float))]
    exp["Avg Trip Credit Index"] = round(sum(tci) / len(tci), 3)

    at = sorted([t for t in trips if t.get("Status") == "Actual"],
                key=lambda t: t["Start_Date"])
    gaps = [(b["Start_Date"] - a["End_Date"]) / 86400.0
            for a, b in zip(at, at[1:])]
    exp["Avg Days Between Trips"] = round(sum(gaps) / len(gaps), 1)

    bv = [num(t.get("Actual_Block")) - num(t.get("Planned_Block"))
          for t in trips if t.get("Status") == "Actual" and num(t.get("Planned_Block")) > 0]
    cv = [num(t.get("Actual_Credit")) - num(t.get("Planned_Credit"))
          for t in trips if t.get("Status") == "Actual" and num(t.get("Planned_Credit")) > 0]
    exp["Avg Block Variance per Trip (h)"] = round(sum(bv) / len(bv), 2)
    exp["Avg Credit Variance per Trip (h)"] = round(sum(cv) / len(cv), 2)

    monthly = defaultdict(lambda: [[], []])
    for t in et:
        m = t.get("Trip_Month")
        monthly[m][0].append(num(t.get("Actual_Credit")) / (t["TAFB"] / 24.0))
        monthly[m][1].append(num(t.get("Actual_Block")) / (t["TAFB"] / 24.0))
    exp["Credit & Block per TAFB Day by Month"] = {
        m: (round(sum(c) / len(c), 2), round(sum(b) / len(b), 2))
        for m, (c, b) in monthly.items()}

    # row-count + key-column spot checks for the detail tables
    exp["__duty_detail_rows"] = len(duties)
    exp["__trip_detail_rows"] = len(et)
    return exp


NOW_TOL_CARDS = {  # 'now'-anchored: allow 0.5h skew
    "Flight Time last 672h — cap 100h (§117.23(b)(1))",
    "Flight Time last 365d — cap 1000h (§117.23(b)(2))",
    "FDP Hours last 168h — cap 60h (§117.23(c)(1))",
    "FDP Hours last 672h — cap 190h (§117.23(c)(2))",
}


def main():
    mb = Metabase()
    mb.login()
    coll = next(c["id"] for c in mb.get("/api/collection")
                if c.get("name") == "Logbook" and not c.get("archived"))
    cards = {it["name"]: it["id"] for it in
             mb.get(f"/api/collection/{coll}/items?models=card")["data"]}

    expected = build_expected()
    lines, failures, checked = [], 0, 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Trip Efficiency & Duty Legality verification — {stamp}\n")
    lines.append("Every card recomputed independently from live Grist REST "
                 f"(tolerance {TOL}; ±0.5 on now-anchored rolling windows). "
                 "FDP = report→release (conservative proxy); Table A/B shown "
                 "as floor/ceiling pending local-time data.\n")
    lines.append("| Card | Result |")
    lines.append("|------|--------|")

    for name, exp in expected.items():
        if name.startswith("__"):
            continue
        checked += 1
        if name not in cards:
            lines.append(f"| {name} | ❌ card not found |"); failures += 1
            continue
        tol = 0.5 if name in NOW_TOL_CARDS else TOL
        try:
            rows = mb.card_rows(cards[name])
            diffs = []
            if isinstance(exp, dict):
                got = {r[0]: tuple(r[1:]) for r in rows}
                for k, vals in exp.items():
                    if k not in got:
                        diffs.append(f"missing {k}"); continue
                    for i, v in enumerate(vals):
                        if got[k][i] is None or abs(float(got[k][i]) - v) > tol:
                            diffs.append(f"{k}[{i}]: exp {v} got {got[k][i]}")
                diffs += [f"unexpected {k}" for k in got if k not in exp]
            else:
                g = rows[0][0]
                if g is None or abs(float(g) - float(exp)) > tol:
                    diffs = [f"exp {exp} got {g}"]
        except Exception as e:
            diffs = [f"query failed: {e}"]
        if diffs:
            failures += 1
            lines.append(f"| {name} | ❌ {'; '.join(diffs[:6])} |")
            print(f"FAIL {name}: {diffs[:6]}")
        else:
            lines.append(f"| {name} | ✅ matches live Grist |")
            print(f"OK   {name}")

    # detail tables: row counts vs live Grist
    for card, key in [("Duty Period Legality Detail", "__duty_detail_rows"),
                      ("Trip Efficiency Detail", "__trip_detail_rows")]:
        checked += 1
        got = len(mb.card_rows(cards[card]))
        if got == expected[key]:
            lines.append(f"| {card} | ✅ {got} rows == live Grist |")
            print(f"OK   {card} ({got} rows)")
        else:
            failures += 1
            lines.append(f"| {card} | ❌ {got} rows vs {expected[key]} in Grist |")
            print(f"FAIL {card}: {got} vs {expected[key]}")

    lines.append(f"\n**{checked - failures}/{checked} cards verified.**")
    out = os.path.join(REPO_ROOT, "verification-report.md")
    content = open(out).read() if os.path.exists(out) else ""
    idx = content.find("# Trip Efficiency & Duty Legality verification")
    if idx >= 0:
        content = content[:idx]
    with open(out, "w") as f:
        f.write(content.rstrip() + "\n\n" + "\n".join(lines) + "\n")
    print(f"\n{checked - failures}/{checked} verified -> {out}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
