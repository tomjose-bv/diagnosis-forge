"""Business metrics as SQL over the simulated tables.

    value(con, "revenue", start, end, where={"channel": "email"})
    breakdown(con, "revenue", current, baseline, "region")  -> per-value current, baseline, delta

Refunds are dated by refund date and get their dimensions from the refunded order.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# metric -> (numerator SQL, denominator SQL or None, dimensions it can be split by)
_SUM = {
    "revenue": ("SELECT {dim} AS k, SUM(revenue) AS v FROM orders WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
                ("channel", "campaign", "region", "product")),
    "orders": ("SELECT {dim} AS k, COUNT(*) AS v FROM orders WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
               ("channel", "campaign", "region", "product")),
    "units": ("SELECT {dim} AS k, SUM(quantity) AS v FROM orders WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
              ("channel", "campaign", "region", "product")),
    "sessions": ("SELECT {dim} AS k, SUM(sessions) AS v FROM sessions WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
                 ("channel", "campaign", "region")),
    "ad_spend": ("SELECT {dim} AS k, SUM(spend) AS v FROM ad_spend WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
                 ("channel", "campaign", "region")),
    "clicks": ("SELECT {dim} AS k, SUM(clicks) AS v FROM ad_spend WHERE date BETWEEN ? AND ? {f} GROUP BY 1",
               ("channel", "campaign", "region")),
    "refunds": ("SELECT {dim} AS k, SUM(r.amount) AS v FROM refunds r JOIN orders o USING (order_id) "
                "WHERE r.date BETWEEN ? AND ? {f} GROUP BY 1", ("channel", "campaign", "region", "product")),
}
_RATIO = {
    "net_revenue": ("revenue", "-", "refunds"),
    "conversion_rate": ("orders", "/", "sessions"),
    "roas": ("revenue", "/", "ad_spend"),
    "cpc": ("ad_spend", "/", "clicks"),
    "average_order_value": ("revenue", "/", "orders"),
    "unit_price": ("revenue", "/", "units"),
    "refund_rate": ("refunds", "/", "revenue"),
}
METRICS = sorted(set(_SUM) | set(_RATIO))
DESCRIPTIONS = {
    "revenue": "sum of orders.revenue by order date",
    "orders": "number of orders",
    "sessions": "sum of sessions.sessions",
    "ad_spend": "sum of ad_spend.spend",
    "clicks": "sum of ad_spend.clicks",
    "refunds": "sum of refunds.amount by refund date",
    "net_revenue": "revenue minus refunds",
    "conversion_rate": "orders / sessions",
    "roas": "revenue / ad_spend (return on ad spend)",
    "cpc": "ad_spend / clicks (cost per click)",
    "average_order_value": "revenue / orders",
    "units": "sum of orders.quantity",
    "unit_price": "revenue / units",
    "refund_rate": "refunds / revenue",
}


def dims(metric: str) -> tuple[str, ...]:
    if metric in _SUM:
        return _SUM[metric][1]
    a, _, b = _RATIO[metric]
    return tuple(d for d in dims(a) if d in dims(b))


def _filter(where: dict[str, str], metric: str, alias: str = "") -> tuple[str, list[Any]]:
    bad = set(where) - set(dims(metric))
    if bad:
        raise ValueError(f"{metric} cannot be filtered by {sorted(bad)}")
    prefix = "o." if metric == "refunds" else alias
    return "".join(f" AND {prefix}{k} = ?" for k in where), list(where.values())


def _grouped(con, metric: str, start: date, end: date, dim: str | None, where: dict[str, str]) -> dict[Any, float]:
    if metric in _SUM:
        sql, _ = _SUM[metric]
        f, params = _filter(where, metric)
        col = ("o." if metric == "refunds" else "") + dim if dim else "'all'"
        rows = con.execute(sql.format(dim=col, f=f), [start, end, *params]).fetchall()
        return {k: float(v or 0) for k, v in rows}
    a, op, b = _RATIO[metric]
    if dim and dim not in dims(metric):
        raise ValueError(f"{metric} cannot be split by {dim}")
    x, y = _grouped(con, a, start, end, dim, where), _grouped(con, b, start, end, dim, where)
    keys = set(x) | set(y)
    if op == "-":
        return {k: x.get(k, 0.0) - y.get(k, 0.0) for k in keys}
    return {k: (x.get(k, 0.0) / y[k]) if y.get(k) else 0.0 for k in keys}


def value(con, metric: str, start: date, end: date, where: dict[str, str] | None = None) -> float:
    return _grouped(con, metric, start, end, None, where or {}).get("all", 0.0)


def breakdown(con, metric: str, current: tuple[date, date], baseline: tuple[date, date], dim: str,
              where: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Per value of `dim`: current, baseline and delta, largest absolute delta first."""
    cur = _grouped(con, metric, *current, dim, where or {})
    base = _grouped(con, metric, *baseline, dim, where or {})
    rows = [{"value": k, "current": cur.get(k, 0.0), "baseline": base.get(k, 0.0),
             "delta": cur.get(k, 0.0) - base.get(k, 0.0)} for k in set(cur) | set(base)]
    return sorted(rows, key=lambda r: (-abs(r["delta"]), str(r["value"])))


def is_ratio(metric: str) -> bool:
    return metric in _RATIO


def parts(metric: str) -> tuple[str, str, str]:
    return _RATIO[metric]


def _lit(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def sql_for(metric: str, start: date, end: date, where: dict[str, str] | None = None) -> str:
    """A self-contained SQL query (literals, no parameters) returning the metric as one number."""
    where = where or {}
    if metric in _SUM:
        sql, _ = _SUM[metric]
        f, params = _filter(where, metric)
        text = sql.format(dim="'all'", f=f).replace(" GROUP BY 1", "")
        for v in [start.isoformat(), end.isoformat(), *params]:
            text = text.replace("?", _lit(v), 1)
        return text.replace("SELECT 'all' AS k, ", "SELECT ")
    a, op, b = _RATIO[metric]
    x, y = sql_for(a, start, end, where), sql_for(b, start, end, where)
    if op == "-":
        return f"SELECT ({x}) - ({y})"
    return f"SELECT ({x}) / NULLIF(({y}), 0)"
