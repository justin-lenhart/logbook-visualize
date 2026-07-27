# Metabase public embed URLs (for Grist integration)

Public sharing is enabled so Grist pages can embed Metabase views
(Custom-URL widgets). These links carry no auth — but Metabase binds to
the **Tailscale IP only**, so they are reachable exclusively on the
Tailnet; the bind is the security boundary (same model as Grist itself).

Regenerate with `python3 scripts/enable_embeds.py` (idempotent — UUIDs
are stable once created).

| View | Public URL |
|------|-----------|
| Daily Ops (full dashboard) | http://100.78.241.102:3000/public/dashboard/ec389b81-d929-4043-8223-5194efbe6735 |
| Application Reference (full dashboard) | http://100.78.241.102:3000/public/dashboard/cb050317-8fe5-4e01-9ea8-c4b47ce38c9c |
| Monthly Block & Credit (Part 121) | http://100.78.241.102:3000/public/question/1ecf691b-9e8b-4c61-9ff0-7e54dd461ece |
| Planned vs Actual Block by Month | http://100.78.241.102:3000/public/question/3a765dd7-5a98-4c1b-bc0d-a7a7bcd6a578 |
| Planned vs Actual Credit by Month | http://100.78.241.102:3000/public/question/b0c9bfd4-74e8-43a7-8005-2c3c06ec233f |
| Avg Trip Credit Index by Month | http://100.78.241.102:3000/public/question/afa7dbeb-3b88-4ec1-a59e-7a0fb2b4674d |
| Avg TAFB by Month | http://100.78.241.102:3000/public/question/4381c1be-33e2-4733-b32e-0938a5333c66 |
| Block by Category x Position | http://100.78.241.102:3000/public/question/89fda222-07dc-40d5-a927-f8a5eaa3d7dc |
| Block by Class x Position | http://100.78.241.102:3000/public/question/4135512c-4a1c-4bd4-bcb2-a7e509e61f05 |
| Block by Engine x Position | http://100.78.241.102:3000/public/question/2fb730e0-5d0b-4034-8400-2e588c606e20 |
