#!/usr/bin/env bash
# logbook-visualize: sync the Grist Logbook doc to a plain SQLite copy for Metabase.
#
# STRICTLY read-only toward Grist: the live .grist file is opened read-only
# (SQLite URI mode=ro) and copied with the SQLite Online Backup API — the same
# mechanism as the sqlite3 CLI's ".backup" command (the CLI is not installed on
# crushbox, so Python's stdlib sqlite3.Connection.backup is used instead).
#
# Pipeline: live .grist --(online backup)--> temp copy --(prune to scope
# tables, vacuum)--> --(online backup in place)--> /srv/appdata/metabase/db/logbook.db
# The final in-place backup preserves the destination inode so Metabase's
# bind-mounted view of the file never goes stale.
#
# Scope tables kept: Flights, Trips, Duty_Periods, Aircraft, RSR_Metrics (SkyWest
# RSR averages). Airports and all Grist metadata/summary tables are dropped from
# the copy — never the source.
#
# Cron: one line in crushbox's crontab runs this every 15 minutes.
set -euo pipefail

GRIST_DOC="/srv/appdata/grist/docs/$(cat /srv/homelab/migration/grist-doc.txt).grist"
DEST_DIR="/srv/appdata/metabase/db"
DEST="$DEST_DIR/logbook.db"
LOG="/srv/appdata/metabase/sync.log"
TMP="$DEST_DIR/.sync-tmp.db"

mkdir -p "$DEST_DIR"
# Keep the log from growing forever: truncate when > 200 lines.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 200 ]; then
  tail -n 100 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

python3 - "$GRIST_DOC" "$TMP" "$DEST" <<'PYEOF' >> "$LOG" 2>&1
import marshal, sqlite3, sys, os, time

src_path, tmp_path, dest_path = sys.argv[1], sys.argv[2], sys.argv[3]
KEEP = {"Flights", "Trips", "Duty_Periods", "Aircraft", "RSR_Metrics"}
stamp = time.strftime("%Y-%m-%d %H:%M:%S")



def last_data_change(conn):
    """Epoch seconds (UTC) of the newest Grist action that touched a user
    table, read from the doc's action history. Layout-only actions (column
    widths, view settings: tables named _grist_*) are skipped, so the result
    is when the DATA last changed. None if it cannot be determined."""
    try:
        for (body,) in conn.execute(
                "SELECT body FROM _gristsys_ActionHistory ORDER BY id DESC LIMIT 500"):
            action = marshal.loads(body)
            for ua in action.get("userActions", []):
                if (len(ua) > 1 and isinstance(ua[1], str)
                        and not ua[1].startswith("_grist")):
                    return int(action["info"][1]["time"] / 1000)
    except Exception as e:
        print(f"{stamp} WARN last_data_change: {type(e).__name__}: {e}")
    return None


try:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # 1. Online backup of the live doc (opened READ-ONLY) to a temp copy.
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    tmp = sqlite3.connect(tmp_path)
    src.backup(tmp)
    data_changed_at = last_data_change(src)
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

    # Stamp freshness into the copy (feeds the dashboards' "Data Last
    # Changed" and "Last Sync" tiles; epoch seconds, UTC): when the Grist
    # data last changed, and when this copy was taken.
    tmp.execute("DROP TABLE IF EXISTS sync_meta")
    tmp.execute("CREATE TABLE sync_meta (synced_at INTEGER, data_changed_at INTEGER)")
    tmp.execute("INSERT INTO sync_meta VALUES (?, ?)",
                (int(time.time()), data_changed_at))
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
