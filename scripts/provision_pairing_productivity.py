"""Stage-2 provisioning: the "Pairing Productivity" dashboard — the user's
flown trips vs SkyWest RSR system-wide averages (Grist RSR_Metrics).

Definitions (match the RSR report):
- Every ratio is a SUM over SUM across the trips in view — never an average of
  per-trip ratios.
- Credit = Trips.Actual_Credit (sum of SkedPlus Day Totals, which matches the
  crew pay report on most trips); Block = Trips.Actual_Block; TAFB = Trips.TAFB.
- Days = Trips.Trip_Length (calendar days); DP = Duty_Periods with
  Status 'Actual'; Duty = SUM(release - report) of those duty periods.
- Fleet = the RSR bucket (CRJ200 / CRJ550 / CRJ7&9) with the most
  non-deadhead block on the trip. 700 and 900 share one RSR bucket.
- Line type comes from the hand-kept Grist table Bid_Months (Line / Reserve).
- System = the RSR system value for each trip's month and fleet, averaged
  over the trips in view (trip-weighted), so it always describes the same
  months and fleets as "You".
- Index > 1.00 always means better than the system: You / System for
  higher-is-better metrics, System / You for lower-is-better ones.

Idempotent: archives same-name cards, reuses the dashboard (and its public
link). Usage: python3 scripts/provision_pairing_productivity.py
"""
import uuid

from mb import Metabase
from provision_daily_ops import ensure_collection, get_logbook_db_id

DASHBOARD_NAME = "Pairing Productivity"

FLEET_CASE = ("CASE a.Aircraft WHEN 'CR2' THEN 'CRJ200' WHEN 'CR5' THEN 'CRJ550' "
              "WHEN 'CR7' THEN 'CRJ7&9' WHEN 'CR9' THEN 'CRJ7&9' END")

# (label, better, your SUM/SUM expression, RSR_Metrics column)
METRICS = [
    ("Credit / duty period", "Higher", "SUM(cr) / SUM(dps)", "Cr_per_DP"),
    ("Credit / day", "Higher", "SUM(cr) / SUM(days)", "Cr_per_Day"),
    ("Block / duty period", "Higher", "SUM(bk) / SUM(dps)", "Bk_per_DP"),
    ("Block / day", "Higher", "SUM(bk) / SUM(days)", "Bk_per_Day"),
    ("TAFB / block", "Lower", "SUM(tafb) / SUM(bk)", "TAFB_per_Bk"),
    ("TAFB / credit", "Lower", "SUM(tafb) / SUM(cr)", "TAFB_per_Cr"),
    ("Duty / block", "Lower", "SUM(duty) / SUM(bk)", "Duty_per_Bk"),
    ("Duty / credit", "Lower", "SUM(duty) / SUM(cr)", "Duty_per_Cr"),
]
RSR_COLS = ", ".join(f"r.{m[3]}" for m in METRICS)

TRIPS_CTE = f"""WITH fl AS (
  SELECT f.Trips AS trip, {FLEET_CASE} AS fleet, SUM(f.Block_Time) AS blk
  FROM Flights f JOIN Aircraft a ON a.id = f.Aircraft
  WHERE f.Trips > 0 AND COALESCE(f.Deadhead, 0) = 0
  GROUP BY 1, 2),
fleet_of AS (
  SELECT trip, fleet FROM (
    SELECT trip, fleet,
           ROW_NUMBER() OVER (PARTITION BY trip ORDER BY blk DESC, fleet) AS rn
    FROM fl WHERE fleet IS NOT NULL)
  WHERE rn = 1),
dp AS (
  SELECT Trips AS trip, COUNT(*) AS dps,
         SUM((Release_Time - Report_Time) / 3600.0) AS duty
  FROM Duty_Periods WHERE Status = 'Actual' GROUP BY 1),
ts AS (
  SELECT t.id, t.Trip_Key AS trip_key, t.Trip_Month AS month, t.Base AS base,
         fo.fleet AS fleet, COALESCE(bm.Line_Type, 'Unlabeled') AS line_type,
         t.Actual_Credit AS cr, t.Actual_Block AS bk, t.TAFB AS tafb,
         t.Trip_Length AS days, dp.dps AS dps, dp.duty AS duty,
         t.Start_Date AS start_date
  FROM Trips t
  JOIN dp ON dp.trip = t.id
  LEFT JOIN fleet_of fo ON fo.trip = t.id
  LEFT JOIN Bid_Months bm ON bm.Month = t.Trip_Month
  WHERE t.Status = 'Actual' AND t.TAFB > 0),
f AS (
  SELECT * FROM ts WHERE 1 = 1
  [[AND line_type = {{{{line_type}}}}]]
  [[AND fleet = {{{{fleet}}}}]]
  [[AND base = {{{{base}}}}]]),
fr AS (
  SELECT f.*, {RSR_COLS}
  FROM f LEFT JOIN RSR_Metrics r
    ON r.Scope = 'SYS' AND r.Fleet = f.fleet AND r.Data_Month = f.month)
"""
TRIP_TAGS = ("line_type", "fleet", "base")


