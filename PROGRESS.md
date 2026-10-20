# Progress

## Done

- Plan written (PLAN.md). Local repo created with personal git identity.
- M1.1 Project skeleton: pyproject (duckdb, pyyaml), src layout, scripts/setup.py (.venv),
  MIT license, README stub, smoke tests. 2 tests passing.
- M1.2 `sim.py`: Business (channels with campaigns, sessions, conversion, CPC; regions;
  products with price, refund rate, mix), simulate(seed, effects) -> sessions, ad_spend,
  orders, refunds with weekend seasonality, growth and noise; Effect(driver in
  sessions/cpc/conversion/price/refund_rate, factor, date range, where dims); load() into
  DuckDB via temp CSVs (120 days: ~14.5k orders, 0.3 s simulate, ~2 s load). 8 tests
  passing.

## Ideas for later

## Publishing

Work happens on local branch `dev`. One push per day across all projects, from prepared slice
branches each ending in a README commit (C:/Users/Admin/Projects/PUBLISH-SCHEDULE.md). Never
change commit dates. The GitHub repo does not exist yet: ask the user before creating it.

## Next step

Milestone 1, step 3: scenario format. `src/diagnosis_forge/scenario.py`: YAML {name,
question (plain English), seed, business overrides (days, scale), metric (revenue |
net_revenue | orders | ad_spend | conversion_rate | refunds | roas), compare: {current:
[start, end], baseline: [start, end]}, effects: [...], cause: {driver, where} (the planted
ground truth; null for no-cause scenarios), distractors: [...] (effects that are real but
not the answer), vague: bool, clarifications: {regex: answer}}; validation (dates inside the
simulated range, cause matches one effect). Metric SQL definitions in `metrics.py` (value
for a period, optionally grouped by dims). Tests.
