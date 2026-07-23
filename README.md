# logbook-visualize

Metabase dashboards over the self-hosted Grist pilot logbook on mintbox.
Grist stays the single source of truth (pure backend); Metabase is a
read-only, prettier frontend.

## Status — BETA (2026-07-22)

Functional and fully verified, not yet aesthetically polished. Active
branch: **`metabase-build`** (local only); `main` is the initial stub and
the target of the eventual merge once the user blesses the beta.

This is the visualization half of the larger logbook system (end state:
SkedPlus → automatic import into Grist + this frontend serving daily ops
and **airline applications**; the import half lives in the `logbook` repo,
branch `logbook-grist` — that repo's `distribute`/`enhanced-map` branches
are deprecated). System-level roadmap: `~/Developer/homelab/TODO.md`
("🎯 End state" section).

Toward 1.0 from here:
- **Aesthetic pass** — theming/branding, tile sizing, number formatting,
  chart colors (Metabase appearance settings are admin-UI or
  enterprise-API territory; the free tier still allows layout + viz
  polish per card).
- **Close the schema gaps** (below) so the Application Reference
  dashboard can fully replace the gh-pages app sheets — each needs a
  USER-approved Grist schema addition; never invent the numbers.
- **Currency/recency extras** as flying picks up: rolling 30/60/90-day
  tiles, landings currency (61.57), IFR currency inputs if approaches/
  holds get logged consistently.

**URL: <http://100.78.241.102:3000>** (Tailscale-only bind, like Grist).
Login: `whoostie@gmail.com`; the admin password lives on mintbox in the
gitignored **`~/Developer/logbook-visualize/.env`** (`MB_ADMIN_PASSWORD`,
chmod 600 — never committed, never printed). The landing page is the
**Daily Ops** dashboard; **Application Reference** is the second dashboard
(both in the *Logbook* collection).

## Architecture

```
Grist doc (live)                       Metabase container
~/docker/grist/docs/<docId>.grist      metabase/metabase:latest
        │  read-only                   bound to 100.78.241.102:3000
        │  SQLite online backup        app data: ~/docker/metabase/data
        ▼  (cron, */15)                heap capped at 1 GB
~/docker/metabase/db/logbook.db  ──►   mounted read-only at /logbook
(plain SQLite: Flights, Trips,         datasource "Logbook" (SQLite)
 Duty_Periods, Aircraft only)
```

