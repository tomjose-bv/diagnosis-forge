from pathlib import Path

import pytest

from diagnosis_forge.answer import actual_pct, score
from diagnosis_forge.reference import diagnose
from diagnosis_forge.scenario import build, load

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted((ROOT / "scenarios").rglob("*.yaml"))


def test_dev_set_size():
    assert len([f for f in FILES if f.parent.name == "dev"]) >= 16


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}-{p.stem}")
def test_scenario_is_sound_and_reference_succeeds(path):
    s = load(path)
    assert s.name == path.stem and s.question
    con = build(s)
    if s.cause is not None:
        assert abs(actual_pct(s, con)) >= 10, "the planted cause must move the metric materially"
    sc = score(s, diagnose(s, con), con)
    assert sc.success or (s.cause is None and sc.cause == "correct_none"), sc
