"""Scenario format: a question about a metric change, a simulated business, and the planted cause.

    name: west_promo_overspend
    question: Ad spend jumped in the second half of February. What happened?
    seed: 11
    business: {days: 90, scale: 1.0}
    metric: ad_spend
    compare: {current: [2026-02-15, 2026-02-28], baseline: [2026-02-01, 2026-02-14]}
    effects:
      - {driver: cpc, factor: 2.5, start: 2026-02-15, end: 2026-02-28,
         where: {campaign: spring_promo, region: west}}
    cause: {driver: cpc, where: {campaign: spring_promo, region: west}}   # null: nothing happened
    vague: false                       # the question leaves metric or period open (milestone 4)
    clarifications: {}                 # scripted answers {regex: answer} for the clarify agent

Effects other than the cause are distractors: real changes that are not the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from diagnosis_forge.metrics import METRICS
from diagnosis_forge.sim import DIMS, DRIVERS, Business, Effect, default_business

MECHANISMS = {"sessions": "traffic", "cpc": "cost_per_click", "conversion": "conversion", "price": "price",
              "refund_rate": "refunds"}


class ScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    seed: int
    business: Business
    metric: str
    current: tuple[date, date]
    baseline: tuple[date, date]
    effects: tuple[Effect, ...]
    cause: dict[str, Any] | None  # {"driver": ..., "where": {...}}
    vague: bool = False
    clarifications: dict[str, str] = field(default_factory=dict)

    @property
    def mechanism(self) -> str | None:
        return MECHANISMS[self.cause["driver"]] if self.cause else None


def _date(v: Any, where: str) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise ScenarioError(f"{where}: not a date: {v!r}") from None


def _period(v: Any, where: str) -> tuple[date, date]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ScenarioError(f"{where}: must be [start, end]")
    a, b = _date(v[0], where), _date(v[1], where)
    if b < a:
        raise ScenarioError(f"{where}: end before start")
    return a, b


def parse(data: Any) -> Scenario:
    if not isinstance(data, dict):
        raise ScenarioError("scenario must be a mapping")
    for key in ("name", "question", "seed", "metric", "compare", "effects", "cause"):
        if key not in data:
            raise ScenarioError(f"missing required key: {key}")
    unknown = set(data) - {"name", "question", "seed", "business", "metric", "compare", "effects", "cause",
                           "vague", "clarifications"}
    if unknown:
        raise ScenarioError(f"unknown keys: {sorted(unknown)}")
    if data["metric"] not in METRICS:
        raise ScenarioError(f"metric must be one of {METRICS}")
    b = data.get("business") or {}
    if set(b) - {"days", "scale", "start"}:
        raise ScenarioError(f"business: unknown keys {sorted(set(b) - {'days', 'scale', 'start'})}")
    biz = default_business(start=_date(b.get("start", "2026-01-01"), "business.start"), days=int(b.get("days", 120)),
                           scale=float(b.get("scale", 1.0)))
    last = biz.start.toordinal() + biz.days - 1
    cmp = data["compare"] or {}
    current, baseline = _period(cmp.get("current"), "compare.current"), _period(cmp.get("baseline"), "compare.baseline")
    for p, name in ((current, "current"), (baseline, "baseline")):
        if p[0] < biz.start or p[1].toordinal() > last:
            raise ScenarioError(f"compare.{name} is outside the simulated days")
    effects = []
    for i, e in enumerate(data["effects"] or []):
        if not isinstance(e, dict) or e.get("driver") not in DRIVERS:
            raise ScenarioError(f"effects[{i}]: driver must be one of {sorted(DRIVERS)}")
        where = dict(e.get("where") or {})
        if set(where) - DIMS:
            raise ScenarioError(f"effects[{i}]: unknown dimensions {sorted(set(where) - DIMS)}")
        effects.append(Effect(e["driver"], float(e["factor"]), _date(e["start"], f"effects[{i}]"),
                              _date(e["end"], f"effects[{i}]"), where))
    cause = data["cause"]
    if cause is not None:
        cause = {"driver": cause.get("driver"), "where": dict(cause.get("where") or {})}
        if not any(e.driver == cause["driver"] and e.where == cause["where"] for e in effects):
            raise ScenarioError("cause must match one of the effects (driver and where)")
    return Scenario(
        name=str(data["name"]), question=str(data["question"]).strip(), seed=int(data["seed"]), business=biz,
        metric=data["metric"], current=current, baseline=baseline, effects=tuple(effects), cause=cause,
        vague=bool(data.get("vague", False)), clarifications=dict(data.get("clarifications") or {}),
    )


def load(path: str | Path) -> Scenario:
    import yaml

    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f))


_BUILT: dict[str, object] = {}


def build(s: Scenario, fresh: bool = False):
    """Simulate the scenario's business and load it into an in-memory DuckDB.

    Results are cached per process (same business, seed and effects -> same database), since
    building takes seconds and everything that uses it only reads. Pass fresh=True for a new one.
    """
    from diagnosis_forge.sim import load as load_db, simulate

    key = repr((s.business, s.seed, s.effects))
    if fresh or key not in _BUILT:
        con = load_db(simulate(s.business, s.seed, s.effects))
        if fresh:
            return con
        _BUILT[key] = con
    return _BUILT[key]