- **`sync-grist.sh`** (cron `*/15`, single crontab line commented
  `# logbook-visualize sync`) opens the live `.grist` file **read-only**
  (SQLite URI `mode=ro`) and copies it with the SQLite **Online Backup
  API** — the same mechanism as the `sqlite3` CLI's `.backup` command.
  (The `sqlite3` CLI is not installed on mintbox and installing needs
  sudo, so the script uses Python's stdlib `sqlite3.Connection.backup`.)
  The copy is pruned to the four scope tables (Airports and all
  `_grist_*`/summary tables are dropped **from the copy only**), then
  written into the destination with a second in-place backup so the
  file's inode never changes under the container's bind mount.
  Log: `~/docker/metabase/sync.log` (self-truncating).
- Grist is **never written to** — no API writes, no schema changes, no
  helper columns were added.
- Grist formula/rollup values (`Total_Landing`, `Actual_*`,
  `Trip_Credit_Index`, `Flight_Month`, `Trip_Month`, `*_from_Aircraft`,
  Aircraft hour rollups) are **materialized** in the SQLite file — all
  cards use them as-is and never recompute them.

## Data semantics

- `Legacy_Summary = true` flights are pre-airline **career aggregate
  rows**: included in career/application totals, **excluded** from
  monthly trends and current-month tiles.
- Monthly airline-ops trend filters `Operation = 'Part 121'`.
- `Dual_Given` = instructor time; `Dual_Received` = instruction received.
- Dates are epoch seconds (UTC); month bucketing uses the materialized
  `Flight_Month` / `Trip_Month` Grist helper columns where possible.

## Dashboards

**Daily Ops** (homepage, 21 cards): career tiles (total / PIC / SIC /
night / instrument / XC / credit / landings / flights — legacy included),
current-calendar-month tiles (auto-rolling `date('now','start of month')`
SQL — equivalent to a relative-date filter, chosen so the cards stay
native-SQL and verifiable), monthly block+credit trend (Part 121, legacy
excluded), planned-vs-actual block and credit by month, avg Trip Credit
Index and avg TAFB by month, and Category / Class / Engine × Position
block-hour pivots.

**Application Reference** (11 cards): headline numbers (total, PIC,
airplane, rotorcraft, fixed-wing turbine, FW-turbine PIC, all-turbine),
per-aircraft totals with instructor time and last-flown, FAA 8710
hours-by-category matrix (incl. night T/O landings split PIC/SIC), class
hours PIC/SIC (ASEL / AMEL / Helicopter / Powered Lift), and
currency-by-recency block-hour buckets (0–12 / 13–24 / 25–36 / 37–48 /
49–60 / older months).

## Verification

Every card is recomputed **independently from the live Grist REST API**
(not the synced SQLite) with tolerance 0.1 — see
[`verification-report.md`](verification-report.md). Current status:
**32/32 cards match** (21 Daily Ops + 11 Application Reference).
Stage-1 plumbing check: Metabase `Flights` row count == live Grist row
count (134 at build time).

Note: the static gh-pages app sheets were generated 2026-06-21; numbers
here are live and legitimately differ where flights were logged since
(e.g. career total). Verification is always against **live Grist**, not
the static pages.

## GAPS — cells on the app pages that are NOT derivable from Grist

These appear on the public app sheets but have no source column in the
Grist doc. They were **not built** (no numbers invented, no columns added
to Grist). Schema additions that would close each gap are listed.

| Page cell | Why underivable | Schema addition that would fix it |
|-----------|-----------------|-----------------------------------|
| Military sortie counts (swa) | No sortie-count column anywhere; legacy rows aggregate hours only | `Flights.Sorties` (int) on legacy/military rows |
| PIC/SIC/Instr ×0.3 sortie conversions (swa) | Derived from sortie counts (above) | same as above |
| "Type Rated" flags (ual) | Not a column on `Aircraft` | `Aircraft.Type_Rated` (bool) |
| Manufacturer / Model split (ual) | `Aircraft.Aircraft` is a single short code (e.g. `AH-1Z`); no manufacturer column | `Aircraft.Manufacturer`, `Aircraft.Model` (text) |
| Milestone table (summary: 1000 FW-turbine-PIC, 1500 turbine, 1000 FW-turbine) | Milestone *targets* are business constants, not data; only the "have" side is derivable (built as headline scalars) | a small `Milestones` table (name, metric, target) |
| SWA "Aircraft Category Totals" buckets (Jet/Turbine, Military Trainers, Turbo Prop ME, Light Piston, Heli/Power Lift) | Bucket membership is app-specific business logic (e.g. T-6B's *instruction received* counted as SIC) not encoded in any column | `Aircraft.SWA_Bucket` (choice) — plus a decision on the Instr-Recv-as-SIC rule |
| Per-airframe merged rows (TH-57B/C, CRJ-200/700/900 on the pages) | Grist tracks them as separate Aircraft rows; the merge is page cosmetics. Dashboard shows them unmerged (honest, still verifiable) | none needed (could group by `FAA_Type` if merging is wanted) |

## How to rebuild from scratch

```bash
cd ~/Developer/logbook-visualize
cp .env.example .env        # set MB_ADMIN_PASSWORD (generate one), TS_IP
./sync-grist.sh             # first copy of logbook.db
docker compose up -d        # Metabase on http://100.78.241.102:3000
python3 scripts/metabase_setup.py           # first-run setup + datasource
python3 scripts/provision_daily_ops.py      # Daily Ops + homepage
python3 scripts/provision_application_ref.py
python3 scripts/verify_daily_ops.py         # both write verification-report.md
python3 scripts/verify_application_ref.py
printf '%s\n' '*/15 * * * * /home/mint/Developer/logbook-visualize/sync-grist.sh # logbook-visualize sync' | crontab -
```

All provisioning is idempotent (cards are archived and recreated by name;
dashboards updated in place). Everything uses the Python stdlib — no pip
installs needed on mintbox.

## Grist embedding (live since 2026-07-23)

Both dashboards are embedded into the Grist doc as pages, via Custom-URL
widgets pointing at the public links in [`embed-urls.md`](embed-urls.md)
(with `#bordered=false&titled=false` for clean iframes):

- Grist page **"Analytics (Metabase)"** → Daily Ops dashboard
- Grist page **"Application Reference"** → Application Reference dashboard

The embeds render the live dashboards — **any appearance/content edit made
in Metabase auto-reflects in the Grist pages** (same URL, no re-embed
needed). Per-card public links also exist in `embed-urls.md` if Grist
pages ever want to compose individual charts widget-by-widget.

## Operations

- Sync cadence: every 15 min (`crontab -l` → the `# logbook-visualize sync`
  line). New Grist edits appear in Metabase within 15 min; force with
  `./sync-grist.sh`.
- Metabase app data lives in `~/docker/metabase/data` (H2). The synced
  SQLite is `~/docker/metabase/db/logbook.db` — disposable, rebuilt every
  sync.
- Container: `docker compose ps` in this repo; JVM heap capped at 1 GB
  (mintbox has 7.4 GB shared with the media stack).
