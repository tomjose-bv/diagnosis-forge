# diagnosis-forge: plan

A local AI agent that answers "why did this metric change?" questions over a business's data
("revenue dipped last quarter, what happened?", "marketing spend spiked last month"), and a
benchmark that measures whether it finds the real cause. Every claim in an answer must cite the
SQL query and the numbers behind it, and the harness re-runs those queries to check them.
Everything runs on one machine: Ollama for the model, DuckDB for the data.

Most "ask your data" tools give a confident paragraph. This project measures whether the
paragraph is right and whether its evidence holds up.

## Architecture

```
scenario YAML ──► business simulator (seeded) ──► DuckDB tables (orders, ad spend, sessions, refunds)
     │                     │ planted cause                     ▲
     ▼                     ▼                                    │ read-only SQL
 question ──► agent (Ollama) ── tools ──► guard ───────────────┘
                   │
                   ▼
         structured answer (cause + evidence queries)
                   │
   harness: re-run evidence SQL → check numbers → compare cause with the planted one → metrics
```

- **Business simulator:** a seeded daily model of a small online business: channels, campaigns,
  regions, products; sessions → orders (conversion), ad spend, refunds. Normal noise, weekly
  seasonality and growth trends.
- **Planted causes:** a scenario changes one thing in one period, for example: one campaign's
  spend jumps in one region; conversion drops on one channel (tracking or checkout problem); a
  product's refund rate spikes; a price cut lifts orders but cuts revenue per order; a channel's
  traffic collapses. Some scenarios add distractors (a real but irrelevant change elsewhere) or
  no cause at all (normal noise).
- **Answer format:** JSON: metric, direction and size of the change, the cause as a set of
  dimension values (`{"campaign": "spring_promo", "region": "west"}`) and a mechanism
  (`spend_increase`, `conversion_drop`, ...), and evidence items `{claim, sql, value}`.
- **Harness:** re-runs every evidence query read-only and checks the cited values; scores the
  cause against the planted one (exact, partial, wrong), and the size estimate.

## Agent variants

1. `reference`: a hand-written decomposition (no AI): compares periods, drills down dimension by
   dimension, and picks the largest contributor. Proves the harness; target close to 100%.
2. `prompt`: one model call with the schema and the question; answer from SQL it proposes.
3. `sql-loop`: the model runs queries (up to N) and then answers.
4. `graph`: fixed plan: size the change → split by each dimension → drill into the largest
   contributor → check the mechanism → verify evidence → answer.
5. `graph+clarify`: for vague questions, asks a scripted user which metric, period and comparison.

## Scenarios and metrics

- About 16 development scenarios plus 5 held-out ones (fixed in their own commit before any agent).
- Metrics:
  - cause accuracy: exact, partial (right dimension, wrong value, or only part of the set), wrong
  - mechanism accuracy
  - evidence validity: share of cited numbers that the harness reproduces
  - unsupported claims: claims without a reproducible query
  - false alarms on no-cause scenarios
  - queries run, clarifying questions, rounds, tokens and time; calls blocked by the guard

## Milestones (each split into small committed steps)

1. Simulator, scenario format, planted causes, DuckDB loader, answer format, evidence checker,
   scoring, harness and the `reference` diagnoser.
2. Guard (read-only SQL, row and time limits), tools, LLM client, `prompt` and `sql-loop` agents.
3. The `graph` agent.
4. Distractors, no-cause scenarios, vague questions and `graph+clarify`.
5. Real runs over three seeds, README with results, CI, v0.1.0 release (ask before pushing).

Later (not planned yet): data behind mock APIs, connected with connector-forge first.

## Stack

Python 3.12, duckdb, pyyaml, pytest. Ollama with `qwen2.5-coder:3b` (optional `qwen2.5-coder:7b`).
