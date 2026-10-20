"""Command-line entry point."""

import argparse

from diagnosis_forge import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnosis-forge")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)
    return 0
