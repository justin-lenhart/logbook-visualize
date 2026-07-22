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
| Monthly Block & Credit (Part 121) | http://100.78.241.102:3000/public/question/3ecb77aa-c28e-45a5-b47c-027ceefc7692 |
| Planned vs Actual Block by Month | http://100.78.241.102:3000/public/question/978c58b3-3862-4f97-8a3b-5cbcfe1e8448 |
| Planned vs Actual Credit by Month | http://100.78.241.102:3000/public/question/89111bb6-6b89-4f17-a6d8-92a592bc70f4 |
| Avg Trip Credit Index by Month | http://100.78.241.102:3000/public/question/63a52ea4-a568-4d11-9501-079e3de19062 |
| Avg TAFB by Month | http://100.78.241.102:3000/public/question/a05c3066-757c-4949-adba-c6f94a9509e3 |
| Block by Category x Position | http://100.78.241.102:3000/public/question/e68d5f10-5d47-417b-b7d9-260bf9fa36b7 |
| Block by Class x Position | http://100.78.241.102:3000/public/question/f8b70385-6f78-4ef4-b3e4-4689243b47fd |
| Block by Engine x Position | http://100.78.241.102:3000/public/question/9a29f26e-a762-45ea-a52f-88df4f61efab |
