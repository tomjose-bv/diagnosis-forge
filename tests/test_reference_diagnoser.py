import pytest

from diagnosis_forge.answer import score
from diagnosis_forge.reference import diagnose
from diagnosis_forge.scenario import build, parse
from test_scenario_metrics import BASE

CUR = ["2026-02-15", "2026-02-28"]
CASES = {
    "cpc_spike": dict(),
    "email_conversion_drop": dict(
        metric="revenue",
        effects=[{"driver": "conversion", "factor": 0.25, "start": CUR[0], "end": CUR[1], "where": {"channel": "email"}}],
        cause={"driver": "conversion", "where": {"channel": "email"}}),
    "pro_plan_refunds": dict(
        metric="refunds",
        effects=[{"driver": "refund_rate", "factor": 6.0, "start": CUR[0], "end": CUR[1], "where": {"product": "pro_plan"}}],
        cause={"driver": "refund_rate", "where": {"product": "pro_plan"}}),
    "organic_traffic_collapse": dict(
        metric="sessions",
        effects=[{"driver": "sessions", "factor": 0.3, "start": CUR[0], "end": CUR[1], "where": {"channel": "organic"}}],
        cause={"driver": "sessions", "where": {"channel": "organic"}}),
    "north_search_traffic_drop": dict(
        metric="revenue",
        effects=[{"driver": "sessions", "factor": 0.1, "start": CUR[0], "end": CUR[1],
                  "where": {"channel": "paid_search", "region": "north"}}],
        cause={"driver": "sessions", "where": {"channel": "paid_search", "region": "north"}}),
}


@pytest.mark.parametrize("name", CASES)
def test_reference_finds_planted_cause(name):
    s = parse({**BASE, "name": name, "business": {"days": 60, "scale": 1.0}, **CASES[name]})
    con = build(s)
    sc = score(s, diagnose(s, con), con)
    assert sc.success, sc


def test_reference_no_cause():
    s = parse({**BASE, "metric": "revenue", "effects": [], "cause": None, "business": {"days": 60, "scale": 1.0}})
    con = build(s)
    a = diagnose(s, con)
    sc = score(s, a, con)
    assert a["cause"] is None and sc.cause == "correct_none" and sc.evidence_verified == 2