def you_vs_system_sql():
    agg = ", ".join(
        [f"{expr} AS y{i}, AVG({col}) AS s{i}"
         for i, (_l, _b, expr, col) in enumerate(METRICS)])
    rows = []
    for i, (label, better, _e, _c) in enumerate(METRICS):
        index = f"y{i} / s{i}" if better == "Higher" else f"s{i} / y{i}"
        rows.append(
            f"SELECT '{label}' AS Metric, '{better}' AS [Better], "
            f"ROUND(y{i}, 2) AS You, ROUND(s{i}, 2) AS [SkyWest system], "
            f"ROUND({index}, 2) AS [Index] FROM agg")
    return (f"{TRIPS_CTE}, agg AS (SELECT {agg} FROM fr)\n"
            + "\nUNION ALL\n".join(rows))


def monthly_chart_sql(i):
    _label, _better, expr, col = METRICS[i]
    return (f"{TRIPS_CTE}SELECT month AS Month, ROUND({expr}, 2) AS You, "
            f"ROUND(AVG({col}), 2) AS [SkyWest system] "
            "FROM fr GROUP BY month ORDER BY month")


def monthly_table_sql():
    cols = ", ".join(
        f"ROUND({expr}, 2) AS [{label} (you)], ROUND(AVG({col}), 2) AS [{label} (sys)]"
        for label, _b, expr, col in METRICS)
    return (f"{TRIPS_CTE}SELECT month AS Month, "
            "GROUP_CONCAT(DISTINCT line_type) AS [Line type], COUNT(*) AS Trips, "
            f"GROUP_CONCAT(DISTINCT fleet) AS Fleets, {cols} "
            "FROM fr GROUP BY month ORDER BY month DESC")


TRIP_DETAIL_SQL = (
    f"{TRIPS_CTE}SELECT trip_key AS Trip, month AS Month, line_type AS [Line type], "
    "base AS Base, fleet AS Fleet, days AS Days, dps AS DPs, "
    "ROUND(cr, 2) AS [Credit h], ROUND(bk, 2) AS [Block h], ROUND(tafb, 1) AS [TAFB h], "
    "ROUND(duty, 1) AS [Duty h], "
    "ROUND(cr / dps, 2) AS [Credit/DP], ROUND(cr / days, 2) AS [Credit/day], "
    "ROUND(tafb / cr, 2) AS [TAFB/credit], ROUND(TAFB_per_Cr, 2) AS [TAFB/credit (sys)], "
    "ROUND(duty / cr, 2) AS [Duty/credit], ROUND(Duty_per_Cr, 2) AS [Duty/credit (sys)] "
    "FROM fr ORDER BY start_date DESC")

RSR_REFERENCE_SQL = (
    "SELECT Data_Month AS Month, Fleet, "
    + ", ".join(f"ROUND({col}, 2) AS [{label}]" for label, _b, _e, col in METRICS)
    + ", Report_Month AS [From report] FROM RSR_Metrics "
    "WHERE Scope = 'SYS' [[AND Fleet = {{fleet}}]] ORDER BY Data_Month DESC, Fleet")

LINE = {"graph.dimensions": ["Month"], "graph.metrics": ["You", "SkyWest system"]}

