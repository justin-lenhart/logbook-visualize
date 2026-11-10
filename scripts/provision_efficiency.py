"""Efficiency dashboard: your flown trips vs SkyWest RSR averages.

Personal: totals over your flown trips, e.g. credit per day = total credit /
total trip days.
SkyWest: for each month, the average of the CRJ200, CRJ550 and CRJ7&9 values
in the Grist RSR_Metrics table.
ORD: the same average over the ORD domicile reports, which publish credit per
day only, so ORD appears on that one metric and nowhere else.

Usage: python3 scripts/provision_efficiency.py
"""
from mb import Metabase
from provision_daily_ops import (ensure_collection, get_logbook_db_id,
                                 TS_SQL, SYNC_SQL, FRESHNESS_TITLES)

DASHBOARD_NAME = "Efficiency"

HEADER = (
    "**Efficiency Metrics: flown trips vs SkyWest RSR averages.** "
    "*SkyWest* values are the system-wide RSR values, averaged across the "
    "CRJ200, CRJ550 and CRJ7&9 fleets. **Index = Personal ÷ SkyWest** for "
    "'Higher' metrics and SkyWest ÷ Personal for 'Lower' metrics, so an "
    "Index above 1.00 always means better than SkyWest. *ORD* is the same "
    "average over the ORD reports, which publish credit per day only.")

# One row per flown trip: credit, block, TAFB, days, duty periods, duty hours.
FLOWN = """
  SELECT t.Trip_Key AS trip, t.Trip_Month AS month, t.Start_Date AS start,
         t.Actual_Credit AS credit, t.Actual_Block AS block, t.TAFB AS tafb,
         t.Trip_Length AS days, COUNT(d.id) AS dps,
         SUM((d.Release_Time - d.Report_Time) / 3600.0) AS duty
  FROM Trips t
  JOIN Duty_Periods d ON d.Trips = t.id AND d.Status = 'Actual'
  WHERE t.Status = 'Actual' AND t.TAFB > 0
  GROUP BY t.id
"""

# Your metrics per month.
PERSONAL = """
  SELECT month, COUNT(*) AS trips,
         SUM(credit) / SUM(dps)  AS cr_dp,   SUM(credit) / SUM(days) AS cr_day,
         SUM(block)  / SUM(dps)  AS bk_dp,   SUM(block)  / SUM(days) AS bk_day,
         SUM(tafb)   / SUM(block) AS tafb_bk, SUM(tafb)  / SUM(credit) AS tafb_cr,
         SUM(duty)   / SUM(block) AS duty_bk, SUM(duty)  / SUM(credit) AS duty_cr
  FROM flown GROUP BY month
"""

# SkyWest metrics per month: average of the three CRJ fleets, system-wide
# reports only (RSR_Metrics also holds domicile rows).
SKYWEST = """
  SELECT Data_Month AS month,
         AVG(Cr_per_DP)   AS cr_dp,   AVG(Cr_per_Day)  AS cr_day,
         AVG(Bk_per_DP)   AS bk_dp,   AVG(Bk_per_Day)  AS bk_day,
         AVG(TAFB_per_Bk) AS tafb_bk, AVG(TAFB_per_Cr) AS tafb_cr,
         AVG(Duty_per_Bk) AS duty_bk, AVG(Duty_per_Cr) AS duty_cr
  FROM RSR_Metrics
  WHERE Scope = 'SYS' AND Fleet IN ('CRJ200', 'CRJ550', 'CRJ7&9')
  GROUP BY Data_Month
"""

# ORD metrics per month: the same average over the ORD domicile reports. They
# carry credit per day and nothing else, so this has one column.
ORD = """
  SELECT Data_Month AS month, AVG(Cr_per_Day) AS cr_day
  FROM RSR_Metrics
  WHERE Scope = 'ORD' AND Fleet IN ('CRJ200', 'CRJ550', 'CRJ7&9')
  GROUP BY Data_Month
"""

WITH = (f"WITH flown AS ({FLOWN}),\n personal AS ({PERSONAL}),\n"
        f" skywest AS ({SKYWEST}),\n ord AS ({ORD})\n")

