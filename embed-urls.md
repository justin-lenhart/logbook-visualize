# Metabase public embed URLs (for Grist integration)

Public sharing is enabled so Grist pages can embed Metabase views
(Custom-URL widgets). These links carry no auth — but Metabase binds to
the **Tailscale IP only**, so they are reachable exclusively on the
Tailnet; the bind is the security boundary (same model as Grist itself).

Regenerate with `python3 scripts/enable_embeds.py` (idempotent — UUIDs
are stable once created).

| View | Public URL |
|------|-----------|
| Daily Ops (full dashboard) | http://100.78.232.7:3000/public/dashboard/ec389b81-d929-4043-8223-5194efbe6735 |
| Application Reference (full dashboard) | http://100.78.232.7:3000/public/dashboard/cb050317-8fe5-4e01-9ea8-c4b47ce38c9c |
| Trip Efficiency & Duty Legality (full dashboard) | http://100.78.232.7:3000/public/dashboard/4b676242-0cd5-4c08-a260-32d476e6d93e |
| Efficiency (full dashboard) | http://100.78.232.7:3000/public/dashboard/a6cc7e9e-e057-42c6-b966-69d4633cad4d |
| Monthly Block & Credit (Part 121) | http://100.78.232.7:3000/public/question/b878e653-a60e-4c25-b197-853fa72d02c2 |
| Planned vs Actual Block by Month | http://100.78.232.7:3000/public/question/1f83f4e0-0618-4a0b-8f38-e8d8ab9da600 |
| Planned vs Actual Credit by Month | http://100.78.232.7:3000/public/question/d8404b18-9ea8-4bdb-8adc-7c4848d72c68 |
| Avg TAFB by Month | http://100.78.232.7:3000/public/question/336c3557-84a3-4b53-8db9-afa0596b7c1d |
| Block by Category x Position | http://100.78.232.7:3000/public/question/691373b8-c1c7-4aca-b9eb-edef4c38dfd5 |
| Block by Class x Position | http://100.78.232.7:3000/public/question/3bca96e9-0723-459b-973d-ce4198d33ec9 |
| Block by Engine x Position | http://100.78.232.7:3000/public/question/2e2f4b1f-5631-4795-b7fd-2f8306cf4de2 |
