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
| Trip Efficiency & Duty Legality (full dashboard) | http://100.78.241.102:3000/public/dashboard/4b676242-0cd5-4c08-a260-32d476e6d93e |
| Pairing Productivity (full dashboard) | http://100.78.241.102:3000/public/dashboard/a6cc7e9e-e057-42c6-b966-69d4633cad4d |
| Monthly Block & Credit (Part 121) | http://100.78.241.102:3000/public/question/cf63f27c-469f-4b41-ab00-f742b602304c |
| Planned vs Actual Block by Month | http://100.78.241.102:3000/public/question/17218dfb-102b-45af-bcc1-648000bf3287 |
| Planned vs Actual Credit by Month | http://100.78.241.102:3000/public/question/272e12ce-cd99-4039-93f2-300cf62fd5e3 |
| Avg TAFB by Month | http://100.78.241.102:3000/public/question/9e44dad0-8188-4249-aa8e-0d57eca28bd6 |
| Block by Category x Position | http://100.78.241.102:3000/public/question/7d0728b4-0785-49a5-917f-50e80c6fe354 |
| Block by Class x Position | http://100.78.241.102:3000/public/question/3ab5934e-a409-44c9-85f2-434e5bca96a3 |
| Block by Engine x Position | http://100.78.241.102:3000/public/question/58283d25-9ccc-4207-97e3-e6dbe30cc04a |
