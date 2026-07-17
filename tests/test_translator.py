import pytest

from axiomprover.parser import parse_source
from axiomprover.translator import UnsupportedError, translate_function


def translate(source: str):
    targets = parse_source(source)
    assert len(targets) == 1
    return translate_function(targets[0])


def test_straight_line_function():
    module = translate(
        """
from axiomprover import ensures, requires

@requires(lambda n: n >= 0)
@ensures(lambda n, result: result >= n)
def double(n: int) -> int:
    return n + n
"""
    )
    assert module.definition == (
        "def double (n : Int) : Int :=\n  (n + n)"
    )
    assert len(module.theorems) == 1
    assert module.theorems[0].statement == (
        "theorem double_spec_1 (n : Int) (_h1 : (n ≥ 0)) :\n"
        "    ((double n) ≥ n)"
    )


def test_branching_becomes_ite():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda a, b, result: result >= a)
def max2(a: int, b: int) -> int:
    if a >= b:
        return a
    return b
"""
    )
    assert "(if (a ≥ b) then a else b)" in module.definition


def test_assignment_is_inlined():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda n, result: result >= n)
def f(n: int) -> int:
    x = n + 1
    y = x + x
    return y
"""
    )
    assert "((n + 1) + (n + 1))" in module.definition


def test_augmented_assignment_and_reassignment():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda n, result: result == 2 * n + 3)
def f(n: int) -> int:
    x = n
    x += n + 3
    return x
"""
    )
    assert "(n + (n + 3))" in module.definition


def test_branch_fallthrough_duplicates_continuation():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    if n < 0:
        n = -n
    return n
"""
    )
    assert module.definition == (
        "def f (n : Int) : Int :=\n  (if (n < 0) then (-n) else n)"
    )


def test_division_by_positive_literal_uses_notation():
    # For a literal divisor >= 1, Python floor division/modulo coincide with
    # Lean's Euclidean `/`/`%` notation on Int, which omega reasons about
    # (raw Int.ediv/Int.emod constants are invisible to omega's frontend).
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda n, result: result <= n or n < 0)
def f(n: int) -> int:
    x = n // 2
    return x % 10
"""
    )
    assert "((n / 2) % 10)" in module.definition
    assert "Int.ediv" not in module.definition
    assert "Int.emod" not in module.definition


def test_division_by_variable_or_negative_literal_maps_to_floor():
    # Floor and Euclidean division disagree for negative divisors, so the
    # faithful (if automation-hostile) fdiv/fmod model is kept there.
    module = translate(
        """
from axiomprover import ensures, requires

@requires(lambda a, b: b != 0)
@ensures(lambda a, b, result: result == result)
def f(a: int, b: int) -> int:
    x = a // b
    return x % -3
"""
    )
    assert "Int.fdiv a b" in module.definition
    assert "Int.fmod (Int.fdiv a b) (-3)" in module.definition


def test_bool_result_uses_decide():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda a, b, result: result == (a >= b))
def is_ge(a: int, b: int) -> bool:
    return a >= b
"""
    )
    assert "(decide (a ≥ b))" in module.definition
    assert module.bool_params == []


def test_bool_params_tracked_in_order():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda a, b, result: result == (a != b))
def bool_xor(a: bool, b: bool) -> bool:
    return (a or b) and not (a and b)
"""
    )
    assert module.bool_params == ["a", "b"]
    assert "((a || b) && (!(a && b)))" in module.definition


def test_spec_connectives_become_prop_connectives():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda a, b, result: result >= a and result >= b)
def max2(a: int, b: int) -> int:
    if a >= b:
        return a
    return b
"""
    )
    goal = module.theorems[0].statement
    assert "∧" in goal and "and" not in goal.split(":")[-1]


def test_chained_comparison_in_spec():
    module = translate(
        """
from axiomprover import ensures, requires

@requires(lambda lo, hi: lo <= hi)
@ensures(lambda lo, hi, result: lo <= result <= hi)
def f(lo: int, hi: int) -> int:
    return lo
"""
    )
    goal = module.theorems[0].statement
    assert "lo ≤ (f lo hi) ∧ (f lo hi) ≤ hi" in goal


def test_lean_keyword_parameter_is_mangled():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda then, result: result == then)
def f(then: int) -> int:
    return then
"""
    )
    assert "py_then" in module.definition


@pytest.mark.parametrize(
    "body, message",
    [
        ("    while n > 0:\n        n -= 1\n    return n", "While"),
        ("    return len(str(n))", "Call"),
        ("    return n / 2", "float division"),
        ("    return [n]", "List"),
        ("    for i in range(n):\n        pass\n    return n", "For"),
    ],
)
def test_unsupported_constructs_rejected(body, message):
    source = (
        "from axiomprover import ensures\n"
        "@ensures(lambda n, result: result >= 0)\n"
        "def f(n: int) -> int:\n"
        f"{body}\n"
    )
    with pytest.raises(UnsupportedError, match=message):
        translate(source)


def test_missing_return_rejected():
    with pytest.raises(UnsupportedError, match="fall off the end"):
        translate(
            """
from axiomprover import ensures

@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    x = n + 1
"""
        )


def test_render_pairs_theorems_with_tactics():
    module = translate(
        """
from axiomprover import ensures

@ensures(lambda n, result: result >= n)
@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    if n >= 0:
        return n
    return 0
"""
    )
    rendered = module.render(["omega_a", "omega_b"])
    assert "f_spec_1" in rendered and "f_spec_2" in rendered
    assert rendered.index("omega_a") < rendered.index("omega_b")
