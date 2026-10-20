"""Agent tools for one scenario, behind a guard.

Agents query the scenario's own data (that is the task) through read-only SQL, but never see
the planted cause or the simulator settings. Tools: read_question, read_catalog, run_sql,
check_answer (parses the answer and re-runs its evidence, like a reviewer would), submit.
The guard enforces per-tool limits and the SQL rules in sqlguard.py, and logs every call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from diagnosis_forge.answer import AnswerError, check_evidence, parse
from diagnosis_forge.catalog import render as render_catalog
from diagnosis_forge.scenario import Scenario, build
from diagnosis_forge.sqlguard import SQLError, run

DEFAULT_LIMITS = {"read_question": 3, "read_catalog": 3, "run_sql": 20, "check_answer": 5, "submit": 1}
MAX_ROWS = 30


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    ok: bool
    blocked: bool
    seconds: float
    result: str


@dataclass
class ToolBox:
    scenario: Scenario
    run_dir: Path
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    log: list[ToolCall] = field(default_factory=list)
    answer: Any = None
    submitted: bool = False

    def __post_init__(self):
        self.run_dir = Path(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.con = build(self.scenario)

    @property
    def blocked(self) -> int:
        return sum(c.blocked for c in self.log)

    @property
    def queries(self) -> int:
        return sum(1 for c in self.log if c.tool == "run_sql" and not c.blocked)

    def count(self, tool: str) -> int:
        return sum(1 for c in self.log if c.tool == tool and not c.blocked)

    def call(self, tool: str, args: dict[str, Any] | None = None) -> str:
        args = dict(args or {})
        started = time.monotonic()
        handler = getattr(self, f"_tool_{tool}", None)
        blocked, ok = False, False
        if handler is None:
            blocked, result = True, f"error: unknown tool {tool!r}"
        elif self.submitted:
            blocked, result = True, "error: already submitted"
        elif self.count(tool) >= self.limits.get(tool, 0):
            blocked, result = True, f"error: call limit for {tool} reached ({self.limits.get(tool, 0)})"
        else:
            try:
                result, ok = handler(**args), True
            except SQLError as e:
                blocked = "not allowed" in str(e) or "only" in str(e)
                result = f"error: {e}"
            except TypeError as e:
                result = f"error: bad arguments: {e}"
        short = {k: (v[:120] + "..." if isinstance(v, str) and len(v) > 120 else v) for k, v in args.items()}
        self.log.append(ToolCall(tool, short, ok, blocked, round(time.monotonic() - started, 3), result[:400]))
        return result

    # tools
    def _tool_read_question(self) -> str:
        s = self.scenario
        return (f"Question: {s.question}\nCurrent period: {s.current[0]} to {s.current[1]}\n"
                f"Baseline period: {s.baseline[0]} to {s.baseline[1]}")

    def _tool_read_catalog(self) -> str:
        return render_catalog()

    def _tool_run_sql(self, sql: str) -> str:
        cols, rows, truncated = run(self.con, sql, max_rows=MAX_ROWS)
        lines = [" | ".join(cols)]
        for r in rows:
            lines.append(" | ".join(_fmt(v) for v in r))
        if truncated:
            lines.append(f"... more rows (only the first {MAX_ROWS} are shown)")
        if not rows:
            lines.append("(no rows)")
        return "\n".join(lines)

    def _tool_check_answer(self, answer: str) -> str:
        try:
            a = parse(answer)
        except AnswerError as e:
            return f"the answer cannot be read: {e}"
        checks = check_evidence(self.con, a)
        bad = [f"- evidence {i + 1}: {c}" for i, c in enumerate(checks) if c]
        if not checks:
            return "the answer has no evidence; every number needs a query"
        return "all evidence checks out" if not bad else "evidence problems:\n" + "\n".join(bad)

    def _tool_submit(self, answer: str) -> str:
        self.answer = answer
        self.submitted = True
        (self.run_dir / "answer.json").write_text(answer if isinstance(answer, str) else json.dumps(answer),
                                                  encoding="utf-8")
        return "submitted"


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:.2f}"
    return str(v)
