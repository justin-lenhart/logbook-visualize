"""Provision the "Trip Efficiency & Duty Legality" dashboard.

PERSONAL ANALYTICS ONLY — this is a curiosity/awareness tool, NOT a
compliance system (see the disclaimer card the script installs).

Design notes (citations validated against eCFR July 2026 — see
logbook repo docs/part117-compliance-plan.md):
- FDP length uses Report->Release (slightly conservative proxy for the
  regulatory report->last-block-in FDP; both are shown per duty period).
- Table A (§117.11) flight-time and Table B (§117.13) FDP limits key off
  LOCAL acclimated report time, which is BLOCKED (Airports.UTC_Offset is
  all zeros) — so utilization is shown against BOTH the table floor and
  ceiling (Table A: 8h/9h; Table B: 9h/14h) and labeled as a range.
- Cumulative limits (§117.23): flight time 100h/672h + 1000h/365d,
  FDP 60h/168h + 190h/672h. Flight time excludes deadhead (deadhead legs
  carry 0 block in this logbook anyway) and legacy/non-121 rows.
- Rest (§117.25(e)): 10h minimum before an FDP; within-trip gaps only
  (between-trip gaps are days off, tracked as an efficiency metric).
- Filters: Start/End date, Trip, Aircraft as dashboard widgets mapped to
  optional template tags. Rolling-window "current" cards are always
  as-of-now (deliberately unfiltered).
- Click-through: legality scalars link to the duty-period detail table,
  efficiency scalars to the trip detail table.

Usage: python3 scripts/provision_duty_legality.py
"""
import uuid

from mb import Metabase
from provision_daily_ops import get_logbook_db_id, ensure_collection

DASHBOARD_NAME = "Trip Efficiency & Duty Legality"

# Cards removed from the dashboard; archived so they do not linger. Trip
# Credit Index is retired (see provision_pairing_productivity.py).
RETIRED_CARDS = {"Avg Trip Credit Index"}

DISCLAIMER = (
    "## ⚠️ Personal analytics — NOT a compliance system\n\n"
    "Numbers here are curiosity/awareness metrics computed from my logbook "
    "copy. **The company's official scheduling/legality system is the sole "
    "authority for 14 CFR 117 legality.** Not modeled: local report time "
    "(Table A/B limits shown as floor–ceiling ranges instead), deadhead/"
    "reserve/augmented-crew/split-duty edge cases, acclimatization, FDP "
    "extensions, and CBA limits. Never use these numbers for an actual "
    "legality decision.")

# --- shared SQL fragments -------------------------------------------------
ACT_FLT = ("Legacy_Summary = 0 AND Operation = 'Part 121' AND Deadhead = 0 "
           "AND In_Time IS NOT NULL")


def fdp_hours(a):
    """FDP length (Release - Report) in hours for table alias ``a``.

    SkedPlus stores one duty date, so a release after midnight can land at or
    before report. A duty period is never >24h, so treat that case as a
    next-day release (+86400s). Defensive: after the importer fix no such rows
    remain, but this keeps a stray bad row from ever showing a negative FDP.
    """
    return (f"(CASE WHEN {a}.Release_Time > {a}.Report_Time THEN {a}.Release_Time "
            f"ELSE {a}.Release_Time + 86400 END - {a}.Report_Time) / 3600.0")


FDP_H = fdp_hours("d")

# optional filter fragments (template tags)
D_DATE = ("[[AND d.Duty_Date >= CAST(strftime('%s', {{start_date}}) AS INT)]] "
          "[[AND d.Duty_Date < CAST(strftime('%s', {{end_date}}, '+1 day') AS INT)]]")
T_DATE = ("[[AND t.Start_Date >= CAST(strftime('%s', {{start_date}}) AS INT)]] "
          "[[AND t.Start_Date < CAST(strftime('%s', {{end_date}}, '+1 day') AS INT)]]")
D_TRIP = "[[AND EXISTS (SELECT 1 FROM Trips tt WHERE tt.id = d.Trips AND tt.Trip_Key LIKE '%' || {{trip}} || '%')]]"
T_TRIP = "[[AND t.Trip_Key LIKE '%' || {{trip}} || '%']]"
D_ACFT = ("[[AND EXISTS (SELECT 1 FROM Flights fa JOIN Aircraft aa ON fa.Aircraft = aa.id "
          "WHERE fa.Duty_Period = d.id AND aa.Aircraft = {{aircraft}})]]")

