from datetime import date

import pytest

from diagnosis_forge.sim import Effect, default_business, load, simulate

BIZ = default_business(days=28, scale=0.3)
JAN = (date(2026, 1, 15), date(2026, 1, 28))


def test_deterministic():
    assert simulate(BIZ, 1) == simulate(BIZ, 1)
    assert simulate(BIZ, 1) != simulate(BIZ, 2)


def test_shapes():
    t = simulate(BIZ, 1)
    combos = sum(len(c.campaigns) for c in BIZ.channels) * len(BIZ.regions)
    assert len(t["sessions"]) == 28 * combos
    paid = sum(len(c.campaigns) for c in BIZ.channels if c.cpc > 0) * len(BIZ.regions)
    assert len(t["ad_spend"]) == 28 * paid
    assert len(t["orders"]) > 100 and 0 < len(t["refunds"]) < len(t["orders"])


def test_load_into_duckdb():
    con = load(simulate(BIZ, 1))
    assert con.execute("select count(*) from orders").fetchone()[0] == len(simulate(BIZ, 1)["orders"])
    assert con.execute("select min(date), max(date) from sessions").fetchone() == (date(2026, 1, 1), date(2026, 1, 28))
    assert con.execute("select sum(revenue) > 0, count(distinct channel) from orders").fetchone() == (True, 4)


def spend(con, where=""):
    return con.execute(f"select sum(spend) from ad_spend where date between '2026-01-15' and '2026-01-28' {where}").fetchone()[0]


def test_effect_changes_only_its_slice():
    base = load(simulate(BIZ, 3))
    eff = Effect("cpc", 2.0, *JAN, {"campaign": "spring_promo", "region": "west"})
    hit = load(simulate(BIZ, 3, [eff]))
    target = "and campaign = 'spring_promo' and region = 'west'"
    assert spend(hit, target) / spend(base, target) == pytest.approx(2.0, rel=0.1)
    other = "and not (campaign = 'spring_promo' and region = 'west')"
    assert spend(hit, other) / spend(base, other) == pytest.approx(1.0, rel=0.05)


def test_conversion_effect():
    base = load(simulate(BIZ, 4))
    hit = load(simulate(BIZ, 4, [Effect("conversion", 0.3, *JAN, {"channel": "email"})]))
    q = "select count(*) from orders where channel = 'email' and date >= '2026-01-15'"
    assert hit.execute(q).fetchone()[0] < 0.5 * base.execute(q).fetchone()[0]


def test_bad_effect():
    with pytest.raises(ValueError, match="driver"):
        simulate(BIZ, 1, [Effect("weather", 2.0, *JAN)])
    with pytest.raises(ValueError, match="dimensions"):
        simulate(BIZ, 1, [Effect("price", 2.0, *JAN, {"color": "red"})])
