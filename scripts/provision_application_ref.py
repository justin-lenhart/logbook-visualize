"""Stage-3 provisioning: the "Application Reference" dashboard — replicates
the derivable parts of the public gh-pages app sheets
(justin-lenhart.github.io/logbook/apps/{ual,swa,faa,summary}.html).

Built: per-aircraft totals + last-flown, headline numbers, FAA 8710
category matrix, class hours table (PIC / SIC / dual received / total),
currency-by-recency buckets, and three total-reconciliation checks.
NOT built (underivable from Grist — see README "GAPS"): military sortie
counts, x0.3 sortie conversions, type-rated flags, manufacturer/model
splits, milestone targets, SWA custom category buckets.

Usage: python3 scripts/provision_application_ref.py
"""
from mb import Metabase
from provision_daily_ops import (get_logbook_db_id, ensure_collection,
                                 provision, archive_cards_by_name, TS_SQL,
                                 SYNC_SQL, FRESHNESS_TITLES)

DASHBOARD_NAME = "Application Reference"

# Cards renamed in a later version; archived so they do not linger in the collection.
RETIRED_CARDS = {"Totals by Aircraft", "Class Hours (PIC / SIC)"}

# Applications ask for hours per FAA type (CL65, H1...), not per subtype
# (CR2/CR5/CR7/CR9...). Subtypes flown are listed for reference.
SUBTYPES_FLOWN = ("(SELECT GROUP_CONCAT(x, ', ') FROM (SELECT b.Aircraft AS x FROM Aircraft b "
                  "WHERE b.FAA_Type = a.FAA_Type AND EXISTS "
                  "(SELECT 1 FROM Flights g WHERE g.Aircraft = b.id) ORDER BY b.Aircraft))")

AIRPLANE = "Category = 'Airplane'"
FW_TURB = f"{AIRPLANE} AND Engine_Category_from_Aircraft = 'Turbine'"

MONTHS_AGO = ("(CAST(strftime('%Y','now') AS INT)*12 + CAST(strftime('%m','now') AS INT)) - "
              "(CAST(strftime('%Y', Flight_Date,'unixepoch') AS INT)*12 + "
              "CAST(strftime('%m', Flight_Date,'unixepoch') AS INT))")


def _8710_row(ord_, label, expr):
    return (f"SELECT {ord_} AS ord, '{label}' AS Metric, "
            f"ROUND(SUM(CASE WHEN Category='Airplane' THEN {expr} ELSE 0 END),1) AS Airplane, "
            f"ROUND(SUM(CASE WHEN Category='Helicopter' THEN {expr} ELSE 0 END),1) AS Rotorcraft, "
            f"ROUND(SUM(CASE WHEN Category='Powered Lift' THEN {expr} ELSE 0 END),1) AS [Powered Lift] "
            f"FROM Flights")


FAA_8710_SQL = " UNION ALL ".join([
    _8710_row(1, "Total Hours", "Block_Time"),
    _8710_row(2, "Instruction Received", "Dual_Received"),
    _8710_row(3, "Pilot in Command (PIC)", "PIC_Time"),
    _8710_row(4, "Second in Command (SIC)", "SIC_Time"),
    _8710_row(5, "Instructor (Dual Given)", "Dual_Given"),
    _8710_row(6, "Cross Country", "Cross_Country_Time"),
    _8710_row(7, "Instrument", "Instrument_Time"),
    _8710_row(8, "Night", "Night_Time"),
    _8710_row(9, "Night Takeoff/Landings", "Night_Landing"),
    _8710_row(10, "Night T/O Landing PIC",
              "CASE WHEN Flight_Position='PIC' THEN Night_Landing ELSE 0 END"),
    _8710_row(11, "Night T/O Landing SIC",
              "CASE WHEN Flight_Position='SIC' THEN Night_Landing ELSE 0 END"),
]) + " ORDER BY ord"

HIDE_ORD = {"table.columns": [
    {"name": "ord", "enabled": False},
    {"name": "Metric", "enabled": True},
    {"name": "Airplane", "enabled": True},
    {"name": "Rotorcraft", "enabled": True},
    {"name": "Powered Lift", "enabled": True},
]}

# Class table: PIC + SIC + Dual Recv = Total on every row, and the airplane
# classes sum to the 8710 Airplane "Total Hours" (every flight row satisfies
# PIC_Time + SIC_Time + Dual_Received = Block_Time).
_CLASSES = [("ASEL", "Category='Airplane' AND Class='Single-Engine Land'"),
            ("AMEL", "Category='Airplane' AND Class='Multi-Engine Land'"),
            ("Helicopter", "Class='Rotorcraft'"),
            ("Powered Lift", "Category='Powered Lift'")]