DUTY_BASE = (f"FROM Duty_Periods d WHERE d.Status = 'Actual' {D_DATE} {D_TRIP} {D_ACFT}")

# within-trip rest gaps: consecutive actual duty periods of the same trip
REST_CTE = (
    "WITH rests AS (SELECT d.id, d.Duty_Date, d.Trips, "
    "(d.Report_Time - (SELECT MAX(p.Release_Time) FROM Duty_Periods p "
    "WHERE p.Trips = d.Trips AND p.Status = 'Actual' "
    "AND p.Release_Time <= d.Report_Time AND p.id != d.id)) / 3600.0 AS rest_h "
    f"FROM Duty_Periods d WHERE d.Status = 'Actual' {D_DATE} {D_TRIP} {D_ACFT}) ")

TRIP_EFF_BASE = (
    "FROM Trips t WHERE t.Status = 'Actual' AND t.TAFB > 0 "
    f"{T_DATE} {T_TRIP}")

ROLL_BLOCK_DAY = (
    "WITH days(d) AS (SELECT DISTINCT date(In_Time,'unixepoch') FROM Flights "
    f"WHERE {ACT_FLT}) "
    "SELECT d AS Day, ROUND((SELECT COALESCE(SUM(f.Block_Time),0) FROM Flights f "
    f"WHERE {ACT_FLT.replace('In_Time','f.In_Time').replace('Legacy_Summary','f.Legacy_Summary').replace('Operation','f.Operation').replace('Deadhead','f.Deadhead')} "
    "AND f.In_Time <  CAST(strftime('%s', d, '+1 day') AS INT) "
    "AND f.In_Time >= CAST(strftime('%s', d, '+1 day') AS INT) - {W}*3600),1) "
    "AS [Flight time, trailing {W}h] FROM days ORDER BY d")

ROLL_FDP_DAY = (
    "WITH days(d) AS (SELECT DISTINCT date(Report_Time,'unixepoch') FROM Duty_Periods "
    "WHERE Status='Actual') "
    f"SELECT d AS Day, ROUND((SELECT COALESCE(SUM({fdp_hours('p')}),0) "
    "FROM Duty_Periods p WHERE p.Status='Actual' "
    "AND p.Report_Time <  CAST(strftime('%s', d, '+1 day') AS INT) "
    "AND p.Report_Time >= CAST(strftime('%s', d, '+1 day') AS INT) - {W}*3600),1) "
    "AS [FDP hours, trailing {W}h] FROM days ORDER BY d")


def now_window_flight(hours):
    return ("SELECT ROUND(COALESCE(SUM(Block_Time),0),1) FROM Flights "
            f"WHERE {ACT_FLT} AND In_Time <= CAST(strftime('%s','now') AS INT) "
            f"AND In_Time >= CAST(strftime('%s','now') AS INT) - {hours}*3600")


def now_window_fdp(hours):
    return (f"SELECT ROUND(COALESCE(SUM({fdp_hours('d')}),0),1) "
            "FROM Duty_Periods d WHERE d.Status='Actual' "
            f"AND d.Report_Time <= CAST(strftime('%s','now') AS INT) "
            f"AND d.Report_Time >= CAST(strftime('%s','now') AS INT) - {hours}*3600")


