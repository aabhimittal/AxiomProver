"""Pipeline tests with a fake Lean runner — verdict logic without a toolchain."""

from pathlib import Path

from conftest import EXAMPLES

from axiomprover.report import Verdict
from axiomprover.runner import LeanNotFoundError, LeanResult
from axiomprover.verifier import verify_file


class AcceptingRunner:
    """Pretends the kernel accepts everything; records checked files."""

    def __init__(self):
        self.checked: list[str] = []

    def check(self, lean_file: Path) -> LeanResult:
        self.checked.append(lean_file.read_text(encoding="utf-8"))
        return LeanResult(accepted=True, stdout="", stderr="")


class RejectingRunner:
    def check(self, lean_file: Path) -> LeanResult:
        return LeanResult(accepted=False, stdout="error: unsolved goals", stderr="")


class MissingRunner:
    def check(self, lean_file: Path) -> LeanResult:
        raise LeanNotFoundError("lean not found")


def _by_name(reports):
    return {r.function: r for r in reports}


def test_verified_when_kernel_accepts(tmp_path):
    runner = AcceptingRunner()
    reports = _by_name(
        verify_file(EXAMPLES / "arithmetic.py", runner=runner, emit_dir=tmp_path)
    )
    assert reports["max2"].verdict is Verdict.VERIFIED
    assert all(t.proved for t in reports["max2"].theorems)
    # The first strategy "wins" under an accepting runner; what matters is
    # that the recorded tactic is the one in the emitted artifact.
    artifact = Path(reports["max2"].lean_file).read_text(encoding="utf-8")
    for t in reports["max2"].theorems:
        assert t.tactic in artifact


def test_refuted_beats_proof_search(tmp_path):
    # Even with an accepting runner, buggy code must come back REFUTED —
    # the falsifier runs first and the kernel never gets a vote.
    runner = AcceptingRunner()
    reports = _by_name(
        verify_file(EXAMPLES / "buggy.py", runner=runner, emit_dir=tmp_path)
    )
    for name, report in reports.items():
        assert report.verdict is Verdict.REFUTED, name
        assert report.counterexample is not None
    assert runner.checked == []  # no kernel calls were made at all


def test_unknown_when_no_strategy_closes(tmp_path):
    reports = _by_name(
        verify_file(
            EXAMPLES / "arithmetic.py", runner=RejectingRunner(), emit_dir=tmp_path
        )
    )
    report = reports["int_abs"]
    assert report.verdict is Verdict.UNKNOWN
    assert "sorry" in Path(report.lean_file).read_text(encoding="utf-8")
    assert not any(t.proved for t in report.theorems)


def test_error_when_lean_missing_but_refuted_still_works(tmp_path):
    arithmetic = _by_name(
        verify_file(
            EXAMPLES / "arithmetic.py", runner=MissingRunner(), emit_dir=tmp_path
        )
    )
    assert arithmetic["max2"].verdict is Verdict.ERROR

    buggy = _by_name(
        verify_file(EXAMPLES / "buggy.py", runner=MissingRunner(), emit_dir=tmp_path)
    )
    assert buggy["max2_buggy"].verdict is Verdict.REFUTED


def test_unsupported_reported_not_guessed(tmp_path):
    src = tmp_path / "loopy.py"
    src.write_text(
        """
from axiomprover import ensures, requires

@requires(lambda n: n >= 0)
@ensures(lambda n, result: result >= 0)
def count_down(n: int) -> int:
    while n > 0:
        n -= 1
    return n
"""
    )
    reports = verify_file(src, runner=AcceptingRunner(), emit_dir=tmp_path)
    assert len(reports) == 1
    assert reports[0].verdict is Verdict.UNSUPPORTED
    assert "While" in reports[0].detail


def test_no_falsify_skips_execution(tmp_path):
    src = tmp_path / "explosive.py"
    src.write_text(
        """
from axiomprover import ensures

BOOM = []
BOOM.pop()  # module level: executes only under the falsifier

@ensures(lambda n, result: result == n)
def ident(n: int) -> int:
    return n
"""
    )
    reports = verify_file(
        src, runner=AcceptingRunner(), emit_dir=tmp_path, falsify=False
    )
    assert reports[0].verdict is Verdict.VERIFIED

    # With falsification on, the module-level crash surfaces as ERROR.
    reports = verify_file(
        src, runner=AcceptingRunner(), emit_dir=tmp_path, falsify=True
    )
    assert reports[0].verdict is Verdict.ERROR


def test_relative_emit_dir_reaches_runner_as_absolute_path(tmp_path, monkeypatch):
    # Regression: the runner invokes `lean` with cwd=lean_file.parent, so a
    # relative artifact path (the CLI's default emit dir is relative to the
    # source file) silently broke every kernel call and surfaced as UNKNOWN.
    class PathCheckingRunner:
        def __init__(self):
            self.paths = []

        def check(self, lean_file: Path) -> LeanResult:
            self.paths.append(lean_file)
            assert lean_file.is_absolute(), lean_file
            assert lean_file.exists(), lean_file
            return LeanResult(accepted=True, stdout="", stderr="")

    src = tmp_path / "f.py"
    src.write_text(
        """
from axiomprover import ensures

@ensures(lambda n, result: result == n)
def ident(n: int) -> int:
    return n
"""
    )
    monkeypatch.chdir(tmp_path)
    runner = PathCheckingRunner()
    reports = verify_file("f.py", runner=runner, emit_dir="out", falsify=False)
    assert reports[0].verdict is Verdict.VERIFIED
    assert runner.paths, "runner was never invoked"


def test_limits_examples_are_unknown_under_rejecting_runner(tmp_path):
    reports = _by_name(
        verify_file(EXAMPLES / "limits.py", runner=RejectingRunner(), emit_dir=tmp_path)
    )
    assert reports["square"].verdict is Verdict.UNKNOWN
    assert reports["even_split"].verdict is Verdict.UNKNOWN