_CLASS_COLS = [("PIC", "PIC_Time"), ("SIC", "SIC_Time"),
               ("Dual Recv", "Dual_Received"), ("Total", "Block_Time")]
CLASS_SQL = " UNION ALL ".join(
    f"SELECT {i} AS ord, '{label}' AS Class, " + ", ".join(
        f"ROUND(SUM(CASE WHEN {cond} THEN {col} ELSE 0 END),1) AS [{alias}]"
        for alias, col in _CLASS_COLS) + " FROM Flights"
    for i, (label, cond) in enumerate(_CLASSES, 1)) + " ORDER BY ord"

# Integrity checks: grand total = sum of categories = sum of FAA types.
# A flight with no Aircraft link has a null Category/Class and drops out of
# every grouped card while still counting in Total Time. All three must read 0.
CHECK_CATEGORY_SQL = ("SELECT ROUND(SUM(Block_Time) - SUM(CASE WHEN Category IS NOT NULL "
                      "THEN Block_Time ELSE 0 END),1) FROM Flights")
CHECK_TYPE_SQL = ("SELECT ROUND((SELECT SUM(Block_Time) FROM Flights) - "
                  "(SELECT SUM(f.Block_Time) FROM Flights f JOIN Aircraft a "
                  "ON f.Aircraft = a.id WHERE a.FAA_Type IS NOT NULL AND a.FAA_Type <> ''),1)")
CHECK_NO_AIRCRAFT_SQL = ("SELECT COUNT(*) FROM Flights WHERE COALESCE(Deadhead,0) = 0 "
                         "AND (Aircraft IS NULL OR Aircraft = 0)")

# Recency buckets count CALENDAR months back from the current month (0 = this
# month). The first three are cumulative and overlap: "0-3 mo" = this month
# plus the three before it, and so on; from 13-24 on the buckets are disjoint.
BUCKETS = [("0-3 mo", 0, 3), ("0-6 mo", 0, 6), ("0-12 mo", 0, 12), ("13-24", 13, 24), ("25-36", 25, 36),
           ("37-48", 37, 48), ("49-60", 49, 60)]
_bucket_cols = ", ".join(
    f"ROUND(SUM(CASE WHEN {MONTHS_AGO} BETWEEN {lo} AND {hi} "
    f"THEN f.Block_Time ELSE 0 END),1) AS [{label}]"
    for label, lo, hi in BUCKETS)