# (name, sql, display, viz, tags) — tags: subset of {start_date,end_date,trip,aircraft}
DT = ("start_date", "end_date")
CARDS = [
    # -- legality averages (filterable) --
    ("Avg FDP Length (h)",
     f"SELECT ROUND(AVG({FDP_H}),1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip", "aircraft")),

    ("Avg FDP % of Table B floor 9h (§117.13)",
     f"SELECT ROUND(AVG({FDP_H}) / 9.0 * 100, 1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " %"}, DT + ("trip", "aircraft")),

    ("Avg FDP % of Table B ceiling 14h (§117.13)",
     f"SELECT ROUND(AVG({FDP_H}) / 14.0 * 100, 1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " %"}, DT + ("trip", "aircraft")),

    ("Avg Block per Duty (h)",
     f"SELECT ROUND(AVG(d.Actual_Block),1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip", "aircraft")),

    ("Avg Block % of Table A floor 8h (§117.11)",
     f"SELECT ROUND(AVG(d.Actual_Block) / 8.0 * 100, 1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " %"}, DT + ("trip", "aircraft")),

    ("Avg Block % of Table A ceiling 9h (§117.11)",
     f"SELECT ROUND(AVG(d.Actual_Block) / 9.0 * 100, 1) {DUTY_BASE}",
     "scalar", {"scalar.suffix": " %"}, DT + ("trip", "aircraft")),

    # -- rest (§117.25(e)) --
    ("Avg Rest Between Duties (h)",
     REST_CTE + "SELECT ROUND(AVG(rest_h),1) FROM rests WHERE rest_h IS NOT NULL",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip", "aircraft")),

    ("Min Rest Between Duties (h)",
     REST_CTE + "SELECT ROUND(MIN(rest_h),1) FROM rests WHERE rest_h IS NOT NULL",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip", "aircraft")),

    ("Avg Rest Ratio % of 10h min (§117.25(e))",
     REST_CTE + "SELECT ROUND(AVG(rest_h / 10.0 * 100),1) FROM rests WHERE rest_h IS NOT NULL",
     "scalar", {"scalar.suffix": " %"}, DT + ("trip", "aircraft")),

    ("Rests Under 10h (count, §117.25(e))",
     REST_CTE + "SELECT COUNT(*) FROM rests WHERE rest_h IS NOT NULL AND rest_h < 10.0",
     "scalar", {}, DT + ("trip", "aircraft")),

    # -- cumulative limits (§117.23), always as-of-now --
    ("Flight Time last 672h — cap 100h (§117.23(b)(1))",
     now_window_flight(672), "progress", {"progress.goal": 100}, ()),

    ("Flight Time last 365d — cap 1000h (§117.23(b)(2))",
     now_window_flight(24 * 365), "progress", {"progress.goal": 1000}, ()),

    ("FDP Hours last 168h — cap 60h (§117.23(c)(1))",
     now_window_fdp(168), "progress", {"progress.goal": 60}, ()),

    ("FDP Hours last 672h — cap 190h (§117.23(c)(2))",
     now_window_fdp(672), "progress", {"progress.goal": 190}, ()),

    ("Rolling 672h Flight Time by Day (cap 100h)",
     ROLL_BLOCK_DAY.replace("{W}", "672"),
     "line", {"graph.dimensions": ["Day"],
              "graph.metrics": ["Flight time, trailing 672h"],
              "graph.goal_value": 100, "graph.show_goal": True,
              "graph.goal_label": "100h cap"}, ()),

    ("Rolling 168h FDP Hours by Day (cap 60h)",
     ROLL_FDP_DAY.replace("{W}", "168"),
     "line", {"graph.dimensions": ["Day"],
              "graph.metrics": ["FDP hours, trailing 168h"],
              "graph.goal_value": 60, "graph.show_goal": True,
              "graph.goal_label": "60h cap"}, ()),

    # -- efficiency (filterable) --
    ("Avg Credit per TAFB Day",
     f"SELECT ROUND(AVG(t.Actual_Credit / (t.TAFB / 24.0)),2) {TRIP_EFF_BASE}",
     "scalar", {"scalar.suffix": " h/day"}, DT + ("trip",)),

    ("Avg Block per TAFB Day",
     f"SELECT ROUND(AVG(t.Actual_Block / (t.TAFB / 24.0)),2) {TRIP_EFF_BASE}",
     "scalar", {"scalar.suffix": " h/day"}, DT + ("trip",)),

    ("Avg Days Between Trips",
     "SELECT ROUND(AVG(gap),1) FROM (SELECT (t.Start_Date - LAG(t.End_Date) "
     "OVER (ORDER BY t.Start_Date)) / 86400.0 AS gap "
     "FROM Trips t WHERE t.Status = 'Actual') WHERE gap IS NOT NULL",
     "scalar", {"scalar.suffix": " days"}, ()),

    ("Avg Block Variance per Trip (h)",
     "SELECT ROUND(AVG(t.Actual_Block - t.Planned_Block),2) FROM Trips t "
     f"WHERE t.Status = 'Actual' AND t.Planned_Block > 0 {T_DATE} {T_TRIP}",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip",)),

    ("Avg Credit Variance per Trip (h)",
     "SELECT ROUND(AVG(t.Actual_Credit - t.Planned_Credit),2) FROM Trips t "
     f"WHERE t.Status = 'Actual' AND t.Planned_Credit > 0 {T_DATE} {T_TRIP}",
     "scalar", {"scalar.suffix": " h"}, DT + ("trip",)),

    ("Credit & Block per TAFB Day by Month",
     "SELECT t.Trip_Month AS Month, "
     "ROUND(AVG(t.Actual_Credit / (t.TAFB / 24.0)),2) AS [Credit/day], "
     "ROUND(AVG(t.Actual_Block / (t.TAFB / 24.0)),2) AS [Block/day] "
     f"{TRIP_EFF_BASE} GROUP BY t.Trip_Month ORDER BY t.Trip_Month",
     "line", {"graph.dimensions": ["Month"],
              "graph.metrics": ["Credit/day", "Block/day"]}, DT + ("trip",)),

    # -- detail tables (drill targets, filterable) --
    ("Duty Period Legality Detail",
     "SELECT d.Duty_Date AS ts_date, "
     "(SELECT tt.Trip_Key FROM Trips tt WHERE tt.id = d.Trips) AS Trip, "
     "strftime('%Y-%m-%d %H:%MZ', d.Report_Time, 'unixepoch') AS [Report (UTC)], "
     "strftime('%H:%MZ', d.Release_Time, 'unixepoch') AS [Release (UTC)], "
     f"ROUND({FDP_H},1) AS [Duty h (rpt-rls)], "
     "ROUND(((SELECT MAX(f.In_Time) FROM Flights f WHERE f.Duty_Period = d.id) "
     "- d.Report_Time) / 3600.0, 1) AS [FDP h (rpt-blkin)], "
     "d.Actual_Block AS [Block h], d.Actual_Legs AS Legs, "
     "ROUND(d.Actual_Block / 8.0 * 100, 0) AS [Blk % of 8h], "
     f"ROUND({FDP_H} / 9.0 * 100, 0) AS [FDP % of 9h], "
     f"ROUND({FDP_H} / 14.0 * 100, 0) AS [FDP % of 14h], "
     "(SELECT ROUND((d.Report_Time - MAX(p.Release_Time)) / 3600.0, 1) "
     "FROM Duty_Periods p WHERE p.Trips = d.Trips AND p.Status = 'Actual' "
     "AND p.Release_Time <= d.Report_Time AND p.id != d.id) AS [Rest before (h)], "
     "(SELECT GROUP_CONCAT(DISTINCT aa.Aircraft) FROM Flights fa "
     "JOIN Aircraft aa ON fa.Aircraft = aa.id WHERE fa.Duty_Period = d.id) AS Aircraft "
     f"{DUTY_BASE} ORDER BY d.Report_Time DESC",
     "table", {"column_settings": {'["name","ts_date"]': {"column_title": "Date"}}},
     DT + ("trip", "aircraft")),

    ("Trip Efficiency Detail",
     "SELECT t.Trip_Key AS Trip, date(t.Start_Date,'unixepoch') AS Start, "
     "date(t.End_Date,'unixepoch') AS [End], "
     "ROUND(t.TAFB / 24.0, 2) AS [TAFB days], "
     "t.Actual_Block AS [Block h], t.Actual_Credit AS [Credit h], "
     "ROUND(t.Actual_Credit / (t.TAFB / 24.0), 2) AS [Credit/day], "
     "ROUND(t.Actual_Block / (t.TAFB / 24.0), 2) AS [Block/day], "
     "ROUND(CASE WHEN t.Actual_Block > 0 THEN t.Actual_Credit / t.Actual_Block END, 2) AS [Credit:Block], "
     "CASE WHEN t.Planned_Block > 0 THEN ROUND(t.Actual_Block - t.Planned_Block, 2) END AS [Blk Var], "
     "CASE WHEN t.Planned_Credit > 0 THEN ROUND(t.Actual_Credit - t.Planned_Credit, 2) END AS [Cr Var], "
     "ROUND((t.Start_Date - (SELECT MAX(p.End_Date) FROM Trips p "
     "WHERE p.Status = 'Actual' AND p.End_Date <= t.Start_Date AND p.id != t.id)) "
     "/ 86400.0, 1) AS [Days since prev] "
     f"{TRIP_EFF_BASE} ORDER BY t.Start_Date DESC",
     "table", {}, DT + ("trip",)),
]

TAG_DEFS = {
    "start_date": ("date", "Start Date"),
    "end_date": ("date", "End Date"),
    "trip": ("text", "Trip"),
    "aircraft": ("text", "Aircraft"),
}

PARAMETERS = [
    {"id": "p-startdate", "name": "Start Date", "slug": "start_date",
     "type": "date/single", "sectionId": "date"},
    {"id": "p-enddate", "name": "End Date", "slug": "end_date",
     "type": "date/single", "sectionId": "date"},
    {"id": "p-trip", "name": "Trip", "slug": "trip",
     "type": "category", "sectionId": "string"},
    {"id": "p-aircraft", "name": "Aircraft", "slug": "aircraft",
     "type": "category", "sectionId": "string"},
]
PARAM_FOR_TAG = {"start_date": "p-startdate", "end_date": "p-enddate",
                 "trip": "p-trip", "aircraft": "p-aircraft"}

# layout: (row, col, sx, sy) — disclaimer text card occupies row 0
LAYOUT = {
    "Avg FDP Length (h)": (3, 0, 6, 3),
    "Avg FDP % of Table B floor 9h (§117.13)": (3, 6, 6, 3),
    "Avg FDP % of Table B ceiling 14h (§117.13)": (3, 12, 6, 3),
    "Avg Block per Duty (h)": (3, 18, 6, 3),
    "Avg Block % of Table A floor 8h (§117.11)": (6, 0, 6, 3),
    "Avg Block % of Table A ceiling 9h (§117.11)": (6, 6, 6, 3),
    "Avg Rest Between Duties (h)": (6, 12, 6, 3),
    "Min Rest Between Duties (h)": (6, 18, 6, 3),
    "Avg Rest Ratio % of 10h min (§117.25(e))": (9, 0, 6, 3),
    "Rests Under 10h (count, §117.25(e))": (9, 6, 6, 3),
    "Flight Time last 672h — cap 100h (§117.23(b)(1))": (12, 0, 12, 3),
    "Flight Time last 365d — cap 1000h (§117.23(b)(2))": (12, 12, 12, 3),
    "FDP Hours last 168h — cap 60h (§117.23(c)(1))": (15, 0, 12, 3),
    "FDP Hours last 672h — cap 190h (§117.23(c)(2))": (15, 12, 12, 3),
    "Rolling 672h Flight Time by Day (cap 100h)": (18, 0, 12, 6),
    "Rolling 168h FDP Hours by Day (cap 60h)": (18, 12, 12, 6),
    "Duty Period Legality Detail": (24, 0, 24, 9),
    "Avg Credit per TAFB Day": (33, 0, 8, 3),
    "Avg Block per TAFB Day": (33, 8, 8, 3),
    "Avg Days Between Trips": (33, 16, 8, 3),
    "Avg Block Variance per Trip (h)": (36, 0, 6, 3),
    "Avg Credit Variance per Trip (h)": (36, 6, 6, 3),
    "Credit & Block per TAFB Day by Month": (36, 12, 12, 6),
    "Trip Efficiency Detail": (42, 0, 24, 9),
}

# scalar -> detail-table click-through
CLICK_TARGET = {
    "Avg FDP Length (h)": "Duty Period Legality Detail",
    "Avg FDP % of Table B floor 9h (§117.13)": "Duty Period Legality Detail",
    "Avg FDP % of Table B ceiling 14h (§117.13)": "Duty Period Legality Detail",
    "Avg Block per Duty (h)": "Duty Period Legality Detail",
    "Avg Block % of Table A floor 8h (§117.11)": "Duty Period Legality Detail",
    "Avg Block % of Table A ceiling 9h (§117.11)": "Duty Period Legality Detail",
    "Avg Rest Between Duties (h)": "Duty Period Legality Detail",
    "Min Rest Between Duties (h)": "Duty Period Legality Detail",
    "Avg Rest Ratio % of 10h min (§117.25(e))": "Duty Period Legality Detail",
    "Rests Under 10h (count, §117.25(e))": "Duty Period Legality Detail",
    "Avg Credit per TAFB Day": "Trip Efficiency Detail",
    "Avg Block per TAFB Day": "Trip Efficiency Detail",
    "Avg Days Between Trips": "Trip Efficiency Detail",
    "Avg Block Variance per Trip (h)": "Trip Efficiency Detail",
    "Avg Credit Variance per Trip (h)": "Trip Efficiency Detail",
}


def make_card(mb, name, sql, display, viz, tags, db_id, coll_id):
    template_tags = {}
    for tag in tags:
        ttype, disp = TAG_DEFS[tag]
        template_tags[tag] = {
            "id": str(uuid.uuid4()), "name": tag, "display-name": disp,
            "type": ttype, "required": False,
        }
    if display == "scalar":
        viz = {"scalar.compact_primary_number": False, **viz}
    return mb.post("/api/card", {
        "name": name, "display": display,
        "visualization_settings": viz, "collection_id": coll_id,
        "dataset_query": {
            "type": "native", "database": db_id,
            "native": {"query": sql, "template-tags": template_tags},
        },
    })


def main():
    mb = Metabase()
    mb.login()
    db_id = get_logbook_db_id(mb)
    coll_id = ensure_collection(mb)

    # archive existing same-name cards (idempotent re-run)
    items = mb.get(f"/api/collection/{coll_id}/items?models=card")
    names = {c[0] for c in CARDS} | RETIRED_CARDS
    for it in items.get("data", []):
        if it["name"] in names:
            mb.put(f"/api/card/{it['id']}", {"archived": True})

    # dashboard (reuse if present)
    dashes = mb.get("/api/dashboard")
    dl = dashes if isinstance(dashes, list) else dashes.get("data", [])
    dash_id = next((d["id"] for d in dl
                    if d["name"] == DASHBOARD_NAME and not d.get("archived")), None)
    if dash_id is None:
        dash_id = mb.post("/api/dashboard", {
            "name": DASHBOARD_NAME, "collection_id": coll_id})["id"]

    made = {}
    for name, sql, display, viz, tags in CARDS:
        card = make_card(mb, name, sql, display, viz, tags, db_id, coll_id)
        made[name] = card["id"]
        print(f"  card {card['id']:>3}  {name}")

    dashcards = [{
        "id": -1000, "card_id": None, "row": 0, "col": 0,
        "size_x": 24, "size_y": 3, "parameter_mappings": [],
        "visualization_settings": {
            "virtual_card": {"name": None, "display": "text",
                             "visualization_settings": {},
                             "dataset_query": {}, "archived": False},
            "text": DISCLAIMER},
    }]
    for i, (name, _sql, _display, _viz, tags) in enumerate(CARDS):
        r, c, sx, sy = LAYOUT[name]
        viz = {}
        if name in CLICK_TARGET:
            viz["click_behavior"] = {
                "type": "link", "linkType": "question",
                "targetId": made[CLICK_TARGET[name]]}
        dashcards.append({
            "id": -(i + 1), "card_id": made[name],
            "row": r, "col": c, "size_x": sx, "size_y": sy,
            "parameter_mappings": [
                {"parameter_id": PARAM_FOR_TAG[t], "card_id": made[name],
                 "target": ["variable", ["template-tag", t]]}
                for t in tags],
            "visualization_settings": viz,
        })

    mb.put(f"/api/dashboard/{dash_id}",
           {"parameters": PARAMETERS, "dashcards": dashcards})
    print(f"dashboard '{DASHBOARD_NAME}' (id {dash_id}): "
          f"{len(dashcards)} dashcards (incl. disclaimer), "
          f"{len(PARAMETERS)} filters")


if __name__ == "__main__":
    main()
