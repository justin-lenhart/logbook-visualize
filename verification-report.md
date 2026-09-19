# Daily Ops verification — 2026-09-18 23:56 UTC

Every card recomputed independently from live Grist REST (tolerance 0.1).

| Card | Result |
|------|--------|
| Career: Total Time | ✅ matches live Grist |
| Career: PIC | ✅ matches live Grist |
| Career: SIC | ✅ matches live Grist |
| Career: Night | ✅ matches live Grist |
| Career: Instrument | ✅ matches live Grist |
| Career: Cross Country | ✅ matches live Grist |
| Career: Credit | ✅ matches live Grist |
| Career: Landings | ✅ matches live Grist |
| Career: Flights | ✅ matches live Grist |
| Passengers Adventured | ✅ matches live Grist |
| This Month: Block | ✅ matches live Grist |
| This Month: Credit | ✅ matches live Grist |
| This Month: Flights | ✅ matches live Grist |
| This Month: Landings | ✅ matches live Grist |
| Monthly Block & Credit (Part 121) | ✅ matches live Grist |
| Planned vs Actual Block by Month | ✅ matches live Grist |
| Planned vs Actual Credit by Month | ✅ matches live Grist |
| Avg TAFB by Month | ✅ matches live Grist |
| Block by Category x Position | ✅ matches live Grist |
| Block by Class x Position | ✅ matches live Grist |
| Block by Engine x Position | ✅ matches live Grist |

**21/21 cards verified.**

# Application Reference verification — 2026-09-18 23:56 UTC

Every card recomputed independently from live Grist REST (tolerance 0.1).

| Card | Result |
|------|--------|
| App: Total Time | ✅ matches live Grist |
| App: Total PIC | ✅ matches live Grist |
| App: Airplane | ✅ matches live Grist |
| App: Rotorcraft | ✅ matches live Grist |
| App: Fixed-Wing Turbine | ✅ matches live Grist |
| App: Fixed-Wing Turbine PIC | ✅ matches live Grist |
| App: Turbine (All Categories) | ✅ matches live Grist |
| Totals by FAA Type | ✅ matches live Grist |
| FAA 8710 — Hours by Category | ✅ matches live Grist |
| Class Hours (PIC / SIC) | ✅ matches live Grist |
| Currency — Block Hours by Recency | ✅ matches live Grist |

**11/11 cards verified.**

# Trip Efficiency & Duty Legality verification — 2026-09-18 23:56 UTC

Every card recomputed independently from live Grist REST (tolerance 0.1; ±0.5 on now-anchored rolling windows). FDP = report→release (conservative proxy); Table A/B shown as floor/ceiling pending local-time data.

| Card | Result |
|------|--------|
| Avg FDP Length (h) | ✅ matches live Grist |
| Avg FDP % of Table B floor 9h (§117.13) | ✅ matches live Grist |
| Avg FDP % of Table B ceiling 14h (§117.13) | ✅ matches live Grist |
| Avg Block per Duty (h) | ✅ matches live Grist |
| Avg Block % of Table A floor 8h (§117.11) | ✅ matches live Grist |
| Avg Block % of Table A ceiling 9h (§117.11) | ✅ matches live Grist |
| Avg Rest Between Duties (h) | ✅ matches live Grist |
| Min Rest Between Duties (h) | ✅ matches live Grist |
| Avg Rest Ratio % of 10h min (§117.25(e)) | ✅ matches live Grist |
| Rests Under 10h (count, §117.25(e)) | ✅ matches live Grist |
| Flight Time last 672h — cap 100h (§117.23(b)(1)) | ✅ matches live Grist |
| Flight Time last 365d — cap 1000h (§117.23(b)(2)) | ✅ matches live Grist |
| FDP Hours last 168h — cap 60h (§117.23(c)(1)) | ✅ matches live Grist |
| FDP Hours last 672h — cap 190h (§117.23(c)(2)) | ✅ matches live Grist |
| Rolling 672h Flight Time by Day (cap 100h) | ✅ matches live Grist |
| Rolling 168h FDP Hours by Day (cap 60h) | ✅ matches live Grist |
| Avg Credit per TAFB Day | ✅ matches live Grist |
| Avg Block per TAFB Day | ✅ matches live Grist |
| Avg Days Between Trips | ✅ matches live Grist |
| Avg Block Variance per Trip (h) | ✅ matches live Grist |
| Avg Credit Variance per Trip (h) | ✅ matches live Grist |
| Credit & Block per TAFB Day by Month | ✅ matches live Grist |
| Duty Period Legality Detail | ✅ 67 rows == live Grist |
| Trip Efficiency Detail | ✅ 26 rows == live Grist |

**24/24 cards verified.**
