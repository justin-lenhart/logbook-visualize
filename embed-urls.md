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
| Monthly Block & Credit (Part 121) | http://100.78.241.102:3000/public/question/fd642d8c-0203-477b-ac6f-53497d287171 |
| Planned vs Actual Block by Month | http://100.78.241.102:3000/public/question/5b82105a-2572-43f4-9dc3-6b76a04bdc07 |
| Planned vs Actual Credit by Month | http://100.78.241.102:3000/public/question/dd03238a-1174-4e31-ac94-9c3556a02514 |
| Avg Trip Credit Index by Month | http://100.78.241.102:3000/public/question/9cd3bf16-1c30-49bf-87dd-2461f626cc64 |
| Avg TAFB by Month | http://100.78.241.102:3000/public/question/3c05fc89-8e80-4fcd-8463-f028c32b0337 |
| Block by Category x Position | http://100.78.241.102:3000/public/question/39f43609-20e3-4d43-8231-9397ab98afac |
| Block by Class x Position | http://100.78.241.102:3000/public/question/cafa3658-e785-40e5-af47-7462e7d7cb6d |
| Block by Engine x Position | http://100.78.241.102:3000/public/question/a7f3b433-2fd5-4db4-ad77-5923eb22a83b |
