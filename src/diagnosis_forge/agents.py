"""Agent variants that answer "why did this metric change?".

- prompt:   one call from the catalog and the question; must answer with evidence queries it
            has never run.
- sql-loop: each reply is either one SQL query (its result is shown) or the final answer.

The final answer is scored with answer.score on the same data; agents never see the score.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from diagnosis_forge.answer import AnswerError, parse, score
from diagnosis_forge.llm import LLM, extract_json
from diagnosis_forge.scenario import Scenario
from diagnosis_forge.tools import ToolBox

SYSTEM = """You are a careful data analyst. You explain why a business metric changed between two
periods, using only the data described in the catalog (DuckDB SQL). Find the smallest slice
(for example one campaign in one region, or one product) that explains most of the change, and
the mechanism. If the change is within normal variation, say so with "cause": null.
Never guess numbers: every number in your answer must come from a query in "evidence"."""

LOOP_HELP = """Work step by step. In each reply do exactly one of:
1. Run a query: reply with one SQL query in a ```sql block. You will see its result.
2. Finish: reply with the final answer JSON in a ```json block.
You can run at most {n} queries."""

SQL_BLOCK = re.compile(r"```sql\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SQL_LINE = re.compile(r"^\s*SQL:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


@dataclass
class AgentResult:
    variant: str
    scenario: str
    model: str
    score: dict[str, Any] | None
    llm_calls: int
    prompt_tokens: int
    output_tokens: int
    llm_seconds: float
    seconds: float
    queries: int
    tool_calls: int
    blocked: int
    questions: int = 0
    error: str | None = None
    tool_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _context(tb: ToolBox) -> str:
    return f"{tb.call('read_catalog')}\n\n{tb.call('read_question')}"


def find_sql(reply: str) -> str | None:
    m = SQL_BLOCK.search(reply)
    if m:
        return m.group(1).strip()
    m = SQL_LINE.search(reply)
    return m.group(1).strip() if m else None


def find_answer(reply: str) -> str | None:
    text = extract_json(reply)
    if text is None:
        return None
    try:
        parse(text)
    except AnswerError:
        return None
    return text


def _finish(variant, s: Scenario, llm, tb: ToolBox, started, error=None, questions=0) -> AgentResult:
    sc = None
    if tb.answer is not None:
        sc = score(s, tb.answer, tb.con).to_dict()
    elif error is None:
        error = "no answer submitted"
    return AgentResult(
        variant=variant, scenario=s.name, model=getattr(llm, "model", type(llm).__name__), score=sc,
        llm_calls=llm.usage.calls, prompt_tokens=llm.usage.prompt_tokens, output_tokens=llm.usage.output_tokens,
        llm_seconds=round(llm.usage.seconds, 2), seconds=round(time.monotonic() - started, 2), queries=tb.queries,
        tool_calls=len(tb.log), blocked=tb.blocked, questions=questions, error=error,
        tool_log=[asdict(c) for c in tb.log],
    )


def run_prompt(s: Scenario, llm: LLM, run_dir: Path) -> AgentResult:
    started = time.monotonic()
    tb = ToolBox(s, run_dir)
    reply = llm.chat(_messages(SYSTEM, _context(tb) + "\n\nReply with the final answer JSON in a ```json block."))
    text = extract_json(reply)
    if text is not None:
        tb.call("submit", {"answer": text})
    return _finish("prompt", s, llm, tb, started, error=None if text else "no JSON answer in the reply")


def sql_loop(tb: ToolBox, llm: LLM, messages: list[dict[str, str]], max_queries: int) -> str | None:
    """Alternate queries and results until the model answers; returns the answer text or None."""
    for _ in range(max_queries + 1):
        reply = llm.chat(messages)
        answer = find_answer(reply)
        sql = find_sql(reply)
        if answer is not None and (sql is None or reply.find("```json") > reply.find("```sql")):
            return answer
        if sql is None or tb.queries >= max_queries:
            break
        result = tb.call("run_sql", {"sql": sql})
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": f"Result:\n{result}\n\n({max_queries - tb.queries} queries left.)"}]
    messages += [{"role": "user", "content": "No more queries. Reply now with the final answer JSON in a ```json block."}]
    reply = llm.chat(messages)
    return extract_json(reply)


def run_sql_loop(s: Scenario, llm: LLM, run_dir: Path, max_queries: int = 12) -> AgentResult:
    started = time.monotonic()
    tb = ToolBox(s, run_dir, limits={"read_question": 1, "read_catalog": 1, "run_sql": max_queries,
                                     "check_answer": 0, "submit": 1})
    messages = _messages(SYSTEM + "\n\n" + LOOP_HELP.format(n=max_queries), _context(tb))
    answer = sql_loop(tb, llm, messages, max_queries)
    if answer is not None:
        tb.call("submit", {"answer": answer})
    return _finish("sql-loop", s, llm, tb, started, error=None if answer else "no JSON answer in the reply")


AGENTS = {"prompt": run_prompt, "sql-loop": run_sql_loop}
