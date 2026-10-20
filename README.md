# diagnosis-forge

A local AI agent that answers "why did this metric change?" questions over a business's data,
citing the SQL and numbers behind every claim, plus a benchmark of synthetic businesses with
planted causes that measures whether it finds the real cause. Everything runs on one machine:
Ollama for the model, DuckDB for the data.

Status: early development.

## Setup

```
python scripts/setup.py
.venv\Scripts\python -m pytest -q      # Windows
.venv/bin/python -m pytest -q          # macOS/Linux
```
