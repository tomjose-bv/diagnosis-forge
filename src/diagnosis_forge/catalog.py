"""What agents get: the tables, the metric definitions, the dimensions and the answer format."""

from __future__ import annotations

from diagnosis_forge.answer import MECHANISM_NAMES
from diagnosis_forge.metrics import DESCRIPTIONS, METRICS, dims
from diagnosis_forge.sim import SCHEMA

ANSWER_HELP = """## Answer format

Reply with one JSON object:

```json
{
  "metric": "<metric name>",
  "change": {"current": <number>, "baseline": <number>, "pct": <percent change, current vs baseline>},
  "cause": {"where": {"<dimension>": "<value>", ...}, "mechanism": "<mechanism>"},
  "evidence": [{"claim": "<what this shows>", "sql": "<one SELECT query>", "value": <the number it returns>}]
}
```

- `cause` is `null` if the change is within normal variation (no specific cause).
- `where` is the smallest slice that explains the change (for example one campaign in one region).
- mechanism, one of: {mechanisms}.
  traffic = sessions changed; cost_per_click = spend per click changed; conversion = orders per
  session changed; price = unit price changed; refunds = refund rate changed.
- Every number you claim needs an evidence item. Each `sql` must return that number in its first
  row and first column; it is re-run to check it.
"""


def render() -> str:
    lines = ["# Data catalog", "", "DuckDB tables (one row per day x channel x campaign x region, or per order/refund):", ""]
    for t, cols in SCHEMA.items():
        lines.append(f"- `{t}`({cols})")
    lines += [
        "",
        "Dimensions: channel, campaign (each belongs to one channel), region, product (orders and refunds only).",
        "Refunds have the refund date; join refunds to orders on order_id for channel, campaign and region.",
        "",
        "## Metrics",
        "",
    ]
    for m in METRICS:
        lines.append(f"- `{m}`: {DESCRIPTIONS[m]}; can be split by {', '.join(dims(m))}")
    lines += ["", ANSWER_HELP.replace("{mechanisms}", ", ".join(MECHANISM_NAMES))]
    return "\n".join(lines)
