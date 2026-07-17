"""Command-line interface.

    axiomprover verify path/to/file.py      # full pipeline
    axiomprover translate path/to/file.py   # print generated Lean, no checking
    axiomprover check-env                   # is a usable Lean on PATH?
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from axiomprover import __version__
from axiomprover.parser import SpecSyntaxError, parse_file
from axiomprover.report import Verdict, render_json, render_text
from axiomprover.runner import LeanRunner
from axiomprover.translator import UnsupportedError, translate_function
from axiomprover.verifier import verify_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="axiomprover",
        description="Lean-based formal verification of AI-generated code",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify contracts in a Python file")
    p_verify.add_argument("file", type=Path)
    p_verify.add_argument("--function", help="verify only this function")
    p_verify.add_argument("--lean-bin", help="path to the lean executable")
    p_verify.add_argument("--timeout", type=float, default=120.0,
                          help="seconds per kernel invocation (default 120)")
    p_verify.add_argument("--emit-dir", type=Path,
                          help="where to write .lean artifacts "
                               "(default: .axiomprover next to the source)")
    p_verify.add_argument("--no-falsify", action="store_true",
                          help="skip counterexample search (do not execute "
                               "the target file)")
    p_verify.add_argument("--trials", type=int, default=2000,
                          help="counterexample search budget per function")
    p_verify.add_argument("--json", action="store_true", help="JSON output")

    p_translate = sub.add_parser(
        "translate", help="print the generated Lean model without checking"
    )
    p_translate.add_argument("file", type=Path)
    p_translate.add_argument("--function", help="translate only this function")

    sub.add_parser("check-env", help="report Lean toolchain availability")

    args = parser.parse_args(argv)

    if args.command == "check-env":
        return _check_env()
    if args.command == "translate":
        return _translate(args)
    return _verify(args)


def _check_env() -> int:
    runner = LeanRunner()
    version = runner.version() if runner.available() else None
    if version:
        print(f"lean: {version}")
        print("environment ok — verify can produce VERIFIED verdicts")
        return 0
    print("lean: NOT FOUND")
    print("Install elan: https://leanprover-community.github.io/get_started.html")
    print("Without Lean, `translate` still works and `verify` can still REFUTE.")
    return 1


def _translate(args: argparse.Namespace) -> int:
    try:
        targets = parse_file(args.file)
    except SpecSyntaxError as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return 2
    targets = _select(targets, args.function)
    for target in targets:
        try:
            module = translate_function(target)
        except UnsupportedError as exc:
            print(f"-- {target.name}: UNSUPPORTED ({exc})\n")
            continue
        print(module.render(["sorry"] * len(module.theorems)))
    return 0


def _verify(args: argparse.Namespace) -> int:
    runner = LeanRunner(lean_bin=args.lean_bin, timeout=args.timeout)
    try:
        reports = verify_file(
            args.file,
            runner=runner,
            emit_dir=args.emit_dir,
            falsify=not args.no_falsify,
            trials=args.trials,
        )
    except SpecSyntaxError as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return 2

    if args.function:
        reports = [r for r in reports if r.function == args.function]
        if not reports:
            print(f"no contracted function named {args.function!r}", file=sys.stderr)
            return 2

    print(render_json(reports) if args.json else render_text(reports))

    if any(r.verdict is Verdict.REFUTED for r in reports):
        return 1
    if any(r.verdict in (Verdict.ERROR, Verdict.UNKNOWN, Verdict.UNSUPPORTED)
           for r in reports):
        return 3
    return 0


def _select(targets, name):
    if not name:
        return targets
    selected = [t for t in targets if t.name == name]
    if not selected:
        print(f"no contracted function named {name!r}", file=sys.stderr)
        raise SystemExit(2)
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
