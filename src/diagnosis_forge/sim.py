"""Seeded simulator of a small online business, with planted causes ("effects").

Tables (one row per day x channel x campaign x region, plus one row per order / refund):
    sessions(date, channel, campaign, region, sessions)
    ad_spend(date, channel, campaign, region, clicks, spend)        -- paid channels only
    orders(order_id, date, channel, campaign, region, product, quantity, unit_price, revenue)
    refunds(order_id, date, product, amount)

An effect multiplies one driver for the rows that match its filter during its date range:
    sessions    traffic (and, for paid channels, clicks and spend with it)
    cpc         cost per click (spend up, traffic unchanged)
    conversion  orders per session
    price       unit price of matching products
    refund_rate share of matching orders that get refunded
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

DRIVERS = {"sessions", "cpc", "conversion", "price", "refund_rate"}
DIMS = {"channel", "campaign", "region", "product"}


@dataclass(frozen=True)
class Channel:
    name: str
    sessions: float  # mean daily sessions per campaign at region weight 1
    conversion: float  # orders per session
    cpc: float = 0.0  # cost per click; 0 = organic (no ad spend)
    campaigns: tuple[str, ...] = ("always_on",)


@dataclass(frozen=True)
class Product:
    name: str
    price: float
    refund_rate: float = 0.03
    weight: float = 1.0  # share of orders


@dataclass(frozen=True)
class Effect:
    driver: str
    factor: float
    start: date
    end: date  # inclusive
    where: dict[str, str] = field(default_factory=dict)  # dimension -> value

    def applies(self, d: date, row: dict[str, Any]) -> bool:
        return self.start <= d <= self.end and all(row.get(k) == v for k, v in self.where.items())


@dataclass(frozen=True)
class Business:
    start: date
    days: int
    channels: tuple[Channel, ...]
    regions: dict[str, float]
    products: tuple[Product, ...]
    weekend_factor: float = 0.85
    daily_growth: float = 0.001


def default_business(start: date = date(2026, 1, 1), days: int = 120, scale: float = 1.0) -> Business:
    return Business(
        start=start,
        days=days,
        channels=(
            Channel("paid_search", 220 * scale, 0.032, 0.9, ("brand", "generic")),
            Channel("paid_social", 260 * scale, 0.018, 0.6, ("spring_promo", "retargeting")),
            Channel("email", 120 * scale, 0.045, 0.0, ("newsletter",)),
            Channel("organic", 300 * scale, 0.025, 0.0, ("organic",)),
        ),
        regions={"north": 1.0, "south": 0.8, "east": 0.6, "west": 0.9},
        products=(
            Product("basic_plan", 29.0, 0.02, 3.0),
            Product("pro_plan", 79.0, 0.03, 1.5),
            Product("starter_kit", 49.0, 0.05, 1.0),
            Product("accessory_pack", 15.0, 0.04, 2.0),
        ),
    )


def _factor(effects: list[Effect], driver: str, d: date, row: dict[str, Any]) -> float:
    f = 1.0
    for e in effects:
        if e.driver == driver and e.applies(d, row):
            f *= e.factor
    return f


def _noisy(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    return max(0, round(rng.gauss(mean, math.sqrt(mean))))


def simulate(biz: Business, seed: int, effects: list[Effect] | tuple[Effect, ...] = ()) -> dict[str, list[tuple]]:
    for e in effects:
        if e.driver not in DRIVERS:
            raise ValueError(f"unknown driver {e.driver!r}")
        if set(e.where) - DIMS:
            raise ValueError(f"unknown dimensions {sorted(set(e.where) - DIMS)}")
    effects = list(effects)
    rng = random.Random(seed)
    names = [p.name for p in biz.products]
    weights = [p.weight for p in biz.products]
    by_name = {p.name: p for p in biz.products}
    tables: dict[str, list[tuple]] = {"sessions": [], "ad_spend": [], "orders": [], "refunds": []}
    order_id = 0
    for i in range(biz.days):
        d = biz.start + timedelta(days=i)
        season = (biz.weekend_factor if d.weekday() >= 5 else 1.0) * (1 + biz.daily_growth) ** i
        for ch in biz.channels:
            for camp in ch.campaigns:
                for region, rw in biz.regions.items():
                    row = {"channel": ch.name, "campaign": camp, "region": region}
                    s = _noisy(rng, ch.sessions * rw * season * _factor(effects, "sessions", d, row))
                    tables["sessions"].append((d, ch.name, camp, region, s))
                    if ch.cpc > 0:
                        cpc = ch.cpc * _factor(effects, "cpc", d, row) * rng.uniform(0.95, 1.05)
                        tables["ad_spend"].append((d, ch.name, camp, region, s, round(s * cpc, 2)))
                    conv = min(1.0, ch.conversion * _factor(effects, "conversion", d, row))
                    n_orders = rng.binomialvariate(s, conv) if s else 0
                    for _ in range(n_orders):
                        prod = by_name[rng.choices(names, weights)[0]]
                        prow = {**row, "product": prod.name}
                        qty = rng.choice((1, 1, 1, 2, 2, 3))
                        price = round(prod.price * _factor(effects, "price", d, prow), 2)
                        order_id += 1
                        revenue = round(qty * price, 2)
                        tables["orders"].append((order_id, d, ch.name, camp, region, prod.name, qty, price, revenue))
                        rate = min(1.0, prod.refund_rate * _factor(effects, "refund_rate", d, prow))
                        if rng.random() < rate:
                            rd = d + timedelta(days=rng.randint(1, 14))
                            tables["refunds"].append((order_id, rd, prod.name, revenue))
    return tables


SCHEMA = {
    "sessions": "date DATE, channel VARCHAR, campaign VARCHAR, region VARCHAR, sessions INTEGER",
    "ad_spend": "date DATE, channel VARCHAR, campaign VARCHAR, region VARCHAR, clicks INTEGER, spend DOUBLE",
    "orders": "order_id INTEGER, date DATE, channel VARCHAR, campaign VARCHAR, region VARCHAR, product VARCHAR, "
              "quantity INTEGER, unit_price DOUBLE, revenue DOUBLE",
    "refunds": "order_id INTEGER, date DATE, product VARCHAR, amount DOUBLE",
}


def load(tables: dict[str, list[tuple]], path: str = ":memory:"):
    """Create a DuckDB database with the simulated tables (via temporary CSV files, which is fast)."""
    import csv
    import tempfile
    from pathlib import Path

    import duckdb

    con = duckdb.connect(path)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for name, rows in tables.items():
            f = Path(tmp) / f"{name}.csv"
            with open(f, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows(rows)
            cols = SCHEMA[name]
            con.execute(f"CREATE TABLE {name} ({cols})")
            if rows:
                types = {c.split()[0]: c.split()[1] for c in cols.split(", ")}
                con.execute(f"INSERT INTO {name} SELECT * FROM read_csv('{f.as_posix()}', header=false, "
                            f"columns={types!r})")
    return con
