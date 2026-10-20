"""Reference diagnoser (no AI): size the change, drill down, pick the mechanism, cite evidence.

1. Change = metric(current) vs metric(baseline). Below NOISE_PCT -> no cause.
2. Drill down: for each remaining dimension, split the change by its values; a value "explains"
   the change when its contribution is at least SHARE of the parent's change (same sign). Take
   the dimension whose top value explains the most, add it to the slice, repeat.
   Contributions are additive deltas for sum metrics; for ratio metrics, the ratio change of each
   value weighted by its share of the denominator.
3. Mechanism: on the slice, compare driver metrics (traffic, cost per click, conversion, unit
   price, refund rate) between periods and pick the largest relative change among the drivers
   that can move the metric.
4. Evidence: the SQL it used, with the values it got.
"""

from __future__ import annotations

import math
from typing import Any

from diagnosis_forge.metrics import _grouped, dims, is_ratio, parts, sql_for, value
from diagnosis_forge.scenario import Scenario

NOISE_PCT = 6.0
SHARE = 0.75  # a value must explain at least this share of the parent's change
LIFT = 2.0  # ... and change at least this much more, relative to its size, than the rest
DRIVERS = {  # mechanism -> driver metric
    "traffic": "sessions",
    "cost_per_click": "cpc",
    "conversion": "conversion_rate",
    "price": "unit_price",
    "refunds": "refund_rate",
}
RELEVANT = {
    "ad_spend": ("traffic", "cost_per_click"), "clicks": ("traffic",), "cpc": ("cost_per_click",),
    "sessions": ("traffic",), "revenue": ("traffic", "conversion", "price"), "orders": ("traffic", "conversion"),
    "units": ("traffic", "conversion"), "average_order_value": ("price",), "unit_price": ("price",),
    "conversion_rate": ("conversion",), "roas": ("cost_per_click", "conversion", "price"),
    "refunds": ("refunds", "traffic", "conversion", "price"), "refund_rate": ("refunds",),
    "net_revenue": ("refunds", "traffic", "conversion", "price"),
}


def _contributions(con, metric, s: Scenario, dim, where) -> list[tuple[Any, float, float]]:
    """(value, contribution to the change, share of the baseline) per value of `dim`."""
    cur, base = _grouped(con, metric, *s.current, dim, where), _grouped(con, metric, *s.baseline, dim, where)
    keys = set(cur) | set(base)
    if not is_ratio(metric) or parts(metric)[1] == "-":
        size = metric if not is_ratio(metric) else parts(metric)[0]
        b = _grouped(con, size, *s.baseline, dim, where)
        total_b = sum(abs(v) for v in b.values()) or 1.0
        return [(k, cur.get(k, 0.0) - base.get(k, 0.0), abs(b.get(k, 0.0)) / total_b) for k in keys]
    _, _, den = parts(metric)
    w, wb = _grouped(con, den, *s.current, dim, where), _grouped(con, den, *s.baseline, dim, where)
    total, total_b = sum(w.values()) or 1.0, sum(wb.values()) or 1.0
    return [(k, (cur.get(k, 0.0) - base.get(k, 0.0)) * w.get(k, 0.0) / total, wb.get(k, 0.0) / total_b) for k in keys]


def _slice_for(metric: str, where: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in where.items() if k in dims(metric)}


def diagnose(s: Scenario, con) -> dict[str, Any]:
    cur, base = value(con, s.metric, *s.current), value(con, s.metric, *s.baseline)
    pct = 100.0 * (cur - base) / base if base else 0.0
    evidence = [
        {"claim": f"{s.metric} in the current period", "sql": sql_for(s.metric, *s.current), "value": round(cur, 6)},
        {"claim": f"{s.metric} in the baseline period", "sql": sql_for(s.metric, *s.baseline), "value": round(base, 6)},
    ]
    answer = {"metric": s.metric, "change": {"current": cur, "baseline": base, "pct": round(pct, 2)},
              "cause": None, "evidence": evidence}
    if abs(pct) < NOISE_PCT:
        return answer

    where: dict[str, str] = {}
    parent = cur - base if not is_ratio(s.metric) or parts(s.metric)[1] == "-" else None
    while True:
        best = None
        for dim in dims(s.metric):
            if dim in where:
                continue
            contrib = _contributions(con, s.metric, s, dim, where)
            total = parent if parent is not None else sum(c for _, c, _ in contrib)
            if not total or len(contrib) < 2:
                continue
            k, c, base_share = max(contrib, key=lambda kc: kc[1] * math.copysign(1, total))
            share = c / total
            slice_rel = c / base_share if base_share else float("inf")
            rest_rel = abs(total - c) / (1 - base_share) if base_share < 1 else 0.0
            disproportionate = abs(slice_rel) >= LIFT * rest_rel
            if share >= SHARE and disproportionate and (best is None or share > best[2]):
                best = (dim, k, share, c)
        if best is None:
            break
        where[best[0]] = best[1]
        parent = best[3] if parent is not None else None
    if not where:
        return answer

    mech, best_change = None, 0.0
    for m in RELEVANT[s.metric]:
        driver = DRIVERS[m]
        w = _slice_for(driver, where)
        if len(w) < len(where) and m != "refunds":
            w = _slice_for(driver, where)  # driver cannot see every dimension: use what it can
        try:
            a, b = value(con, driver, *s.current, w), value(con, driver, *s.baseline, w)
        except ValueError:
            continue
        if a <= 0 or b <= 0:
            continue
        change = abs(math.log(a / b))
        if change > best_change:
            mech, best_change, used = m, change, (driver, w, a, b)
    if mech is None:
        return answer
    driver, w, a, b = used
    evidence += [
        {"claim": f"{driver} for {w} now", "sql": sql_for(driver, *s.current, w), "value": round(a, 6)},
        {"claim": f"{driver} for {w} before", "sql": sql_for(driver, *s.baseline, w), "value": round(b, 6)},
    ]
    answer["cause"] = {"where": where, "mechanism": mech}
    return answer
