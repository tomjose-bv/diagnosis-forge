# Progress

## Done

- Plan written (PLAN.md). Local repo created with personal git identity.
- M1.1 Project skeleton: pyproject (duckdb, pyyaml), src layout, scripts/setup.py (.venv),
  MIT license, README stub, smoke tests. 2 tests passing.

## Ideas for later

## Publishing

Work happens on local branch `dev`. One push per day across all projects, from prepared slice
branches each ending in a README commit (C:/Users/Admin/Projects/PUBLISH-SCHEDULE.md). Never
change commit dates. The GitHub repo does not exist yet: ask the user before creating it.

## Next step

Milestone 1, step 2: business simulator. `src/diagnosis_forge/sim.py`: Business config
(start date, days, channels with base sessions + conversion + CPC, campaigns per channel,
regions with weights, products with price + refund rate); simulate(config, seed, effects=[])
-> DataFrames-free row lists for tables sessions(date, channel, campaign, region, sessions),
orders(order_id, date, channel, campaign, region, product, quantity, unit_price, revenue),
ad_spend(date, channel, campaign, region, spend, clicks), refunds(order_id, date, amount).
Weekly seasonality, small trend, Poisson-like noise. Effects (planted causes) multiply a
factor on a filter {dims} for a date range. Load into DuckDB. Tests: determinism, totals, an
effect changes only its slice.
