import diagnosis_forge
from diagnosis_forge.cli import main


def test_version():
    assert diagnosis_forge.__version__


def test_cli_runs():
    assert main([]) == 0


def test_catalog_mentions_everything():
    from diagnosis_forge.catalog import render
    from diagnosis_forge.metrics import METRICS

    doc = render()
    assert all(f"`{m}`" in doc for m in METRICS) and "cost_per_click" in doc and "`orders`(" in doc


def test_cli_eval(tmp_path):
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    out = tmp_path / "r.json"
    assert main(["eval", "--root", str(root), "--scenario", "pro_plan_refunds", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["scores"][0]["success"]


def test_cli_agent_with_fake_llm(tmp_path):
    import argparse
    import json
    from pathlib import Path

    from diagnosis_forge.cli import cmd_agent
    from diagnosis_forge.llm import FakeLLM
    from diagnosis_forge.reference import diagnose
    from diagnosis_forge.scenario import build, load

    root = Path(__file__).resolve().parent.parent
    s = load(root / "scenarios/dev/no_cause_revenue.yaml")
    good = json.dumps(diagnose(s, build(s)), default=str)
    args = argparse.Namespace(root=str(root), set="dev", scenario=["no_cause_revenue", "pro_plan_refunds"],
                              variant="prompt", model="fake", seed=1, temperature=0.0, out=str(tmp_path / "run"))
    assert cmd_agent(args, llm=FakeLLM([f"```json\n{good}\n```"])) == 0
    results = {r["scenario"]: r for r in json.loads((tmp_path / "run/summary.json").read_text())["results"]}
    assert results["no_cause_revenue"]["score"]["cause"] == "correct_none"
    assert "agent crashed" in results["pro_plan_refunds"]["error"]
