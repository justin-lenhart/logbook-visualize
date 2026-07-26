"""Stage-3 provisioning: the "Application Reference" dashboard — replicates
the derivable parts of the public gh-pages app sheets
(justin-lenhart.github.io/logbook/apps/{ual,swa,faa,summary}.html).

Built: per-aircraft totals + last-flown, headline numbers, FAA 8710
category matrix, class PIC/SIC table, currency-by-recency buckets.
NOT built (underivable from Grist — see README "GAPS"): military sortie
counts, x0.3 sortie conversions, type-rated flags, manufacturer/model
splits, milestone targets, SWA custom category buckets.

Usage: python3 scripts/provision_application_ref.py
"""
from mb import Metabase
from provision_daily_ops import (get_logbook_db_id, ensure_collection,
                                 provision, TS_SQL)

DASHBOARD_NAME = "Application Reference"

AIRPLANE = "Category_from_Aircraft = 'Airplane'"
FW_TURB = f"{AIRPLANE} AND Engine_Category_from_Aircraft = 'Turbine'"

MONTHS_AGO = ("(CAST(strftime('%Y','now') AS INT)*12 + CAST(strftime('%m','now') AS INT)) - "
              "(CAST(strftime('%Y', Flight_Date,'unixepoch') AS INT)*12 + "
              "CAST(strftime('%m', Flight_Date,'unixepoch') AS INT))")


def _8710_row(ord_, label, expr):
    return (f"SELECT {ord_} AS ord, '{label}' AS Metric, "
            f"ROUND(SUM(CASE WHEN Category_from_Aircraft='Airplane' THEN {expr} ELSE 0 END),1) AS Airplane, "
            f"ROUND(SUM(CASE WHEN Category_from_Aircraft='Helicopter' THEN {expr} ELSE 0 END),1) AS Rotorcraft, "
            f"ROUND(SUM(CASE WHEN Category_from_Aircraft='Powered Lift' THEN {expr} ELSE 0 END),1) AS [Powered Lift] "
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

BUCKETS = [("0-12 mo", 0, 12), ("13-24", 13, 24), ("25-36", 25, 36),
           ("37-48", 37, 48), ("49-60", 49, 60)]
_bucket_cols = ", ".join(
    f"ROUND(SUM(CASE WHEN {MONTHS_AGO} BETWEEN {lo} AND {hi} "
    f"THEN f.Block_Time ELSE 0 END),1) AS [{label}]"
    for label, lo, hi in BUCKETS)

CARDS = [
    ("App: Last Update", TS_SQL, "scalar", {}),
    ("App: Total Time", "SELECT ROUND(SUM(Block_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("App: Total PIC", "SELECT ROUND(SUM(PIC_Time),1) FROM Flights", "scalar", {"scalar.suffix": " h"}),
    ("App: Airplane", f"SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE {AIRPLANE}", "scalar", {"scalar.suffix": " h"}),
    ("App: Rotorcraft", "SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE Class_from_Aircraft = 'Rotorcraft'", "scalar", {"scalar.suffix": " h"}),
    ("App: Fixed-Wing Turbine", f"SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE {FW_TURB}", "scalar", {"scalar.suffix": " h"}),
    ("App: Fixed-Wing Turbine PIC", f"SELECT ROUND(SUM(PIC_Time),1) FROM Flights WHERE {FW_TURB}", "scalar", {"scalar.suffix": " h"}),
    ("App: Turbine (All Categories)", "SELECT ROUND(SUM(Block_Time),1) FROM Flights WHERE Engine_Category_from_Aircraft = 'Turbine'", "scalar", {"scalar.suffix": " h"}),

    ("Totals by Aircraft",
     "SELECT a.Aircraft, a.Category, a.Class, a.Engine_Category AS Engine, "
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
     "GROUP BY a.id ORDER BY Total DESC",
     "table", {}),

    ("FAA 8710 — Hours by Category", FAA_8710_SQL, "table", HIDE_ORD),

    ("Class Hours (PIC / SIC)",
     "SELECT 1 AS ord, 'ASEL' AS Class, "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Airplane' AND Class_from_Aircraft='Single-Engine Land' THEN PIC_Time ELSE 0 END),1) AS PIC, "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Airplane' AND Class_from_Aircraft='Single-Engine Land' THEN SIC_Time ELSE 0 END),1) AS SIC FROM Flights "
     "UNION ALL SELECT 2, 'AMEL', "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Airplane' AND Class_from_Aircraft='Multi-Engine Land' THEN PIC_Time ELSE 0 END),1), "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Airplane' AND Class_from_Aircraft='Multi-Engine Land' THEN SIC_Time ELSE 0 END),1) FROM Flights "
     "UNION ALL SELECT 3, 'Helicopter', "
     "ROUND(SUM(CASE WHEN Class_from_Aircraft='Rotorcraft' THEN PIC_Time ELSE 0 END),1), "
     "ROUND(SUM(CASE WHEN Class_from_Aircraft='Rotorcraft' THEN SIC_Time ELSE 0 END),1) FROM Flights "
     "UNION ALL SELECT 4, 'Powered Lift', "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Powered Lift' THEN PIC_Time ELSE 0 END),1), "
     "ROUND(SUM(CASE WHEN Category_from_Aircraft='Powered Lift' THEN SIC_Time ELSE 0 END),1) FROM Flights "
     "ORDER BY ord",
     "table", {"table.columns": [
         {"name": "ord", "enabled": False},
         {"name": "Class", "enabled": True},
         {"name": "PIC", "enabled": True},
         {"name": "SIC", "enabled": True}]}),

    ("Currency — Block Hours by Recency",
     "SELECT a.Aircraft, " + _bucket_cols + ", "
     f"ROUND(SUM(CASE WHEN {MONTHS_AGO} > 60 THEN f.Block_Time ELSE 0 END),1) AS Older "
     "FROM Flights f JOIN Aircraft a ON f.Aircraft = a.id "
     "GROUP BY a.id ORDER BY MAX(f.Flight_Date) DESC",
     "table", {}),
]

LAYOUT = {
    "App: Total Time": (0, 0, 6, 3),
    "App: Total PIC": (0, 6, 6, 3),
    "App: Airplane": (0, 12, 6, 3),
    "App: Rotorcraft": (0, 18, 6, 3),
    "App: Fixed-Wing Turbine": (3, 0, 8, 3),
    "App: Fixed-Wing Turbine PIC": (3, 8, 8, 3),
    "App: Turbine (All Categories)": (3, 16, 8, 3),
    "Totals by Aircraft": (6, 0, 24, 9),
    "FAA 8710 — Hours by Category": (15, 0, 12, 9),
    "Class Hours (PIC / SIC)": (15, 12, 12, 9),
    "Currency — Block Hours by Recency": (24, 0, 24, 9),
    # Last Update: small strip at the very bottom (small tile = small text)
    "App: Last Update": (33, 0, 6, 2),
}

DASHCARD_VIZ = {"App: Last Update": {"card.title": "Last Update"}}


def main():
    mb = Metabase()
    mb.login()
    db_id = get_logbook_db_id(mb)
    coll_id = ensure_collection(mb)
    provision(mb, CARDS, LAYOUT, DASHBOARD_NAME, db_id, coll_id,
              dashcard_viz=DASHCARD_VIZ)


if __name__ == "__main__":
    main()
