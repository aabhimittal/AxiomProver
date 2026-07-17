"""The verification pipeline.

    parse ──► falsify (execution; can only refute)
                │
                ▼
          translate to Lean (the modeled semantics)
                │
                ▼
          proof search (strategy chain per theorem)
                │
                ▼
          Lean kernel check ──► VERIFIED / UNKNOWN

Per theorem, candidate tactic scripts are tried against a scratch file; once
every theorem has a winning script, one final artifact containing the
definition and all proved theorems is written and re-checked in a single
kernel run. That final file is the certificate — keep it, re-check it
anywhere, audit its definition against the Python source.
"""

from __future__ import annotations

from pathlib import Path

from axiomprover import falsifier as _falsifier
from axiomprover.parser import TargetFunction, parse_file
from axiomprover.report import FunctionReport, TheoremReport, Verdict
from axiomprover.runner import LeanNotFoundError, LeanRunner
from axiomprover.strategies import strategies_for
from axiomprover.translator import UnsupportedError, translate_function


def verify_file(
    path: str | Path,
    runner: LeanRunner | None = None,
    emit_dir: str | Path | None = None,
    falsify: bool = True,
    trials: int = 2000,
) -> list[FunctionReport]:
    path = Path(path)
    runner = runner or LeanRunner()
    # Resolve so every artifact path handed to the runner (which changes the
    # subprocess cwd) and recorded in reports is unambiguous.
    emit = (Path(emit_dir) if emit_dir else path.parent / ".axiomprover").resolve()
    targets = parse_file(path)
    return [
        verify_function(t, source_path=path, runner=runner, emit_dir=emit,
                        falsify=falsify, trials=trials)
        for t in targets
    ]


def verify_function(
    target: TargetFunction,
    source_path: Path | None,
    runner: LeanRunner,
    emit_dir: Path,
    falsify: bool = True,
    trials: int = 2000,
) -> FunctionReport:
    # 1. Cheap refutation by execution, before any modeling or proof effort.
    #    This also serves functions whose bodies or specs fall outside the
    #    translatable subset — a counterexample needs only the interpreter.
    if falsify and source_path is not None:
        try:
            fn_obj = _falsifier.load_function(source_path, target.name)
            cex = _falsifier.falsify(fn_obj, target, trials=trials)
        except Exception as exc:
            return FunctionReport(
                function=target.name,
                verdict=Verdict.ERROR,
                detail=f"failed to execute module for counterexample search: {exc}",
            )
        if cex is not None:
            return FunctionReport(
                function=target.name,
                verdict=Verdict.REFUTED,
                detail=f"ensures clause violated: {cex.failed_clause}",
                counterexample={"args": cex.args, "result": cex.result},
            )

    # 2. Model the function in Lean. If we can't model it we must not claim
    #    anything about it.
    try:
        module = translate_function(target)
    except UnsupportedError as exc:
        return FunctionReport(
            function=target.name,
            verdict=Verdict.UNSUPPORTED,
            detail=str(exc),
        )

    # 3. Proof search, one theorem at a time.
    emit_dir.mkdir(parents=True, exist_ok=True)
    theorem_reports: list[TheoremReport] = []
    winning: list[str] = []
    try:
        for i, theorem in enumerate(module.theorems):
            tactic = _prove_one(module, i, runner, emit_dir)
            theorem_reports.append(
                TheoremReport(
                    name=theorem.name,
                    clause=theorem.clause_source,
                    proved=tactic is not None,
                    tactic=tactic,
                )
            )
            winning.append(tactic if tactic is not None else "sorry")
    except LeanNotFoundError as exc:
        return FunctionReport(
            function=target.name,
            verdict=Verdict.ERROR,
            detail=str(exc),
            lean_file=_emit(module, ["sorry"] * len(module.theorems), emit_dir),
        )

    lean_file = _emit(module, winning, emit_dir)

    if all(t.proved for t in theorem_reports):
        # 4. Re-check the final combined artifact; the certificate must stand
        #    on its own, not just as separate scratch runs.
        result = runner.check(Path(lean_file))
        if not result.accepted:
            return FunctionReport(
                function=target.name,
                verdict=Verdict.ERROR,
                detail=(
                    "individually proved theorems failed in the combined "
                    f"artifact (kernel said: {result.diagnostics[:500]})"
                ),
                theorems=theorem_reports,
                lean_file=lean_file,
            )
        return FunctionReport(
            function=target.name,
            verdict=Verdict.VERIFIED,
            detail="all ensures clauses kernel-checked for all inputs",
            theorems=theorem_reports,
            lean_file=lean_file,
        )

    open_goals = [t.name for t in theorem_reports if not t.proved]
    return FunctionReport(
        function=target.name,
        verdict=Verdict.UNKNOWN,
        detail=(
            f"no strategy closed: {', '.join(open_goals)}. Emitted artifact "
            f"with `sorry` placeholders — prove manually or add @proof(...)"
        ),
        theorems=theorem_reports,
        lean_file=lean_file,
    )


def _prove_one(module, index: int, runner: LeanRunner, emit_dir: Path) -> str | None:
    """Try the strategy chain on theorem *index*; return the first script the
    kernel accepts, else None."""
    single = _single_theorem_module(module, index)
    scratch = emit_dir / f"_scratch_{module.function_name}_{index}.lean"
    for tactic in strategies_for(module):
        scratch.write_text(single.render([tactic]), encoding="utf-8")
        result = runner.check(scratch)
        if result.accepted:
            scratch.unlink(missing_ok=True)
            return tactic
    scratch.unlink(missing_ok=True)
    return None


def _single_theorem_module(module, index: int):
    from axiomprover.translator import LeanModule

    return LeanModule(
        function_name=module.function_name,
        definition=module.definition,
        theorems=[module.theorems[index]],
        proof_hint=module.proof_hint,
        bool_params=module.bool_params,
    )


def _emit(module, tactics: list[str], emit_dir: Path) -> str:
    out = emit_dir / f"{module.function_name}.lean"
    out.write_text(module.render(tactics), encoding="utf-8")
    return str(out)
