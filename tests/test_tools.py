import json
from pathlib import Path

import pytest

from diagnosis_forge.llm import FakeLLM, extract_json
from diagnosis_forge.reference import diagnose
from diagnosis_forge.scenario import load
from diagnosis_forge.tools import ToolBox

ROOT = Path(__file__).resolve().parent.parent
S = load(ROOT / "scenarios/dev/pro_plan_refunds.yaml")


@pytest.fixture(scope="module")
def tb_module(tmp_path_factory):
    return ToolBox(S, tmp_path_factory.mktemp("run"))


def test_question_and_catalog(tb_module):
    q = tb_module.call("read_question")
    assert "Refunds went up" in q and "2026-03-01" in q
    assert "refund_rate" in tb_module.call("read_catalog")
    assert "pro_plan" not in q  # the cause is never given away


def test_run_sql(tb_module):
    out = tb_module.call("run_sql", {"sql": "SELECT product, COUNT(*) n FROM orders GROUP BY 1 ORDER BY 1"})
    assert out.splitlines()[0] == "product | n" and "pro_plan" in out
    assert "more rows" in tb_module.call("run_sql", {"sql": "SELECT * FROM orders"})
    assert "error: query failed" in tb_module.call("run_sql", {"sql": "SELECT nope FROM orders"})


def test_guard_blocks_writes(tmp_path):
    tb = ToolBox(S, tmp_path)
    assert "only SELECT" in tb.call("run_sql", {"sql": "DROP TABLE orders"})
    assert tb.blocked == 1
    assert "unknown tool" in tb.call("shell", {"cmd": "dir"})


def test_check_answer_and_submit(tmp_path):
    tb = ToolBox(S, tmp_path)
    good = json.dumps(diagnose(S, tb.con), default=str)
    assert tb.call("check_answer", {"answer": good}) == "all evidence checks out"
    bad = json.loads(good)
    bad["evidence"][0]["value"] = 1.0
    assert "evidence 1" in tb.call("check_answer", {"answer": json.dumps(bad)})
    assert "cannot be read" in tb.call("check_answer", {"answer": "it was refunds"})
    assert tb.call("submit", {"answer": good}) == "submitted" and tb.answer == good
    assert "already submitted" in tb.call("run_sql", {"sql": "SELECT 1"})


def test_limits(tmp_path):
    tb = ToolBox(S, tmp_path, limits={"run_sql": 1})
    tb.call("run_sql", {"sql": "SELECT 1"})
    assert "call limit" in tb.call("run_sql", {"sql": "SELECT 1"}) and tb.queries == 1


def test_extract_json():
    assert extract_json('Answer:\n```json\n{"a": {"b": 1}}\n```') == '{"a": {"b": 1}}'
    assert extract_json("no json") is None
    assert FakeLLM(["x"]).chat([]) == "x"
