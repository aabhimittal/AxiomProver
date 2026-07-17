"""End-to-end tests against a real Lean kernel.

Skipped when no `lean` is on PATH (set AXIOMPROVER_LEAN to point elsewhere).
CI installs the toolchain pinned in lean/lean-toolchain and runs these.
"""

import pytest
from conftest import EXAMPLES

from axiomprover.report import Verdict
from axiomprover.runner import LeanRunner
from axiomprover.verifier import verify_file

runner = LeanRunner(timeout=300.0)

pytestmark = pytest.mark.skipif(
    not runner.available(), reason="lean executable not found"
)


def _by_name(reports):
    return {r.function: r for r in reports}


def test_arithmetic_examples_all_verify(tmp_path):
    reports = _by_name(
        verify_file(EXAMPLES / "arithmetic.py", runner=runner, emit_dir=tmp_path)
    )
    for name, report in reports.items():
        assert report.verdict is Verdict.VERIFIED, (
            f"{name}: {report.verdict} — {report.detail}"
        )


def test_buggy_examples_all_refuted(tmp_path):
    reports = _by_name(
        verify_file(EXAMPLES / "buggy.py", runner=runner, emit_dir=tmp_path)
    )
    for name, report in reports.items():
        assert report.verdict is Verdict.REFUTED, name


def test_limits_examples_stay_unknown_not_verified(tmp_path):
    reports = _by_name(
        verify_file(EXAMPLES / "limits.py", runner=runner, emit_dir=tmp_path)
    )
    for name, report in reports.items():
        assert report.verdict is Verdict.UNKNOWN, (
            f"{name}: expected UNKNOWN, got {report.verdict}"
        )


def test_kernel_rejects_a_false_theorem(tmp_path):
    # The soundness test that matters most: hand the kernel a lie and make
    # sure no strategy can launder it into VERIFIED.
    src = tmp_path / "lie.py"
    src.write_text(
        """
from axiomprover import ensures

@ensures(lambda n, result: result >= 1)
def ident(n: int) -> int:
    return n
"""
    )
    reports = verify_file(src, runner=runner, emit_dir=tmp_path, falsify=False)
    assert reports[0].verdict is not Verdict.VERIFIED
