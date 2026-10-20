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
