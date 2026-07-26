"""Stage-2 provisioning: the "Daily Ops" dashboard (cards + layout) via the
Metabase API. Idempotent: deletes + recreates the dashboard's cards on re-run
(cards are looked up by name inside the Logbook collection).

Data semantics (see README):
- Legacy_Summary=1 rows are pre-airline career aggregates: INCLUDED in career
  totals, EXCLUDED from monthly trends and current-month tiles.
- Monthly airline-ops trend filters Operation='Part 121'.
- Formula/rollup values (Total_Landing, Actual_*, Trip_Credit_Index,
  Flight_Month, Trip_Month, *_from_Aircraft) are materialized by Grist in the
  synced SQLite — used as-is, never recomputed.

Usage: python3 scripts/provision_daily_ops.py
"""
from mb import Metabase

DASHBOARD_NAME = "Daily Ops"

CUR_MONTH = ("Flight_Date >= strftime('%s', date('now','start of month')) "
             "AND Flight_Date < strftime('%s', date('now','start of month','+1 month')) "
             "AND Legacy_Summary = 0")

# "Last Update" tile: sync time stamped into logbook.db by sync-grist.sh
# (sync_meta.synced_at, epoch UTC) -> 'HHMMZ | DD MMM YYYY'
TS_SQL = (
    "SELECT strftime('%H%M', synced_at, 'unixepoch') || 'Z | ' || "
    "strftime('%d', synced_at, 'unixepoch') || ' ' || "
    "CASE strftime('%m', synced_at, 'unixepoch') "
    "WHEN '01' THEN 'Jan' WHEN '02' THEN 'Feb' WHEN '03' THEN 'Mar' "
    "WHEN '04' THEN 'Apr' WHEN '05' THEN 'May' WHEN '06' THEN 'Jun' "
    "WHEN '07' THEN 'Jul' WHEN '08' THEN 'Aug' WHEN '09' THEN 'Sep' "
    "WHEN '10' THEN 'Oct' WHEN '11' THEN 'Nov' WHEN '12' THEN 'Dec' END "
    "|| ' ' || strftime('%Y', synced_at, 'unixepoch') "
    "FROM sync_meta ORDER BY synced_at DESC LIMIT 1")

