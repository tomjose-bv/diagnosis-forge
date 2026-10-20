import json

import pytest

from diagnosis_forge.answer import AnswerError, actual_pct, parse, score
from diagnosis_forge.scenario import build, parse as parse_scenario
from diagnosis_forge.sqlguard import SQLError, check, run
from test_scenario_metrics import BASE

S = parse_scenario(BASE)
CPC_SQL = ("SELECT SUM(spend)/SUM(clicks) FROM ad_spend WHERE campaign='spring_promo' AND region='west' "
           "AND date BETWEEN '2026-02-15' AND '2026-02-28'")


@pytest.fixture(scope="module")
def con():
    return build(S)


def answer(con, where=None, mech="cost_per_click", pct=None, evidence=None):
    cpc = con.execute(CPC_SQL).fetchone()[0]
    return {
        "metric": "ad_spend",
        "change": {"pct": actual_pct(S, con) if pct is None else pct},
        "cause": None if where is False else {"where": where or {"campaign": "spring_promo", "region": "west"},
                                              "mechanism": mech},
        "evidence": evidence if evidence is not None else [{"claim": "cpc", "sql": CPC_SQL, "value": cpc}],
    }


@pytest.mark.parametrize("sql, msg", [
    ("DELETE FROM orders", "only SELECT"),
    ("SELECT 1; DROP TABLE orders", "one statement"),
    ("SELECT * FROM read_csv('x.csv')", "not allowed"),
    ("WITH x AS (SELECT 1) SELECT * FROM x; ATTACH 'a.db'", "one statement"),
    ("SELECT getenv('HOME')", "not allowed"),
])
def test_sql_guard(sql, msg):
    with pytest.raises(SQLError, match=msg):
        check(sql)


def test_sql_guard_allows_selects(con):
    assert check("select 'a;b' as x;") == "select 'a;b' as x"
    cols, rows, trunc = run(con, "SELECT region, SUM(spend) s FROM ad_spend GROUP BY 1 ORDER BY 1", max_rows=2)
    assert cols == ["region", "s"] and len(rows) == 2 and trunc
    with pytest.raises(SQLError, match="query failed"):
        run(con, "SELECT nope FROM orders")


def test_exact_answer_succeeds(con):
    sc = score(S, answer(con), con)
    assert sc.cause == "exact" and sc.mechanism_ok and sc.change_ok and sc.success
    assert (sc.evidence_total, sc.evidence_verified, sc.unsupported) == (1, 1, 0)


def test_implied_channel_still_exact(con):
    w = {"channel": "paid_social", "campaign": "spring_promo", "region": "west"}
    assert score(S, answer(con, where=w), con).cause == "exact"


def test_partial_and_wrong(con):
    assert score(S, answer(con, where={"campaign": "spring_promo"}), con).cause == "partial"
    assert score(S, answer(con, where={"campaign": "spring_promo", "region": "west", "product": "pro_plan"}),
                 con).cause == "partial"
    assert score(S, answer(con, where={"region": "east"}), con).cause == "wrong"
    assert score(S, answer(con, where=False), con).cause == "missed"


def test_wrong_mechanism_or_change(con):
    assert not score(S, answer(con, mech="traffic"), con).success
    assert not score(S, answer(con, pct=-10), con).change_ok


def test_bad_evidence(con):
    ev = [{"claim": "made up", "sql": CPC_SQL, "value": 99.0},
          {"claim": "no query", "sql": "DROP TABLE orders", "value": 1}]
    sc = score(S, answer(con, evidence=ev), con)
    assert sc.unsupported == 2 and not sc.success and "cites 99" in sc.evidence_errors[0]
    assert not score(S, answer(con, evidence=[]), con).success  # claims need evidence


def test_no_cause_scenario(con):
    calm = parse_scenario({**BASE, "effects": [], "cause": None})
    c2 = build(calm)
    a = answer(c2, where=False, evidence=[{"claim": "x", "sql": "SELECT 1", "value": 1}])
    a["change"]["pct"] = actual_pct(calm, c2)
    assert score(calm, a, c2).cause == "correct_none"
    assert score(calm, answer(c2), c2).cause == "false_alarm"


def test_parse_from_text_and_errors():
    txt = "Here is my answer:\n" + json.dumps({"metric": "x", "change": {"pct": 1}, "cause": None, "evidence": []})
    assert parse(txt).where is None
    with pytest.raises(AnswerError, match="mechanism"):
        parse({"metric": "x", "change": {"pct": 1}, "cause": {"where": {}, "mechanism": "magic"}, "evidence": []})
    with pytest.raises(AnswerError, match="no JSON"):
        parse("I think it was the weather.")
