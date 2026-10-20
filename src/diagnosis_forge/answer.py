"""Answer format, evidence checking and scoring.

    {
      "metric": "ad_spend",
      "change": {"current": 5321.4, "baseline": 3888.0, "pct": 36.9},
      "cause": {"where": {"campaign": "spring_promo", "region": "west"}, "mechanism": "cost_per_click"},
      "evidence": [
        {"claim": "spring_promo in west cost 2.4x more per click",
         "sql": "SELECT ... ", "value": 2.41}
      ]
    }

`cause` is null when the change is normal noise. Every evidence item's query is re-run read-only;
its first cell must match the cited value (1% relative tolerance).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from diagnosis_forge.metrics import value as metric_value
from diagnosis_forge.scenario import MECHANISMS, Scenario
from diagnosis_forge.sqlguard import SQLError, run

MECHANISM_NAMES = sorted(MECHANISMS.values())


class AnswerError(ValueError):
    pass


@dataclass
class Evidence:
    claim: str
    sql: str
    value: float


@dataclass
class Answer:
    metric: str
    change_pct: float
    where: dict[str, str] | None
    mechanism: str | None
    evidence: list[Evidence]


def parse(data: Any) -> Answer:
    if isinstance(data, str):
        m = re.search(r"\{.*\}", data, re.DOTALL)
        if not m:
            raise AnswerError("no JSON object found")
        try:
            data = json.loads(m.group(0))
        except ValueError as e:
            raise AnswerError(f"invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise AnswerError("answer must be a JSON object")
    for key in ("metric", "change", "cause", "evidence"):
        if key not in data:
            raise AnswerError(f"missing key: {key}")
    change = data["change"]
    if not isinstance(change, dict) or not isinstance(change.get("pct"), (int, float)):
        raise AnswerError("change.pct must be a number (percent change, current vs baseline)")
    cause = data["cause"]
    where, mech = None, None
    if cause is not None:
        if not isinstance(cause, dict) or not isinstance(cause.get("where"), dict):
            raise AnswerError("cause must be null or {where: {dimension: value}, mechanism: ...}")
        where = {str(k): str(v) for k, v in cause["where"].items()}
        mech = cause.get("mechanism")
        if mech not in MECHANISM_NAMES:
            raise AnswerError(f"cause.mechanism must be one of {MECHANISM_NAMES}")
    if not isinstance(data["evidence"], list):
        raise AnswerError("evidence must be a list")
    ev = []
    for i, e in enumerate(data["evidence"]):
        if not isinstance(e, dict) or not isinstance(e.get("sql"), str) or not isinstance(e.get("value"), (int, float)):
            raise AnswerError(f"evidence[{i}] needs claim, sql (string) and value (number)")
        ev.append(Evidence(str(e.get("claim", "")), e["sql"], float(e["value"])))
    return Answer(str(data["metric"]), float(change["pct"]), where, mech, ev)


def check_evidence(con, answer: Answer) -> list[str | None]:
    """Per evidence item: None if verified, else the reason it failed."""
    out: list[str | None] = []
    for e in answer.evidence:
        try:
            _, rows, _ = run(con, e.sql, max_rows=1)
        except SQLError as err:
            out.append(str(err))
            continue
        got = rows[0][0] if rows and rows[0] else None
        try:
            got = float(got)
        except (TypeError, ValueError):
            out.append(f"query's first cell is not a number: {got!r}")
            continue
        if abs(got - e.value) <= max(0.01, 0.01 * abs(got)):
            out.append(None)
        else:
            out.append(f"query returns {got:.4g}, answer cites {e.value:.4g}")
    return out


@dataclass
class Score:
    scenario: str
    valid: bool
    error: str | None
    cause: str  # exact | partial | wrong | correct_none | false_alarm | missed
    cause_score: float
    mechanism_ok: bool | None
    change_ok: bool
    actual_pct: float
    evidence_total: int
    evidence_verified: int
    unsupported: int
    success: bool
    evidence_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize(where: dict[str, str], s: Scenario) -> dict[str, str]:
    """Drop a channel implied by the campaign (spring_promo implies paid_social)."""
    w = dict(where)
    camp_channel = {c: ch.name for ch in s.business.channels for c in ch.campaigns}
    if "campaign" in w and "channel" in w and camp_channel.get(w["campaign"]) == w["channel"]:
        del w["channel"]
    return w


def actual_pct(s: Scenario, con) -> float:
    cur, base = metric_value(con, s.metric, *s.current), metric_value(con, s.metric, *s.baseline)
    return 100.0 * (cur - base) / base if base else 0.0


def score(s: Scenario, answer_data: Any, con) -> Score:
    actual = actual_pct(s, con)
    try:
        a = parse(answer_data)
    except AnswerError as e:
        return Score(s.name, False, str(e), "missed" if s.cause else "wrong", 0.0, None, False, actual, 0, 0, 0, False)
    checks = check_evidence(con, a)
    verified = sum(c is None for c in checks)
    change_ok = (a.change_pct > 0) == (actual > 0) and abs(a.change_pct - actual) <= max(2.0, 0.15 * abs(actual))
    if s.cause is None:
        kind = "correct_none" if a.where is None else "false_alarm"
        cs, mech_ok = (1.0 if kind == "correct_none" else 0.0), None
    elif a.where is None:
        kind, cs, mech_ok = "missed", 0.0, False
    else:
        got, want = _normalize(a.where, s), _normalize(s.cause["where"], s)
        if got == want:
            kind, cs = "exact", 1.0
        elif got and (set(got.items()) < set(want.items()) or
                      (set(want.items()) < set(got.items()) and len(got) == len(want) + 1)):
            kind, cs = "partial", 0.5
        else:
            kind, cs = "wrong", 0.0
        mech_ok = a.mechanism == s.mechanism
    success = cs == 1.0 and mech_ok is not False and change_ok and len(checks) > 0 and verified == len(checks)
    return Score(s.name, True, None, kind, cs, mech_ok, change_ok, round(actual, 2), len(checks), verified,
                 len(checks) - verified, success, [c for c in checks if c][:3])
