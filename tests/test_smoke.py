import diagnosis_forge
from diagnosis_forge.cli import main


def test_version():
    assert diagnosis_forge.__version__


def test_cli_runs():
    assert main([]) == 0