# (name, sql, display, viz, template tags)
CARDS = [
    (Personal vs SkyWest", you_vs_system_sql(), "table", {}, TRIP_TAGS),
    ("Trips in View", f"{TRIPS_CTE}SELECT COUNT(*) FROM fr", "scalar", {}, TRIP_TAGS),
    ("Credit in View", f"{TRIPS_CTE}SELECT ROUND(SUM(cr), 1) FROM fr", "scalar",
     {"scalar.suffix": " h"}, TRIP_TAGS),
    ("Credit per Day by Month", monthly_chart_sql(1), "line", LINE, TRIP_TAGS),
    ("Credit per Duty Period by Month", monthly_chart_sql(0), "line", LINE, TRIP_TAGS),
    ("TAFB per Credit by Month", monthly_chart_sql(5), "line", LINE, TRIP_TAGS),
    ("Duty per Credit by Month", monthly_chart_sql(7), "line", LINE, TRIP_TAGS),
    ("Monthly Comparison", monthly_table_sql(), "table", {}, TRIP_TAGS),
    ("Trip Detail", TRIP_DETAIL_SQL, "table", {}, TRIP_TAGS),
    ("SkyWest RSR by Month", RSR_REFERENCE_SQL, "table", {}, ("fleet",)),
]

TAG_DEFS = {"line_type": "Line Type", "fleet": "Fleet", "base": "Base"}

# Hidden helper card: feeds the Base dropdown from the trips themselves, so a
# new base appears without editing this script. Not placed on the dashboard.
BASE_VALUES_CARD = ("PP: Base Values",
                    "SELECT DISTINCT Base FROM Trips WHERE Base IS NOT NULL "
                    "AND Base != '' ORDER BY Base")


def parameters(base_card_id):
    """Dropdown filters ("list" widgets) instead of free-text boxes."""
    def dropdown(pid, name, slug, source):
        return {"id": pid, "name": name, "slug": slug, "type": "string/=",
                "sectionId": "string", "values_query_type": "list", **source}
    return [
        dropdown("p-linetype", "Line Type", "line_type",
                 {"values_source_type": "static-list",
                  "values_source_config": {"values": ["Line", "Reserve", "Unlabeled"]}}),
        dropdown("p-fleet", "Fleet", "fleet",
                 {"values_source_type": "static-list",
                  "values_source_config": {"values": ["CRJ200", "CRJ550", "CRJ7&9"]}}),
        dropdown("p-base", "Base", "base",
                 {"values_source_type": "card",
                  "values_source_config": {
                      "card_id": base_card_id,
                      "value_field": ["field", "Base", {"base-type": "type/Text"}]}}),
    ]


PARAM_FOR_TAG = {"line_type": "p-linetype", "fleet": "p-fleet", "base": "p-base"}

HEADER = (
    "**Efficiency Metrics: Flown trips vs SkyWest RSR averages.** "
    ".*SkyWest* metrics are system-wide RSR values averaged across "
    "CRJ fleet. **Index = personal / system** Index > 1.00 for "
    "'higher' metrics --> better than system. Inverse for 'lower'"
    "metrics.")

# (row, col, size_x, size_y); the header text card takes rows 0-4
LAYOUT = {
    "Personal vs SkyWest ": (5, 0, 16, 9),
    "Trips in View": (5, 16, 8, 4),
    "Credit in View": (9, 16, 8, 5),
    "Credit per Day by Month": (14, 0, 12, 6),
    "Credit per Duty Period by Month": (14, 12, 12, 6),
    "TAFB per Credit by Month": (20, 0, 12, 6),
    "Duty per Credit by Month": (20, 12, 12, 6),
    "Monthly Comparison": (26, 0, 24, 7),
    "Trip Detail": (33, 0, 24, 9),
    "SkyWest RSR by Month": (42, 0, 24, 8),
}


def make_card(mb, name, sql, display, viz, tags, db_id, coll_id):
    template_tags = {
        tag: {"id": str(uuid.uuid4()), "name": tag, "display-name": TAG_DEFS[tag],
              "type": "text", "required": False}
        for tag in tags}
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

    names = {c[0] for c in CARDS} | {BASE_VALUES_CARD[0]}
    for it in mb.get(f"/api/collection/{coll_id}/items?models=card").get("data", []):
        if it["name"] in names:
            mb.put(f"/api/card/{it['id']}", {"archived": True})

    dashes = mb.get("/api/dashboard")
    dl = dashes if isinstance(dashes, list) else dashes.get("data", [])
    dash_id = next((d["id"] for d in dl
                    if d["name"] == DASHBOARD_NAME and not d.get("archived")), None)
    if dash_id is None:
        dash_id = mb.post("/api/dashboard", {
            "name": DASHBOARD_NAME, "collection_id": coll_id})["id"]

    base_card = make_card(mb, *BASE_VALUES_CARD, "table", {}, (), db_id, coll_id)["id"]
    made = {}
    for name, sql, display, viz, tags in CARDS:
        made[name] = make_card(mb, name, sql, display, viz, tags, db_id, coll_id)["id"]
        print(f"  card {made[name]:>3}  {name}")

    dashcards = [{
        "id": -1000, "card_id": None, "row": 0, "col": 0, "size_x": 24, "size_y": 5,
        "parameter_mappings": [],
        "visualization_settings": {
            "virtual_card": {"name": None, "display": "text",
                             "visualization_settings": {},
                             "dataset_query": {}, "archived": False},
            "text": HEADER},
    }]
    for i, (name, _sql, _display, _viz, tags) in enumerate(CARDS):
        r, c, sx, sy = LAYOUT[name]
        dashcards.append({
            "id": -(i + 1), "card_id": made[name],
            "row": r, "col": c, "size_x": sx, "size_y": sy,
            "parameter_mappings": [
                {"parameter_id": PARAM_FOR_TAG[t], "card_id": made[name],
                 "target": ["variable", ["template-tag", t]]}
                for t in tags],
            # card names carry a "PP: " prefix to stay unique in the shared
            # collection; the dashboard shows them without it
            "visualization_settings": {"card.title": name.removeprefix("PP: ")},
        })

    mb.put(f"/api/dashboard/{dash_id}",
           {"parameters": parameters(base_card), "dashcards": dashcards})
    print(f"dashboard '{DASHBOARD_NAME}' (id {dash_id}): "
          f"{len(dashcards)} dashcards (incl. header), 3 dropdown filters")


if __name__ == "__main__":
    main()
