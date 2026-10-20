from datetime import date

import pytest

from diagnosis_forge.metrics import breakdown, dims, value
from diagnosis_forge.scenario import ScenarioError, build, parse

BASE = {
    "name": "west_promo_overspend",
    "question": "Ad spend jumped in the second half of February. What happened?",
    "seed": 11,
    "business": {"days": 60, "scale": 0.5},
    "metric": "ad_spend",
    "compare": {"current": ["2026-02-15", "2026-02-28"], "baseline": ["2026-02-01", "2026-02-14"]},
    "effects": [{"driver": "cpc", "factor": 2.5, "start": "2026-02-15", "end": "2026-02-28",
                 "where": {"campaign": "spring_promo", "region": "west"}}],
    "cause": {"driver": "cpc", "where": {"campaign": "spring_promo", "region": "west"}},
}


def scen(**over):
    return parse({**BASE, **over})


def test_parse_and_mechanism():
    s = scen()
    assert s.current == (date(2026, 2, 15), date(2026, 2, 28)) and s.mechanism == "cost_per_click"
    assert scen(effects=[], cause=None).mechanism is None


@pytest.mark.parametrize(
    "over, msg",
    [
        ({"metric": "happiness"}, "metric must be one of"),
        ({"compare": {"current": ["2026-05-01", "2026-05-02"], "baseline": ["2026-02-01", "2026-02-02"]}}, "outside"),
        ({"compare": {"current": ["2026-02-10", "2026-02-01"], "baseline": ["2026-02-01", "2026-02-02"]}}, "end before"),
        ({"cause": {"driver": "price", "where": {}}}, "must match one of the effects"),
        ({"effects": [{"driver": "mood", "factor": 2, "start": "2026-02-01", "end": "2026-02-02"}]}, "driver"),
        ({"extra": 1}, "unknown keys"),
    ],
)
def test_errors(over, msg):
    with pytest.raises(ScenarioError, match=msg):
        scen(**over)


@pytest.fixture(scope="module")
def con():
    return build(scen())


def test_metric_values(con):
    s = scen()
    total = value(con, "ad_spend", *s.current)
    by_region = breakdown(con, "ad_spend", s.current, s.baseline, "region")
    assert sum(r["current"] for r in by_region) == pytest.approx(total)
    assert by_region[0]["value"] == "west" and by_region[0]["delta"] > 0  # the planted slice moves most
    cpc = value(con, "cpc", *s.current, {"campaign": "spring_promo", "region": "west"})
    base_cpc = value(con, "cpc", *s.baseline, {"campaign": "spring_promo", "region": "west"})
    assert cpc / base_cpc == pytest.approx(2.5, rel=0.1)


def test_ratio_and_refund_metrics(con):
    s = scen()
    assert 0 < value(con, "conversion_rate", *s.current) < 0.1
    assert value(con, "net_revenue", *s.current) == pytest.approx(
        value(con, "revenue", *s.current) - value(con, "refunds", *s.current))
    assert "product" in dims("refunds") and "product" not in dims("conversion_rate")
    rows = breakdown(con, "refunds", s.current, s.baseline, "channel")
    assert {r["value"] for r in rows} <= {"paid_search", "paid_social", "email", "organic"}


def test_bad_dimension(con):
    s = scen()
    with pytest.raises(ValueError, match="cannot be filtered"):
        value(con, "sessions", *s.current, {"product": "pro_plan"})
    with pytest.raises(ValueError, match="cannot be split"):
        breakdown(con, "conversion_rate", s.current, s.baseline, "product")
