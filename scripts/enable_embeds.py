"""Enable Metabase public sharing and create public links for Grist embeds.

Creates public links for both dashboards plus each individual Daily Ops
chart card (so Grist pages can compose them widget-by-widget), and writes
the URL table to embed-urls.md. Idempotent: re-running returns the same
UUIDs (Metabase keeps a public link once made).

Touches ONLY the `enable-public-sharing` setting — nothing else.

Usage: python3 scripts/enable_embeds.py
"""
import os

from mb import Metabase, BASE, REPO_ROOT

DASHBOARDS = ["Daily Ops", "Application Reference",
              "Trip Efficiency & Duty Legality"]
CHART_CARDS = [
    "Monthly Block & Credit (Part 121)",
    "Planned vs Actual Block by Month",
    "Planned vs Actual Credit by Month",
    "Avg Trip Credit Index by Month",
    "Avg TAFB by Month",
    "Block by Category x Position",
    "Block by Class x Position",
    "Block by Engine x Position",
]

HEADER = """\
# Metabase public embed URLs (for Grist integration)

Public sharing is enabled so Grist pages can embed Metabase views
(Custom-URL widgets). These links carry no auth — but Metabase binds to
the **Tailscale IP only**, so they are reachable exclusively on the
Tailnet; the bind is the security boundary (same model as Grist itself).

Regenerate with `python3 scripts/enable_embeds.py` (idempotent — UUIDs
are stable once created).

| View | Public URL |
|------|-----------|
"""


def main():
    mb = Metabase()
    mb.login()

    mb.put("/api/setting/enable-public-sharing", {"value": True})
    print("enable-public-sharing = true")

    rows = []

    dashes = mb.get("/api/dashboard")
    items = dashes if isinstance(dashes, list) else dashes.get("data", [])
    by_name = {d["name"]: d["id"] for d in items if not d.get("archived")}
    for name in DASHBOARDS:
        r = mb.post(f"/api/dashboard/{by_name[name]}/public_link")
        url = f"{BASE}/public/dashboard/{r['uuid']}"
        rows.append((f"{name} (full dashboard)", url))
        print(f"dashboard {name}: {url}")

    coll = next(c["id"] for c in mb.get("/api/collection")
                if c.get("name") == "Logbook" and not c.get("archived"))
    cards = {it["name"]: it["id"] for it in
             mb.get(f"/api/collection/{coll}/items?models=card")["data"]}
    for name in CHART_CARDS:
        r = mb.post(f"/api/card/{cards[name]}/public_link")
        url = f"{BASE}/public/question/{r['uuid']}"
        rows.append((name, url))
        print(f"card {name}: {url}")

    out = os.path.join(REPO_ROOT, "embed-urls.md")
    with open(out, "w") as f:
        f.write(HEADER)
        for name, url in rows:
            f.write(f"| {name} | {url} |\n")
    print(f"\n{len(rows)} links -> {out}")


if __name__ == "__main__":
    main()
