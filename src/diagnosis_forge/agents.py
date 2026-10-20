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




# --- graph: the code runs standard analyses, the model makes every decision ---------------------

import json as _json

from diagnosis_forge.answer import MECHANISM_NAMES
from diagnosis_forge.metrics import METRICS, _grouped, dims, sql_for, value
from diagnosis_forge.reference import DRIVERS


def _ask_json(llm: LLM, system: str, user: str) -> dict:
    reply = llm.chat(_messages(system, user))
    text = extract_json(reply) or "{}"
    try:
        out = _json.loads(text)
        return out if isinstance(out, dict) else {}
    except ValueError:
        return {}


def _pct(a: float, b: float) -> float:
    return 100.0 * (a - b) / b if b else 0.0


def _table(con, s: Scenario, metric: str, dim: str, where: dict) -> str:
    cur = _grouped(con, metric, *s.current, dim, where)
    base = _grouped(con, metric, *s.baseline, dim, where)
    total = sum(cur.values()) - sum(base.values())
    rows = sorted(set(cur) | set(base), key=lambda k: -abs(cur.get(k, 0) - base.get(k, 0)))
    lines = [f"by {dim}: value | current | baseline | change | change %" + (" | share of total change" if total else "")]
    for k in rows[:8]:
        c, b = cur.get(k, 0.0), base.get(k, 0.0)
        share = f" | {100 * (c - b) / total:.0f}%" if total else ""
        lines.append(f"  {k} | {c:,.2f} | {b:,.2f} | {c - b:+,.2f} | {_pct(c, b):+.1f}%{share}")
    return "\n".join(lines)


def run_graph(s: Scenario, llm: LLM, run_dir: Path, max_depth: int = 3, clarify: bool = False,
              max_questions: int = 3) -> AgentResult:
    """Fixed plan: metric -> size of change -> drill down by dimension -> mechanism -> answer.

    The code runs every query (logged as run_sql calls, so the evidence is real) and shows the
    results; the model decides the metric, whether the change is noise, where to drill and the
    mechanism.
    """
    started = time.monotonic()
    tb = ToolBox(s, run_dir, limits={"read_question": 1, "read_catalog": 1, "run_sql": 200, "check_answer": 2,
                                     "submit": 1})
    question = tb.call("read_question")
    catalog = tb.call("read_catalog")
    asked = 0
    extra = ""
    if clarify:
        extra, asked = _clarify(s, llm, catalog, question, max_questions)
    system = SYSTEM + "\nReply with JSON only."
    context = f"{question}{extra}"

    # 1. which metric
    pick = _ask_json(llm, system, f"{catalog}\n\n{context}\n\nWhich metric does the question ask about? "
                                  f'Reply {{"metric": "<one of {", ".join(METRICS)}>"}}.')
    metric = pick.get("metric")
    if metric not in METRICS:
        return _finish("graph+clarify" if clarify else "graph", s, llm, tb, started,
                       error=f"model chose an unknown metric: {metric!r}", questions=asked)

    con = tb.con
    evidence = []

    def measured(m, start, end, where, claim):
        sql = sql_for(m, start, end, where)
        out = tb.call("run_sql", {"sql": sql})
        v = value(con, m, start, end, where)
        evidence.append({"claim": claim, "sql": sql, "value": round(v, 6)})
        return v, out

    cur, _ = measured(metric, *s.current, {}, f"{metric} in the current period")
    base, _ = measured(metric, *s.baseline, {}, f"{metric} in the baseline period")
    change = _pct(cur, base)

    # 2. drill down
    where: dict[str, str] = {}
    noise = False
    for depth in range(max_depth):
        options = [d for d in dims(metric) if d not in where]
        if not options:
            break
        tables = []
        for d in options:
            tables.append(_table(con, s, metric, d, where))
            tb.log.append(_synthetic_log(f"breakdown {metric} by {d} where {where}"))
        scope = f"within {where}" if where else "overall"
        decision = _ask_json(llm, system, (
            f"{context}\n\n{metric}: current {cur:,.2f}, baseline {base:,.2f}, change {change:+.1f}%.\n"
            f"Breakdowns {scope}:\n" + "\n\n".join(tables) + "\n\n"
            "Decide the next step. If one value in one table explains most of the change and changed much more "
            "than the others, drill into it. If the overall change looks like normal variation (a few percent, "
            "spread evenly), call it noise. If no single value stands out any more, stop.\n"
            'Reply {"drill": {"<dimension>": "<value>"}} or {"stop": true} or {"noise": true}.'))
        if decision.get("noise") and not where:
            noise = True
            break
        drill = decision.get("drill")
        if not isinstance(drill, dict) or len(drill) != 1:
            break
        (d, v), = drill.items()
        if d not in options:
            break
        where[d] = str(v)

    answer: dict[str, Any] = {"metric": metric, "change": {"current": cur, "baseline": base, "pct": round(change, 2)},
                              "cause": None, "evidence": evidence}
    if not noise and where:
        # 3. mechanism: show every driver on the slice, let the model pick
        lines = []
        for mech, driver in DRIVERS.items():
            w = {k: v for k, v in where.items() if k in dims(driver)}
            try:
                a, b = measured(driver, *s.current, w, f"{driver} for {w} now")[0], \
                    measured(driver, *s.baseline, w, f"{driver} for {w} before")[0]
            except ValueError:
                continue
            lines.append(f"  {mech} ({driver}): current {a:,.4f}, baseline {b:,.4f}, change {_pct(a, b):+.1f}%")
        mech = _ask_json(llm, system, (
            f"{context}\n\nThe change is concentrated in {where}. Driver metrics for that slice:\n" + "\n".join(lines)
            + "\n\nWhich mechanism explains the change? Reply "
            f'{{"mechanism": "<one of {", ".join(MECHANISM_NAMES)}>"}}.')).get("mechanism")
        if mech in MECHANISM_NAMES:
            answer["cause"] = {"where": where, "mechanism": mech}
            keep = {f"{DRIVERS[mech]} for {({k: v for k, v in where.items() if k in dims(DRIVERS[mech])})} now",
                    f"{DRIVERS[mech]} for {({k: v for k, v in where.items() if k in dims(DRIVERS[mech])})} before"}
            answer["evidence"] = evidence[:2] + [e for e in evidence[2:] if e["claim"] in keep]
    text = _json.dumps(answer, default=str)
    tb.call("check_answer", {"answer": text})
    tb.call("submit", {"answer": text})
    return _finish("graph+clarify" if clarify else "graph", s, llm, tb, started, questions=asked)


def _synthetic_log(what: str):
    from diagnosis_forge.tools import ToolCall

    return ToolCall("breakdown", {"what": what[:120]}, True, False, 0.0, "")


def _clarify(s, llm, catalog, question, max_questions):  # replaced in milestone 4
    return "", 0


AGENTS = {"prompt": run_prompt, "sql-loop": run_sql_loop, "graph": run_graph}
