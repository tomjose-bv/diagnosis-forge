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


def cmd_agent(args, llm=None) -> int:
    from diagnosis_forge.agents import AGENTS, AgentResult
    from diagnosis_forge.llm import OllamaClient
    from diagnosis_forge.scenario import load

    root = Path(args.root)
    files = sorted((root / "scenarios" / args.set).glob("*.yaml"))
    if args.scenario:
        files = [f for f in files if f.stem in args.scenario]
    if not files:
        print("no scenarios found")
        return 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out or root / "runs" / f"{stamp}-{args.variant}-{args.set}-s{args.seed}")
    results = []
    print(f"{'scenario':<34} {'cause':<13} {'mech':>5} {'evidence':>9} {'ok':>3} {'queries':>7} {'tokens':>7} {'secs':>6}")
    for f in files:
        s = load(f)
        client = llm or OllamaClient(model=args.model, seed=args.seed, temperature=args.temperature)
        try:
            res = AGENTS[args.variant](s, client, out / f.stem)
        except Exception as e:  # a crashed agent (e.g. a model timeout) fails only this scenario
            u = client.usage
            res = AgentResult(args.variant, s.name, getattr(client, "model", "?"), None, u.calls, u.prompt_tokens,
                              u.output_tokens, round(u.seconds, 2), 0.0, 0, 0, 0,
                              error=f"agent crashed: {type(e).__name__}: {e}")
            (out / f.stem).mkdir(parents=True, exist_ok=True)
        results.append(res.to_dict())
        sc = res.score or {}
        print(f"{res.scenario:<34} {sc.get('cause', '-'):<13} {str(sc.get('mechanism_ok', '-')):>5} "
              f"{sc.get('evidence_verified', 0):>4}/{sc.get('evidence_total', 0):<4} "
              f"{'yes' if sc.get('success') or sc.get('cause') == 'correct_none' else 'no':>3} {res.queries:>7} "
              f"{res.prompt_tokens + res.output_tokens:>7} {res.seconds:>6.1f}")
        if res.error:
            print(f"    {res.error[:150]}")
        (out / f.stem / "result.json").write_text(json.dumps(res.to_dict(), indent=2, default=str), encoding="utf-8")
    m = meta(set=args.set, variant=args.variant, model=args.model, seed=args.seed, temperature=args.temperature)
    (out / "summary.json").write_text(json.dumps({"meta": m, "results": results}, indent=2, default=str),
                                      encoding="utf-8")
    print(f"wrote {out}")
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
    ag = sub.add_parser("agent", help="run an AI agent on scenarios (needs Ollama)")
    ag.add_argument("--variant", required=True, choices=("prompt", "sql-loop"))
    ag.add_argument("--set", choices=("dev", "heldout"), default="dev")
    ag.add_argument("--scenario", action="append")
    ag.add_argument("--model", default="qwen2.5-coder:3b")
    ag.add_argument("--seed", type=int, default=1)
    ag.add_argument("--temperature", type=float, default=0.2)
    ag.add_argument("--out")
    ag.add_argument("--root", default=".")
    sub.add_parser("catalog", help="print what agents are told about the data")
    args = parser.parse_args(argv)
    if args.command == "eval":
        return cmd_eval(args)
    if args.command == "agent":
        return cmd_agent(args)
    if args.command == "catalog":
        from diagnosis_forge.catalog import render

        print(render())
        return 0
    parser.print_help()
    return 0
