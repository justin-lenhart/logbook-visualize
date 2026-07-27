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
| Monthly Block & Credit (Part 121) | http://100.78.241.102:3000/public/question/5c538a75-8644-406b-856d-bb5e3a567e10 |
| Planned vs Actual Block by Month | http://100.78.241.102:3000/public/question/5832b6a8-3cbb-4398-9090-351e2f1b17fc |
| Planned vs Actual Credit by Month | http://100.78.241.102:3000/public/question/e3ee1fed-dd81-46e5-abf0-c333a5321dda |
| Avg Trip Credit Index by Month | http://100.78.241.102:3000/public/question/fac25306-f7f5-48a5-80bf-7e3578e9c2db |
| Avg TAFB by Month | http://100.78.241.102:3000/public/question/04a0dd0e-86c8-4eda-bae2-57d766448431 |
| Block by Category x Position | http://100.78.241.102:3000/public/question/0cf3e879-78d0-4e87-8b16-8d7a3d6ab6ec |
| Block by Class x Position | http://100.78.241.102:3000/public/question/c6186c5f-56fb-4816-9956-53b22972dc58 |
| Block by Engine x Position | http://100.78.241.102:3000/public/question/3836d86c-2db8-4a3e-91e1-1e82dd3ae000 |
