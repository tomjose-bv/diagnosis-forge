"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from diagnosis_forge import __version__


def meta(**extra) -> dict:
    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}",
        "processor": platform.processor(),
        "python": platform.python_version(),
        "version": __version__,
        **extra,
    }


def cmd_eval(args) -> int:
    from diagnosis_forge.answer import score
    from diagnosis_forge.reference import diagnose
    from diagnosis_forge.scenario import build, load

    files = sorted((Path(args.root) / "scenarios" / args.set).glob("*.yaml"))
    if args.scenario:
        files = [f for f in files if f.stem in args.scenario]
    if not files:
        print("no scenarios found")
        return 1
    print(f"{'scenario':<34} {'cause':<13} {'mech':>5} {'change':>7} {'evidence':>9} {'ok':>3}")
    scores = []
    for f in files:
        s = load(f)
        con = build(s)
        sc = score(s, diagnose(s, con), con)
        scores.append(sc.to_dict())
        print(f"{s.name:<34} {sc.cause:<13} {str(sc.mechanism_ok):>5} {sc.actual_pct:>6.1f}% "
              f"{sc.evidence_verified:>4}/{sc.evidence_total:<4} {'yes' if sc.success or sc.cause == 'correct_none' else 'no':>3}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"meta": meta(set=args.set, variant="reference"), "scores": scores},
                                             indent=2), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnosis-forge")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    ev = sub.add_parser("eval", help="run the reference diagnoser on a scenario set")
    ev.add_argument("--set", choices=("dev", "heldout"), default="dev")
    ev.add_argument("--scenario", action="append")
    ev.add_argument("--out")
    ev.add_argument("--root", default=".")
    sub.add_parser("catalog", help="print what agents are told about the data")
    args = parser.parse_args(argv)
    if args.command == "eval":
        return cmd_eval(args)
    if args.command == "catalog":
        from diagnosis_forge.catalog import render

        print(render())
        return 0
    parser.print_help()
    return 0