CARDS = [
    ("App: Last Update", TS_SQL, "scalar", {}),
    ("App: Last Sync", SYNC_SQL, "scalar", {}),
    ("App: Total Time", "SELECT ROUND(SUM(Block_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("App: Total PIC", "SELECT ROUND(SUM(PIC_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("App: Airplane", f"SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE {AIRPLANE}", "scalar", {"scalar.suffix": " h"}),
    ("App: Rotorcraft", "SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE Class = 'Rotorcraft'", "scalar", {"scalar.suffix": " h"}),
    ("App: Fixed-Wing Turbine", f"SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE {FW_TURB}", "scalar", {"scalar.suffix": " h"}),
    ("App: Fixed-Wing Turbine PIC", f"SELECT ROUND(SUM(PIC_Time),1) FROM Flights WHERE {FW_TURB}", "scalar", {"scalar.suffix": " h"}),
    ("App: Turbine (All Categories)", "SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE Engine_Category_from_Aircraft = 'Turbine'", "scalar", {"scalar.suffix": " h"}),

    ("Totals by FAA Type",
     f"SELECT a.FAA_Type AS [FAA Type], {SUBTYPES_FLOWN} AS Subtypes, "
     "MAX(a.Category) AS Category, MAX(a.Class) AS Class, "
     "MAX(a.Engine_Category) AS Engine, "
     "COALESCE(ROUND(SUM(f.Block_Time),1),0) AS Total, "
     "COALESCE(ROUND(SUM(f.PIC_Time),1),0) AS PIC, "
     "COALESCE(ROUND(SUM(f.SIC_Time),1),0) AS SIC, "
     "COALESCE(ROUND(SUM(f.Dual_Given),1),0) AS Instructor, "
     "COALESCE(ROUND(SUM(f.Dual_Received),1),0) AS [Instr Recv], "
     "COALESCE(ROUND(SUM(f.Night_Time),1),0) AS Night, "
     "COALESCE(ROUND(SUM(f.Instrument_Time),1),0) AS Instrument, "
     "COALESCE(ROUND(SUM(f.Cross_Country_Time),1),0) AS XC, "
     "CAST(SUM(f.Total_Landing) AS INT) AS Ldgs, "
     "MAX(date(f.Flight_Date,'unixepoch')) AS [Last Flown] "
     "FROM Flights f JOIN Aircraft a ON f.Aircraft = a.id "
     "GROUP BY a.FAA_Type ORDER BY Total DESC",
     "table", {}),

    ("FAA 8710 — Hours by Category", FAA_8710_SQL, "table", HIDE_ORD),

    ("Class Hours", CLASS_SQL, "table", {"table.columns": [
        {"name": "ord", "enabled": False},
        {"name": "Class", "enabled": True},
        {"name": "PIC", "enabled": True},
        {"name": "SIC", "enabled": True},
        {"name": "Dual Recv", "enabled": True},
        {"name": "Total", "enabled": True}]}),

    ("Check: Total minus Categories", CHECK_CATEGORY_SQL, "scalar", {"scalar.suffix": " h"}),
    ("Check: Total minus FAA Types", CHECK_TYPE_SQL, "scalar", {"scalar.suffix": " h"}),
    ("Check: Flights Missing Aircraft", CHECK_NO_AIRCRAFT_SQL, "scalar", {}),

    # TOTAL row is part of the result set (UNION ALL) so it always renders
    # with the table; the hidden sortkey pins it to the top by default.
    ("Currency — Block Hours by Recency",
     "SELECT a.FAA_Type AS [FAA Type], " + _bucket_cols + ", "
     f"ROUND(SUM(CASE WHEN {MONTHS_AGO} > 60 THEN f.Block_Time ELSE 0 END),1) AS Older, "
     "MAX(f.Flight_Date) AS sortkey "
     "FROM Flights f JOIN Aircraft a ON f.Aircraft = a.id GROUP BY a.FAA_Type "
     "UNION ALL SELECT 'TOTAL', " + _bucket_cols + ", "
     f"ROUND(SUM(CASE WHEN {MONTHS_AGO} > 60 THEN f.Block_Time ELSE 0 END),1), "
     "9999999999 FROM Flights f "
     "ORDER BY sortkey DESC",
     "table", {"table.columns": [
         {"name": "FAA Type", "enabled": True},
         {"name": "0-3 mo", "enabled": True},
         {"name": "0-6 mo", "enabled": True},
         {"name": "0-12 mo", "enabled": True},
         {"name": "13-24", "enabled": True},
         {"name": "25-36", "enabled": True},
         {"name": "37-48", "enabled": True},
         {"name": "49-60", "enabled": True},
         {"name": "Older", "enabled": True},
         {"name": "sortkey", "enabled": False}]}),
]

LAYOUT = {
    "App: Total Time": (0, 0, 6, 3),
    "App: Total PIC": (0, 6, 6, 3),
    "App: Airplane": (0, 12, 6, 3),
    "App: Rotorcraft": (0, 18, 6, 3),
    "App: Fixed-Wing Turbine": (3, 0, 8, 3),
    "App: Fixed-Wing Turbine PIC": (3, 8, 8, 3),
    "App: Turbine (All Categories)": (3, 16, 8, 3),
    "Totals by FAA Type": (6, 0, 24, 9),
    "FAA 8710 — Hours by Category": (15, 0, 12, 9),
    "Class Hours": (15, 12, 12, 9),
    "Currency — Block Hours by Recency": (24, 0, 24, 9),
    # Last Update: small strip at the very bottom (small tile = small text)
    "App: Last Update": (33, 0, 6, 2),
    "App: Last Sync": (33, 6, 6, 2),
    # Integrity checks below: each must read 0
    "Check: Total minus Categories": (35, 0, 8, 2),
    "Check: Total minus FAA Types": (35, 8, 8, 2),
    "Check: Flights Missing Aircraft": (35, 16, 8, 2),
}

DASHCARD_VIZ = {
    "App: Last Update": {"card.title": FRESHNESS_TITLES[0]},
    "App: Last Sync": {"card.title": FRESHNESS_TITLES[1]},
    "Check: Total minus Categories": {"card.title": "Check: Total − Categories (must be 0)"},
    "Check: Total minus FAA Types": {"card.title": "Check: Total − FAA Types (must be 0)"},
    "Check: Flights Missing Aircraft": {"card.title": "Check: Flights w/o Aircraft (must be 0)"},
}


def main():
    mb = Metabase()
    mb.login()
    db_id = get_logbook_db_id(mb)
    coll_id = ensure_collection(mb)
    archive_cards_by_name(mb, coll_id, RETIRED_CARDS)
    provision(mb, CARDS, LAYOUT, DASHBOARD_NAME, db_id, coll_id,
              dashcard_viz=DASHCARD_VIZ)


if __name__ == "__main__":
    main()
