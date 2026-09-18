#!/usr/bin/env bash
# logbook-visualize: sync the Grist Logbook doc to a plain SQLite copy for Metabase.
#
# STRICTLY read-only toward Grist: the live .grist file is opened read-only
# (SQLite URI mode=ro) and copied with the SQLite Online Backup API — the same
# mechanism as the sqlite3 CLI's ".backup" command (the CLI is not installed on
# mintbox, so Python's stdlib sqlite3.Connection.backup is used instead).
#
# Pipeline: live .grist --(online backup)--> temp copy --(prune to scope
# tables, vacuum)--> --(online backup in place)--> ~/docker/metabase/db/logbook.db
# The final in-place backup preserves the destination inode so Metabase's
# bind-mounted view of the file never goes stale.
#
# Scope tables kept: Flights, Trips, Duty_Periods, Aircraft, RSR_Metrics (SkyWest
# RSR system averages) and Bid_Months (Line/Reserve label per month). Airports and
# all Grist metadata/summary tables are dropped from the copy — never the source.
#
# Cron: one line in mint's crontab runs this every 15 minutes.
set -euo pipefail

GRIST_DOC="/srv/data/appdata/grist/docs/$(cat /home/mint/Developer/homelab/migration/grist-doc.txt).grist"
DEST_DIR="/srv/data/appdata/metabase/db"
DEST="$DEST_DIR/logbook.db"
LOG="/srv/data/appdata/metabase/sync.log"
TMP="$DEST_DIR/.sync-tmp.db"

mkdir -p "$DEST_DIR"
# Keep the log from growing forever: truncate when > 200 lines.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 200 ]; then
  tail -n 100 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

python3 - "$GRIST_DOC" "$TMP" "$DEST" <<'PYEOF' >> "$LOG" 2>&1
import sqlite3, sys, os, time

src_path, tmp_path, dest_path = sys.argv[1], sys.argv[2], sys.argv[3]
KEEP = {"Flights", "Trips", "Duty_Periods", "Aircraft", "RSR_Metrics", "Bid_Months"}
stamp = time.strftime("%Y-%m-%d %H:%M:%S")

try:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # 1. Online backup of the live doc (opened READ-ONLY) to a temp copy.
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    tmp = sqlite3.connect(tmp_path)
    src.backup(tmp)
    src.close()

    # 2. Prune the COPY down to the scope tables; drop views/indexes on
    #    dropped tables too, then vacuum.
    names = [r[0] for r in tmp.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for name in names:
        if name not in KEEP and not name.startswith("sqlite_"):
            tmp.execute(f'DROP TABLE IF EXISTS "{name}"')
    tmp.commit()
    tmp.execute("VACUUM")

    # Stamp the sync time into the copy (feeds the dashboards' "Last
    # Update" tiles; epoch seconds, UTC).
    tmp.execute("CREATE TABLE IF NOT EXISTS sync_meta (synced_at INTEGER)")
    tmp.execute("DELETE FROM sync_meta")
    tmp.execute("INSERT INTO sync_meta VALUES (?)", (int(time.time()),))
    tmp.commit()

    counts = {t: tmp.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
              for t in sorted(KEEP)}

    # 3. In-place online backup temp -> destination (preserves dest inode,
    #    so the container's bind mount stays valid).
    dest = sqlite3.connect(dest_path)
    tmp.backup(dest)
    dest.close()
    tmp.close()
    os.remove(tmp_path)
    print(f"{stamp} OK {counts}")
except Exception as e:
    print(f"{stamp} FAIL {type(e).__name__}: {e}")
    sys.exit(1)
PYEOF
