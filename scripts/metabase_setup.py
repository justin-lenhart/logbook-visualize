"""Stage-1 provisioning: complete Metabase first-run setup via API and add the
logbook SQLite datasource. Idempotent — safe to re-run.

Usage: python3 scripts/metabase_setup.py
"""
import sys
import time
from mb import Metabase, ENV

LOGBOOK_DB_PATH = "/logbook/logbook.db"  # path inside the container (ro mount)


def main():
    mb = Metabase()
    print("waiting for Metabase health...")
    if not mb.wait_healthy():
        print("FATAL: Metabase never became healthy")
        sys.exit(1)

    props = mb.get("/api/session/properties")
    token = props.get("setup-token")
    if token:
        print("running first-time setup...")
        r = mb.post("/api/setup", {
            "token": token,
            "user": {
                "email": ENV["MB_ADMIN_EMAIL"],
                "password": ENV["MB_ADMIN_PASSWORD"],
                "first_name": "Justin",
                "last_name": "Lenhart",
                "site_name": "Logbook",
            },
            "prefs": {
                "site_name": "Logbook",
                "allow_tracking": False,
            },
        })
        mb.session = r.get("id")
        if not mb.session:
            mb.login()
        print("setup complete, admin created")
    else:
        print("already set up — logging in")
        mb.login()

    dbs = mb.get("/api/database")
    existing = [d for d in dbs["data"] if d["name"] == "Logbook"]
    if existing:
        db_id = existing[0]["id"]
        print(f"datasource already present (id {db_id})")
    else:
        db = mb.post("/api/database", {
            "engine": "sqlite",
            "name": "Logbook",
            "details": {"db": LOGBOOK_DB_PATH},
            "is_full_sync": True,
        })
        db_id = db["id"]
        print(f"datasource created (id {db_id})")

    mb.post(f"/api/database/{db_id}/sync_schema")
    print("schema sync triggered; waiting for tables...")
    for _ in range(30):
        meta = mb.get(f"/api/database/{db_id}/metadata")
        tables = {t["name"] for t in meta.get("tables", [])}
        if {"Flights", "Trips", "Duty_Periods", "Aircraft"} <= tables:
            print(f"tables synced: {sorted(tables)}")
            return
        time.sleep(5)
    print("WARNING: tables not all visible yet; check Metabase admin")


if __name__ == "__main__":
    main()
