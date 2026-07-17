import json

import pytest
from conftest import EXAMPLES

from axiomprover import cli
from axiomprover.runner import LeanResult


class AcceptingRunner:
    def check(self, lean_file):
        return LeanResult(accepted=True, stdout="", stderr="")


@pytest.fixture
def accepting_lean(monkeypatch):
    monkeypatch.setattr(
        cli, "LeanRunner", lambda lean_bin=None, timeout=None: AcceptingRunner()
    )


def test_translate_prints_lean(capsys):
    rc = cli.main(["translate", str(EXAMPLES / "arithmetic.py"), "--function", "max2"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "def max2 (a : Int) (b : Int) : Int :=" in out
    assert "theorem max2_spec_1" in out


def test_translate_marks_unsupported(tmp_path, capsys):
    src = tmp_path / "loopy.py"
    src.write_text(
        "from axiomprover import ensures\n"
        "@ensures(lambda n, result: result >= 0)\n"
        "def f(n: int) -> int:\n"
        "    while n > 0:\n"
        "        n -= 1\n"
        "    return n\n"
    )
    rc = cli.main(["translate", str(src)])
    assert rc == 0
    assert "UNSUPPORTED" in capsys.readouterr().out


def test_verify_json_output(accepting_lean, tmp_path, capsys):
    rc = cli.main(
        [
            "verify",
            str(EXAMPLES / "arithmetic.py"),
            "--json",
            "--emit-dir",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    verdicts = {entry["function"]: entry["verdict"] for entry in payload}
    assert verdicts["max2"] == "VERIFIED"


def test_verify_exit_code_1_on_refutation(accepting_lean, tmp_path, capsys):
    rc = cli.main(
        ["verify", str(EXAMPLES / "buggy.py"), "--emit-dir", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "REFUTED" in out
    assert "counterexample" in out


def test_unknown_function_selection_fails(accepting_lean, tmp_path, capsys):
    rc = cli.main(
        [
            "verify",
            str(EXAMPLES / "arithmetic.py"),
            "--function",
            "nope",
            "--emit-dir",
            str(tmp_path),
        ]
    )
    assert rc == 2
