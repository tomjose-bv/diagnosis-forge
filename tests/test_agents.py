import json
from pathlib import Path

from diagnosis_forge.agents import run_prompt, run_sql_loop
from diagnosis_forge.llm import FakeLLM
from diagnosis_forge.reference import diagnose
from diagnosis_forge.scenario import build, load

ROOT = Path(__file__).resolve().parent.parent
S = load(ROOT / "scenarios/dev/pro_plan_refunds.yaml")
GOOD = json.dumps(diagnose(S, build(S)), default=str)


def fenced(text, lang="json"):
    return f"```{lang}\n{text}\n```"


def test_prompt_agent_correct(tmp_path):
    llm = FakeLLM([fenced(GOOD)])
    r = run_prompt(S, llm, tmp_path)
    assert r.score["success"] and r.llm_calls == 1 and r.queries == 0
    assert "Refunds went up" in llm.seen[0][1]["content"] and "pro_plan" not in llm.seen[0][1]["content"]


def test_prompt_agent_made_up_numbers(tmp_path):
    bad = json.loads(GOOD)
    for e in bad["evidence"]:
        e["value"] = 123.0
    r = run_prompt(S, FakeLLM([fenced(json.dumps(bad))]), tmp_path)
    assert not r.score["success"] and r.score["unsupported"] == len(bad["evidence"])


def test_prompt_agent_no_json(tmp_path):
    r = run_prompt(S, FakeLLM(["It was probably the weather."]), tmp_path)
    assert r.score is None and "no JSON" in r.error


def test_sql_loop_queries_then_answers(tmp_path):
    llm = FakeLLM([fenced("SELECT product, SUM(amount) FROM refunds GROUP BY 1", "sql"), fenced(GOOD)])
    r = run_sql_loop(S, llm, tmp_path)
    assert r.score["success"] and r.queries == 1
    assert "pro_plan" in llm.seen[1][-1]["content"] and "queries left" in llm.seen[1][-1]["content"]


def test_sql_loop_budget_forces_answer(tmp_path):
    llm = FakeLLM([fenced("SELECT 1", "sql")] * 3 + [fenced(GOOD)])
    r = run_sql_loop(S, llm, tmp_path, max_queries=2)
    assert r.queries == 2 and r.score["success"]
    assert "No more queries" in llm.seen[-1][-1]["content"]


def test_sql_loop_blocked_query(tmp_path):
    llm = FakeLLM([fenced("DELETE FROM orders", "sql"), fenced(GOOD)])
    r = run_sql_loop(S, llm, tmp_path)
    assert r.blocked == 1 and r.score["success"]
