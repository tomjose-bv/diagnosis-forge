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
- M1.3 `metrics.py` (revenue, orders, sessions, ad_spend, clicks, refunds by refund date
  with order dims, and ratios net_revenue, conversion_rate, roas, cpc, average_order_value;
  value() and breakdown() by dimension with deltas, largest first) and `scenario.py`
  (question, seed, business size, metric, current/baseline periods, effects, planted cause
  matched to an effect or null, vague + clarifications; mechanism names; build() -> DuckDB).
  18 tests passing.
- M1.4 `sqlguard.py` (one SELECT/WITH statement, no file/settings functions, time limit via
  interrupt, row limit), `answer.py` (answer JSON: metric, change pct, cause where+mechanism
  or null, evidence claim/sql/value; parse from text; evidence re-run with 1% tolerance;
  score: exact/partial/wrong/missed/correct_none/false_alarm, mechanism, change sign+size,
  verified vs unsupported evidence, success). Channel implied by campaign is normalized. 31
  tests passing.
- M1.5 `reference.py` (no AI): change size (noise threshold 6%), drill-down while one value
  explains >= 75% of the parent's change AND changed >= 2x more than the rest relative to
  size (additive deltas for sums, denominator-weighted for ratios), mechanism = largest
  relative change among relevant drivers (sessions, cpc, conversion_rate, unit_price,
  refund_rate), evidence = literal SQL (metrics.sql_for) with values. New metrics units,
  unit_price, refund_rate. Scoring treats a single-campaign channel as the channel. Perfect
  on 5 planted cases + no-cause. 37 tests passing.
- M1.6 17 dev scenarios (scenarios/dev/; business 90 days at 3x scale for less noise): all
  five drivers across channels, campaigns, regions, products; metrics revenue, ad_spend,
  orders, refunds, net_revenue, sessions, roas; 2 with distractors; 2 no-cause (one with an
  irrelevant real change). Each planted cause moves its metric >= 10%; the reference
  diagnoser solves all. Lessons: at 1x scale noise rivals the planted effects; refunds lag
  orders by up to 14 days; a slice with zero traffic needs special handling (0/0 ratios
  skipped). 55 tests passing.

## Ideas for later

## Publishing

Work happens on local branch `dev`. One push per day across all projects, from prepared slice
branches each ending in a README commit (C:/Users/Admin/Projects/PUBLISH-SCHEDULE.md). Never
change commit dates. The GitHub repo does not exist yet: ask the user before creating it.

## Next step

Milestone 1, step 7: 5 held-out scenarios in scenarios/heldout/ (generator already has them:
run the scratch generator with 'heldout' or recreate), committed on their own before any
agent code; reference must solve them. Then step 8: catalog for agents (schema + metric
definitions + answer format) and CLI `diagnosis-forge eval` (reference over a set, JSON
report).
