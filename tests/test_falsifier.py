from conftest import EXAMPLES

from axiomprover.falsifier import falsify, load_function
from axiomprover.parser import parse_file


def _target(path, name):
    return next(t for t in parse_file(path) if t.name == name)


def test_refutes_buggy_max():
    path = EXAMPLES / "buggy.py"
    target = _target(path, "max2_buggy")
    fn = load_function(path, "max2_buggy")
    cex = falsify(fn, target)
    assert cex is not None
    a, b = cex.args["a"], cex.args["b"]
    result = cex.result
    # The witness must actually violate one of the ensures clauses.
    assert not (result >= a and result >= b) or not (result == a or result == b)


def test_refutes_same_sign_at_zero():
    path = EXAMPLES / "buggy.py"
    target = _target(path, "same_sign_buggy")
    fn = load_function(path, "same_sign_buggy")
    cex = falsify(fn, target)
    assert cex is not None
    assert cex.args["a"] == 0 or cex.args["b"] == 0


def test_refutes_round_up_on_odd_input():
    path = EXAMPLES / "buggy.py"
    target = _target(path, "round_up_to_even_buggy")
    fn = load_function(path, "round_up_to_even_buggy")
    cex = falsify(fn, target)
    assert cex is not None
    assert cex.args["n"] % 2 == 1  # only odd inputs violate result >= n
    assert cex.failed_clause == "result >= n"


def test_correct_code_survives_search():
    path = EXAMPLES / "arithmetic.py"
    for name in ("max2", "int_abs", "double", "clamp", "is_ge", "bool_xor"):
        target = _target(path, name)
        fn = load_function(path, name)
        assert falsify(fn, target, trials=500) is None, name


def test_precondition_filters_inputs():
    # double's `result % 2 == 0` and `result >= n` hold only under n >= 0
    # coincidentally for the former; the falsifier must discard inputs that
    # violate @requires instead of reporting them as counterexamples.
    path = EXAMPLES / "arithmetic.py"
    target = _target(path, "double")
    fn = load_function(path, "double")
    assert falsify(fn, target) is None


def test_nonterminating_call_aborts_search_instead_of_hanging(tmp_path):
    source = """
from axiomprover import ensures

@ensures(lambda n, result: result >= 0)
def spin(n: int) -> int:
    total = 0
    while n > 0:  # ~2**31 iterations on boundary inputs
        total += n
        n -= 1
    return total
"""
    path = tmp_path / "spin.py"
    path.write_text(source)
    target = _target(path, "spin")
    fn = load_function(path, "spin")
    # Must return (no verdict), not hang: non-termination is not refutation.
    assert falsify(fn, target, call_timeout=0.2) is None


def test_crash_on_legal_input_is_a_counterexample(tmp_path):
    source = """
from axiomprover import ensures

@ensures(lambda n, result: result >= 0)
def crashy(n: int) -> int:
    return 10 // n
"""
    path = tmp_path / "crashy.py"
    path.write_text(source)
    target = _target(path, "crashy")
    fn = load_function(path, "crashy")
    cex = falsify(fn, target)
    assert cex is not None
    assert cex.args["n"] == 0
    assert "must not raise" in cex.failed_clause