# All months together: your totals vs the average of SkyWest's monthly values
# for the months you flew.
OVERALL_SQL = WITH + """,
p AS (
  SELECT SUM(credit) / SUM(dps)  AS cr_dp,   SUM(credit) / SUM(days) AS cr_day,
         SUM(block)  / SUM(dps)  AS bk_dp,   SUM(block)  / SUM(days) AS bk_day,
         SUM(tafb)   / SUM(block) AS tafb_bk, SUM(tafb)  / SUM(credit) AS tafb_cr,
         SUM(duty)   / SUM(block) AS duty_bk, SUM(duty)  / SUM(credit) AS duty_cr
  FROM flown),
s AS (
  SELECT AVG(cr_dp) AS cr_dp, AVG(cr_day) AS cr_day, AVG(bk_dp) AS bk_dp,
         AVG(bk_day) AS bk_day, AVG(tafb_bk) AS tafb_bk, AVG(tafb_cr) AS tafb_cr,
         AVG(duty_bk) AS duty_bk, AVG(duty_cr) AS duty_cr
  FROM skywest WHERE month IN (SELECT month FROM flown)),
o AS (SELECT AVG(cr_day) AS cr_day FROM ord WHERE month IN (SELECT month FROM flown))
SELECT 'Credit / duty period' AS Metric, 'Higher' AS Better, ROUND(p.cr_dp, 2) AS Personal, ROUND(s.cr_dp, 2) AS SkyWest, NULL AS ORD, ROUND(p.cr_dp / s.cr_dp, 2) AS [Index] FROM p, s
UNION ALL
SELECT 'Credit / day', 'Higher', ROUND(p.cr_day, 2), ROUND(s.cr_day, 2), ROUND(o.cr_day, 2), ROUND(p.cr_day / s.cr_day, 2) FROM p, s, o
UNION ALL
SELECT 'Block / duty period', 'Higher', ROUND(p.bk_dp, 2), ROUND(s.bk_dp, 2), NULL, ROUND(p.bk_dp / s.bk_dp, 2) FROM p, s
UNION ALL
SELECT 'Block / day', 'Higher', ROUND(p.bk_day, 2), ROUND(s.bk_day, 2), NULL, ROUND(p.bk_day / s.bk_day, 2) FROM p, s
UNION ALL
SELECT 'TAFB / block', 'Lower', ROUND(p.tafb_bk, 2), ROUND(s.tafb_bk, 2), NULL, ROUND(s.tafb_bk / p.tafb_bk, 2) FROM p, s
UNION ALL
SELECT 'TAFB / credit', 'Lower', ROUND(p.tafb_cr, 2), ROUND(s.tafb_cr, 2), NULL, ROUND(s.tafb_cr / p.tafb_cr, 2) FROM p, s
UNION ALL
SELECT 'Duty / block', 'Lower', ROUND(p.duty_bk, 2), ROUND(s.duty_bk, 2), NULL, ROUND(s.duty_bk / p.duty_bk, 2) FROM p, s
UNION ALL
SELECT 'Duty / credit', 'Lower', ROUND(p.duty_cr, 2), ROUND(s.duty_cr, 2), NULL, ROUND(s.duty_cr / p.duty_cr, 2) FROM p, s
"""


# Credit per day is the only metric the ORD reports publish, so it is the one
# chart with three lines and is written out rather than built by chart_sql.
CR_DAY_CHART_SQL = WITH + """
SELECT p.month AS Month, ROUND(p.cr_day, 2) AS Personal,
       ROUND(s.cr_day, 2) AS SkyWest, ROUND(o.cr_day, 2) AS ORD
FROM personal p
LEFT JOIN skywest s ON s.month = p.month
LEFT JOIN ord o ON o.month = p.month
ORDER BY p.month
"""


def chart_sql(column):
    """One metric by month: your value and SkyWest's."""
    return WITH + f"""
SELECT p.month AS Month, ROUND(p.{column}, 2) AS Personal, ROUND(s.{column}, 2) AS SkyWest
FROM personal p LEFT JOIN skywest s ON s.month = p.month
ORDER BY p.month
"""


MONTHLY_SQL = WITH + """
SELECT p.month AS Month, p.trips AS Trips,
       ROUND(p.cr_dp, 2)   AS [Credit/DP],     ROUND(s.cr_dp, 2)   AS [Credit/DP SkyWest],
       ROUND(p.cr_day, 2)  AS [Credit/day],    ROUND(s.cr_day, 2)  AS [Credit/day SkyWest],
       ROUND(o.cr_day, 2)  AS [Credit/day ORD],
       ROUND(p.bk_dp, 2)   AS [Block/DP],      ROUND(s.bk_dp, 2)   AS [Block/DP SkyWest],
       ROUND(p.bk_day, 2)  AS [Block/day],     ROUND(s.bk_day, 2)  AS [Block/day SkyWest],
       ROUND(p.tafb_bk, 2) AS [TAFB/block],    ROUND(s.tafb_bk, 2) AS [TAFB/block SkyWest],
       ROUND(p.tafb_cr, 2) AS [TAFB/credit],   ROUND(s.tafb_cr, 2) AS [TAFB/credit SkyWest],
       ROUND(p.duty_bk, 2) AS [Duty/block],    ROUND(s.duty_bk, 2) AS [Duty/block SkyWest],
       ROUND(p.duty_cr, 2) AS [Duty/credit],   ROUND(s.duty_cr, 2) AS [Duty/credit SkyWest]
FROM personal p
LEFT JOIN skywest s ON s.month = p.month
LEFT JOIN ord o ON o.month = p.month
ORDER BY p.month DESC
"""

TRIP_DETAIL_SQL = WITH + """
SELECT trip AS Trip, month AS Month, days AS Days, dps AS DPs,
       ROUND(credit, 2) AS Credit, ROUND(block, 2) AS Block,
       ROUND(tafb, 1) AS TAFB, ROUND(duty, 1) AS Duty,
       ROUND(credit / dps, 2) AS [Credit/DP], ROUND(credit / days, 2) AS [Credit/day],
       ROUND(tafb / credit, 2) AS [TAFB/credit], ROUND(duty / credit, 2) AS [Duty/credit]
FROM flown ORDER BY start DESC
"""

