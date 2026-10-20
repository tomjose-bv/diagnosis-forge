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
- M1.7 5 held-out scenarios in scenarios/heldout/ (traffic boost on one channel+region for
  ad_spend, accessory refund wave, brand-search conversion drop with a traffic distractor,
  starter-kit price rise, no-cause orders with an irrelevant CPC change), committed before
  any agent code; the reference solves all (the refund scenario was strengthened before
  commit, not the reference). 60 tests passing.
- M1.8 `catalog.py` (tables, dimensions, metric definitions, answer JSON format, mechanism
  names) and CLI `diagnosis-forge eval` / `catalog`; reference solves all 5 held-out
  scenarios. Employer-terms checks clean. 62 tests passing. **Milestone 1 done.**
- M2.1 `llm.py` (OllamaClient with reply cap, FakeLLM, extract_json) and `tools.py` ToolBox:
  read_question (question + periods, never the cause), read_catalog, run_sql (sqlguard, 30
  rows shown), check_answer (parse + re-run evidence, reviewer-style), submit; per-tool
  limits; blocked SQL counted. 68 tests passing.
- M2.2 `agents.py`: system prompt (smallest explaining slice + mechanism, null for noise, no
  numbers without queries); `prompt` (one call, evidence it never ran) and `sql-loop` (one
  query per reply via ```sql, results fed back, budget 12, forced final answer); AgentResult
  with score, usage, queries, tool log; CLI `diagnosis-forge agent --variant prompt|sql-
  loop` with crash isolation. 75 tests passing (13.5 min under CPU contention with the
  Ollama benchmark). **Milestone 2 done.**
- M3.1 `graph` agent: model picks the metric; code measures the change (logged run_sql with
  literal SQL); up to 3 drill-down rounds where code shows breakdown tables (current,
  baseline, change, share of total change) for every remaining dimension and the model
  replies drill/stop/noise; code shows all driver metrics for the slice and the model picks
  the mechanism; answer assembled with evidence from the queries that ran, checked,
  submitted. CLI `--variant graph`. **Milestone 3 done.** 78 tests passing.

## Ideas for later

## Publishing

Work happens on local branch `dev`. One push per day across all projects, from prepared slice
branches each ending in a README commit (C:/Users/Admin/Projects/PUBLISH-SCHEDULE.md). Never
change commit dates. The GitHub repo does not exist yet: ask the user before creating it.

## Next step

Milestone 4: vague questions + graph+clarify. Add 4 vague dev scenarios (e.g. 'Something is
off with marketing lately, can you look?') with `vague: true` and scripted clarifications
{regex: answer} giving metric and periods; for vague scenarios read_question shows only the
question (no periods) until clarified; ScriptedUser like flow-forge; graph+clarify asks up
to 3 questions first (implement _clarify); questions counted. Tests with FakeLLM.
