# diagnosis-forge

A local AI agent that answers "why did this metric change?" questions over a business's data
("revenue dipped in early March, what happened?", "ad spend spiked, why?"), plus a benchmark of
synthetic businesses with planted causes that measures whether it finds the real one. Every
number in an answer must cite the SQL behind it, and the harness re-runs those queries to check.
Everything runs on one machine: Ollama for the model, DuckDB for the data.

Most "ask your data" tools give a confident paragraph. This project measures whether the
paragraph is right and whether its evidence holds up.

**Status:** milestone 1 of 5 done: simulator, planted causes, metrics, answer format, evidence
checks, scoring, reference diagnoser and scenarios. The AI agents come next (see [Roadmap](#roadmap)).

## How it works

```
scenario YAML ──► business simulator (seeded) ──► DuckDB: sessions, ad_spend, orders, refunds
     │                     │ planted cause                     ▲
     ▼                     ▼                                    │ read-only SQL
 question ──► reference diagnoser (agents: milestone 2) ────────┘
                   │
                   ▼
   answer JSON: change, cause (slice + mechanism), evidence [{claim, sql, value}]
                   │
   harness: re-run evidence SQL → check numbers → compare cause with the planted one
```

- **Simulator** (`sim.py`): a small online shop over 90 days: four channels with campaigns, four
  regions, four products; sessions → orders (conversion), ad spend (cost per click), refunds
  (lagging orders by up to two weeks), with weekend seasonality, growth and noise.
- **Planted causes**: a scenario changes one driver (traffic, cost per click, conversion, price or
  refund rate) for one slice during the current period. Some scenarios add a distractor (a real
  change that is not the answer) or have no cause at all.
- **Metrics** (`metrics.py`): revenue, orders, sessions, ad spend, refunds, net revenue, conversion
  rate, ROAS, cost per click, unit price, refund rate, each as reproducible SQL.
- **Scoring** (`answer.py`): cause exact / partial / wrong (a campaign implies its channel), mechanism,
  size of the change, share of cited numbers the harness reproduces, unsupported claims, false
  alarms on no-cause scenarios.
- **Reference diagnoser** (`reference.py`, no AI): sizes the change, drills down while one value
  explains at least 75% of it and changed at least twice as much as the rest, then picks the
  driver with the largest relative change. It solves every scenario, which shows each planted
  cause is findable from the data.
- **Scenarios**: 17 development (2 with distractors, 2 with no cause) and 5 held-out.

## Setup

Requires Python 3.12.

```
python scripts/setup.py
.venv\Scripts\python -m pytest -q          # Windows
.venv/bin/python -m pytest -q              # macOS/Linux
```

```
.venv\Scripts\diagnosis-forge eval --set dev             # the reference diagnoser on every scenario
.venv\Scripts\diagnosis-forge catalog                    # what agents are told about the data
```


## Roadmap

1. ~~Simulator, planted causes, metrics, answer format, evidence checks, scoring, reference diagnoser.~~
2. Guard, tools, LLM client, `prompt` and `sql-loop` agents (Ollama, `qwen2.5-coder:3b`).
3. The `graph` agent: the code runs the analyses, the model decides.
4. Vague questions and `graph+clarify`, which asks clarifying questions first.
5. Runs over three seeds, results in this README, CI, v0.1.0 release.

Later: the data behind mock APIs, connected with
[connector-forge](https://github.com/tomjose-bv/connector-forge) first.

## License

MIT