RSR_SQL = """
SELECT Data_Month AS Month, Scope, Fleet,
       ROUND(Cr_per_DP, 2) AS [Credit/DP], ROUND(Cr_per_Day, 2) AS [Credit/day],
       ROUND(Bk_per_DP, 2) AS [Block/DP], ROUND(Bk_per_Day, 2) AS [Block/day],
       ROUND(TAFB_per_Bk, 2) AS [TAFB/block], ROUND(TAFB_per_Cr, 2) AS [TAFB/credit],
       ROUND(Duty_per_Bk, 2) AS [Duty/block], ROUND(Duty_per_Cr, 2) AS [Duty/credit]
FROM RSR_Metrics
WHERE Fleet IN ('CRJ200', 'CRJ550', 'CRJ7&9')
ORDER BY Data_Month DESC, Scope, Fleet
"""

LINE = {"graph.dimensions": ["Month"], "graph.metrics": ["Personal", "SkyWest"]}
LINE_ORD = {"graph.dimensions": ["Month"],
            "graph.metrics": ["Personal", "SkyWest", "ORD"]}

# (name, sql, display, viz, (row, col, width, height)); the header takes rows 0-3
CARDS = [
    ("Personal vs SkyWest", OVERALL_SQL, "table", {}, (4, 0, 16, 9)),
    ("Trips in View", WITH + "SELECT COUNT(*) FROM flown", "scalar", {}, (4, 16, 8, 4)),
    ("Credit in View", WITH + "SELECT ROUND(SUM(credit), 1) FROM flown", "scalar",
     {"scalar.suffix": " h"}, (8, 16, 8, 5)),
    ("Credit per Day by Month", CR_DAY_CHART_SQL, "line", LINE_ORD, (13, 0, 12, 6)),
    ("Credit per Duty Period by Month", chart_sql("cr_dp"), "line", LINE, (13, 12, 12, 6)),
    ("TAFB per Credit by Month", chart_sql("tafb_cr"), "line", LINE, (19, 0, 12, 6)),
    ("Duty per Credit by Month", chart_sql("duty_cr"), "line", LINE, (19, 12, 12, 6)),
    ("Monthly Comparison", MONTHLY_SQL, "table", {}, (25, 0, 24, 7)),
    ("Trip Detail", TRIP_DETAIL_SQL, "table", {}, (32, 0, 24, 9)),
    ("SkyWest RSR by Month", RSR_SQL, "table", {}, (41, 0, 24, 8)),
    # Freshness tiles: small strip at the very bottom
    ("Eff: Last Update", TS_SQL, "scalar", {}, (49, 0, 6, 2)),
    ("Eff: Last Sync", SYNC_SQL, "scalar", {}, (49, 6, 6, 2)),
]
DASHCARD_TITLE = {"Eff: Last Update": FRESHNESS_TITLES[0],
                  "Eff: Last Sync": FRESHNESS_TITLES[1]}


def main():
    mb = Metabase()
    mb.login()
    db_id = get_logbook_db_id(mb)
    coll_id = ensure_collection(mb)

    # Re-running replaces the cards: archive the old ones with the same names.
    names = {card[0] for card in CARDS}
    for item in mb.get(f"/api/collection/{coll_id}/items?models=card")["data"]:
        if item["name"] in names:
            mb.put(f"/api/card/{item['id']}", {"archived": True})

    dash_id = next(d["id"] for d in mb.get("/api/dashboard")
                   if d["name"] == DASHBOARD_NAME and not d.get("archived"))

    header = {"id": -100, "card_id": None, "row": 0, "col": 0, "size_x": 24, "size_y": 4,
              "visualization_settings": {
                  "virtual_card": {"name": None, "display": "text",
                                   "visualization_settings": {},
                                   "dataset_query": {}, "archived": False},
                  "text": HEADER}}
    dashcards = [header]
    for i, (name, sql, display, viz, (row, col, width, height)) in enumerate(CARDS):
        if display == "scalar":
            viz = {"scalar.compact_primary_number": False, **viz}
        card = mb.native_card(name, sql, display=display, viz=viz,
                              collection_id=coll_id, database_id=db_id)
        print(f"  card {card['id']:>3}  {name}")
        dashcards.append({"id": -(i + 1), "card_id": card["id"], "row": row, "col": col,
                          "size_x": width, "size_y": height,
                          "visualization_settings":
                              {"card.title": DASHCARD_TITLE[name]}
                              if name in DASHCARD_TITLE else {}})

    mb.put(f"/api/dashboard/{dash_id}", {"parameters": [], "dashcards": dashcards})
    print(f"dashboard '{DASHBOARD_NAME}' (id {dash_id}): {len(CARDS)} cards")


if __name__ == "__main__":
    main()