# (name, sql, display, viz)
CARDS = [
    ("Ops: Last Update", TS_SQL, "scalar", {}),
    # -- career totals (all ops, legacy INCLUDED) --
    ("Career: Total Time", "SELECT ROUND(SUM(Block_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: PIC", "SELECT ROUND(SUM(PIC_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: SIC", "SELECT ROUND(SUM(SIC_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: Night", "SELECT ROUND(SUM(Night_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: Instrument", "SELECT ROUND(SUM(Instrument_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: Cross Country", "SELECT ROUND(SUM(Cross_Country_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: Credit", "SELECT ROUND(SUM(Credit_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("Career: Landings", "SELECT CAST(SUM(Total_Landing) AS INT) FROM Flights", "scalar", {}),
    ("Career: Flights", "SELECT COUNT(*) FROM Flights", "scalar", {}),

    # -- current calendar month (rolls over automatically; legacy excluded) --
    ("This Month: Block", f"SELECT ROUND(COALESCE(SUM(Block_Time),0),1) FROM Flights WHERE {CUR_MONTH}", "scalar", {"scalar.suffix": " h"}),
    ("This Month: Credit", f"SELECT ROUND(COALESCE(SUM(Credit_Time),0),1) FROM Flights WHERE {CUR_MONTH}", "scalar", {"scalar.suffix": " h"}),
    ("This Month: Flights", f"SELECT COUNT(*) FROM Flights WHERE {CUR_MONTH}", "scalar", {}),
    ("This Month: Landings", f"SELECT CAST(COALESCE(SUM(Total_Landing),0) AS INT) FROM Flights WHERE {CUR_MONTH}", "scalar", {}),

    # -- trends --
    ("Monthly Block & Credit (Part 121)",
     "SELECT Flight_Month AS Month, ROUND(SUM(Block_Time),1) AS Block, "
     "ROUND(SUM(Credit_Time),1) AS Credit FROM Flights "
     "WHERE Operation = 'Part 121' AND Legacy_Summary = 0 "
     "GROUP BY Flight_Month ORDER BY Flight_Month",
     "bar", {"graph.dimensions": ["Month"], "graph.metrics": ["Block", "Credit"]}),

    ("Planned vs Actual Block by Month",
     "SELECT Trip_Month AS Month, ROUND(SUM(Planned_Block),1) AS Planned, "
     "ROUND(SUM(Actual_Block),1) AS Actual FROM Trips "
     "GROUP BY Trip_Month ORDER BY Trip_Month",
     "bar", {"graph.dimensions": ["Month"], "graph.metrics": ["Planned", "Actual"]}),

    ("Planned vs Actual Credit by Month",
     "SELECT Trip_Month AS Month, ROUND(SUM(Planned_Credit),1) AS Planned, "
     "ROUND(SUM(Actual_Credit),1) AS Actual FROM Trips "
     "GROUP BY Trip_Month ORDER BY Trip_Month",
     "bar", {"graph.dimensions": ["Month"], "graph.metrics": ["Planned", "Actual"]}),

    ("Avg Trip Credit Index by Month",
     "SELECT Trip_Month AS Month, ROUND(AVG(Trip_Credit_Index),3) AS [Avg TCI] "
     "FROM Trips WHERE Trip_Credit_Index IS NOT NULL "
     "GROUP BY Trip_Month ORDER BY Trip_Month",
     "line", {"graph.dimensions": ["Month"], "graph.metrics": ["Avg TCI"]}),

    ("Avg TAFB by Month",
     "SELECT Trip_Month AS Month, ROUND(AVG(TAFB),1) AS [Avg TAFB (h)] "
     "FROM Trips WHERE TAFB IS NOT NULL "
     "GROUP BY Trip_Month ORDER BY Trip_Month",
     "line", {"graph.dimensions": ["Month"], "graph.metrics": ["Avg TAFB (h)"]}),

    # -- pivots (career scope: all ops, legacy included) --
    ("Block by Category x Position",
     "SELECT Category_from_Aircraft AS Category, "
     "ROUND(SUM(CASE WHEN Flight_Position='PIC' THEN Block_Time ELSE 0 END),1) AS PIC, "
     "ROUND(SUM(CASE WHEN Flight_Position='SIC' THEN Block_Time ELSE 0 END),1) AS SIC, "
     "ROUND(SUM(Block_Time),1) AS Total FROM Flights "
     "WHERE Category_from_Aircraft IS NOT NULL GROUP BY 1 ORDER BY Total DESC",
     "table", {}),

    ("Block by Class x Position",
     "SELECT Class_from_Aircraft AS Class, "
     "ROUND(SUM(CASE WHEN Flight_Position='PIC' THEN Block_Time ELSE 0 END),1) AS PIC, "
     "ROUND(SUM(CASE WHEN Flight_Position='SIC' THEN Block_Time ELSE 0 END),1) AS SIC, "
     "ROUND(SUM(Block_Time),1) AS Total FROM Flights "
     "WHERE Class_from_Aircraft IS NOT NULL GROUP BY 1 ORDER BY Total DESC",
     "table", {}),

    ("Block by Engine x Position",
     "SELECT Engine_Category_from_Aircraft AS Engine, "
     "ROUND(SUM(CASE WHEN Flight_Position='PIC' THEN Block_Time ELSE 0 END),1) AS PIC, "
     "ROUND(SUM(CASE WHEN Flight_Position='SIC' THEN Block_Time ELSE 0 END),1) AS SIC, "
     "ROUND(SUM(Block_Time),1) AS Total FROM Flights "
     "WHERE Engine_Category_from_Aircraft IS NOT NULL GROUP BY 1 ORDER BY Total DESC",
     "table", {}),
]

# Dashboard layout: 24-column grid. (card name -> row, col, size_x, size_y)
# Row 0 = the Last Update strip; everything else starts at row 3.
LAYOUT = {"Ops: Last Update": (0, 0, 8, 3)}
# career tiles: 9 scalars, 2 rows
for i, n in enumerate(["Career: Total Time", "Career: PIC", "Career: SIC",
                       "Career: Night", "Career: Instrument"]):
    LAYOUT[n] = (3, i * 5 if i < 4 else 20, 4 if i == 4 else 5, 3)
for i, n in enumerate(["Career: Cross Country", "Career: Credit",
                       "Career: Landings", "Career: Flights"]):
    LAYOUT[n] = (6, i * 6, 6, 3)
for i, n in enumerate(["This Month: Block", "This Month: Credit",
                       "This Month: Flights", "This Month: Landings"]):
    LAYOUT[n] = (9, i * 6, 6, 3)
LAYOUT["Monthly Block & Credit (Part 121)"] = (12, 0, 24, 6)
LAYOUT["Planned vs Actual Block by Month"] = (18, 0, 12, 6)
LAYOUT["Planned vs Actual Credit by Month"] = (18, 12, 12, 6)
LAYOUT["Avg Trip Credit Index by Month"] = (24, 0, 12, 6)
LAYOUT["Avg TAFB by Month"] = (24, 12, 12, 6)
LAYOUT["Block by Category x Position"] = (30, 0, 8, 6)
LAYOUT["Block by Class x Position"] = (30, 8, 8, 6)
LAYOUT["Block by Engine x Position"] = (30, 16, 8, 6)

# Per-card dashcard visualization overrides (e.g. displayed title)
DASHCARD_VIZ = {"Ops: Last Update": {"card.title": "Last Update"}}


def get_logbook_db_id(mb):
    dbs = mb.get("/api/database")["data"]
    return next(d["id"] for d in dbs if d["name"] == "Logbook")


def ensure_collection(mb, name="Logbook"):
    cols = mb.get("/api/collection")
    for c in cols:
        if c.get("name") == name and not c.get("archived"):
            return c["id"]
    return mb.post("/api/collection", {"name": name})["id"]


def ensure_dashboard(mb, name, collection_id):
    existing = mb.get("/api/dashboard")
    items = existing if isinstance(existing, list) else existing.get("data", [])
    for d in items:
        if d["name"] == name and not d.get("archived"):
            return d["id"]
    return mb.post("/api/dashboard",
                   {"name": name, "collection_id": collection_id})["id"]


def archive_cards_by_name(mb, collection_id, names):
    items = mb.get(f"/api/collection/{collection_id}/items?models=card")
    for it in items.get("data", []):
        if it["name"] in names:
            mb.put(f"/api/card/{it['id']}", {"archived": True})


def provision(mb, cards, layout, dash_name, db_id, coll_id, dashcard_viz=None):
    archive_cards_by_name(mb, coll_id, {c[0] for c in cards})
    dash_id = ensure_dashboard(mb, dash_name, coll_id)

    made = {}
    for name, sql, display, viz in cards:
        card = mb.native_card(name, sql, display=display, viz=viz,
                              collection_id=coll_id, database_id=db_id)
        made[name] = card["id"]
        print(f"  card {card['id']:>3}  {name}")

    dashcards = []
    for i, (name, *_rest) in enumerate(cards):
        r, c, sx, sy = layout[name]
        dashcards.append({"id": -(i + 1), "card_id": made[name],
                          "row": r, "col": c, "size_x": sx, "size_y": sy,
                          "visualization_settings":
                              (dashcard_viz or {}).get(name, {})})
    mb.put(f"/api/dashboard/{dash_id}", {"dashcards": dashcards})
    print(f"dashboard '{dash_name}' (id {dash_id}) laid out "
          f"with {len(dashcards)} cards")
    return dash_id, made


def main():
    mb = Metabase()
    mb.login()
    db_id = get_logbook_db_id(mb)
    coll_id = ensure_collection(mb)
    dash_id, _ = provision(mb, CARDS, LAYOUT, DASHBOARD_NAME, db_id, coll_id,
                           dashcard_viz=DASHCARD_VIZ)
    # make Daily Ops the landing page
    mb.put("/api/setting/custom-homepage", {"value": True})
    mb.put("/api/setting/custom-homepage-dashboard", {"value": dash_id})
    print(f"homepage set to dashboard {dash_id}")


if __name__ == "__main__":
    main()
