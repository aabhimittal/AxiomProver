"""Unit tests for v0.2 features: call inlining, loop unrolling, builtins,
and depth-adaptive strategies — plus torture cases at the subset's edges."""

import pytest
from conftest import EXAMPLES

from axiomprover.parser import parse_file, parse_source
from axiomprover.strategies import strategies_for
from axiomprover.translator import (
    MAX_UNROLL,
    UnsupportedError,
    translate_function,
)


def translate(source: str, name: str | None = None):
    targets = parse_source(source)
    if name is None:
        assert len(targets) == 1
        return translate_function(targets[0])
    return translate_function(next(t for t in targets if t.name == name))


HEADER = "from axiomprover import ensures, requires\n"


# --- call inlining ---------------------------------------------------------


def test_helper_call_is_inlined():
    module = translate(
        HEADER
        + """
def double(x: int) -> int:
    return x + x

@ensures(lambda n, result: result == 4 * n)
def quadruple(n: int) -> int:
    return double(double(n))
""",
        name="quadruple",
    )
    assert module.definition == (
        "def quadruple (n : Int) : Int :=\n  ((n + n) + (n + n))"
    )


def test_call_in_spec_is_inlined():
    module = translate(
        HEADER
        + """
def reference(a: int, b: int) -> int:
    if a <= b:
        return a
    return b

@ensures(lambda a, b, result: result == reference(a, b))
def branchless(a: int, b: int) -> int:
    return (a + b - abs(a - b)) // 2
""",
        name="branchless",
    )
    goal = module.theorems[0].statement
    assert "(if (a ≤ b) then a else b)" in goal


def test_argument_expressions_substitute_for_parameters():
    module = translate(
        HEADER
        + """
def add(a: int, b: int) -> int:
    return a + b

@ensures(lambda n, result: result == 3 * n + 5)
def f(n: int) -> int:
    return add(n + n, add(n, 5))
""",
        name="f",
    )
    assert "((n + n) + (n + 5))" in module.definition


def test_direct_recursion_refused():
    with pytest.raises(UnsupportedError, match="recursive call chain"):
        translate(
            HEADER
            + """
@ensures(lambda n, result: result >= 0)
def fact(n: int) -> int:
    if n <= 1:
        return 1
    return n * fact(n - 1)
"""
        )


def test_mutual_recursion_refused():
    with pytest.raises(UnsupportedError, match="is_even -> is_odd -> is_even"):
        translate(
            HEADER
            + """
def is_odd(n: int) -> int:
    if n == 0:
        return 0
    return is_even(n - 1)

@ensures(lambda n, result: result >= 0)
def is_even(n: int) -> int:
    if n == 0:
        return 1
    return is_odd(n - 1)
""",
            name="is_even",
        )


def test_callee_arity_mismatch_refused():
    with pytest.raises(UnsupportedError, match="expected 2"):
        translate(
            HEADER
            + """
def add(a: int, b: int) -> int:
    return a + b

@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    return add(n)
""",
            name="f",
        )


def test_unknown_function_call_refused():
    with pytest.raises(UnsupportedError, match="not a module function"):
        translate(
            HEADER
            + """
@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    return len(str(n))
"""
        )


# --- builtins --------------------------------------------------------------


def test_min_max_abs_desugar_to_ite():
    module = translate(
        HEADER
        + """
@ensures(lambda a, b, result: result <= a and result <= b)
def f(a: int, b: int) -> int:
    return min(a, b) + max(a, b) - abs(a) + abs(b) - max(a, b)
"""
    )
    assert "(if a ≤ b then a else b)" in module.definition
    assert "(if a ≥ b then a else b)" in module.definition
    assert "(if a < 0 then (-a) else a)" in module.definition


def test_min_with_three_arguments_folds():
    module = translate(
        HEADER
        + """
@ensures(lambda a, b, c, result: result <= a)
def f(a: int, b: int, c: int) -> int:
    return min(a, b, c)
"""
    )
    # min(a, b, c) = min(min(a, b), c): the inner ite becomes the scrutinee
    # of the outer one.
    inner = "(if a ≤ b then a else b)"
    assert f"(if {inner} ≤ c then {inner} else c)" in module.definition


def test_builtin_shadowed_by_local_refused():
    with pytest.raises(UnsupportedError, match="shadowed"):
        translate(
            HEADER
            + """
@ensures(lambda a, b, result: result <= a)
def f(a: int, b: int) -> int:
    min = a
    return min(min, b)
"""
        )


def test_module_function_beats_builtin_name():
    module = translate(
        HEADER
        + """
def abs(x: int) -> int:
    return x

@ensures(lambda n, result: result == n)
def f(n: int) -> int:
    return abs(n)
""",
        name="f",
    )
    # The module's own (identity) abs is inlined; no ite is introduced.
    assert module.definition == "def f (n : Int) : Int :=\n  n"


# --- bounded loops ---------------------------------------------------------


def test_range_loop_unrolls():
    module = translate(
        HEADER
        + """
@ensures(lambda result: result == 6)
def f() -> int:
    total = 0
    for i in range(1, 4):
        total += i
    return total
"""
    )
    assert module.definition == (
        "def f  : Int :=\n  (((0 + 1) + 2) + 3)"
    )


def test_loop_variable_holds_last_value_after_loop():
    module = translate(
        HEADER
        + """
@ensures(lambda result: result == 2)
def f() -> int:
    for i in range(3):
        pass
    return i
"""
    )
    assert module.definition.endswith("2")


def test_nested_loops_unroll():
    module = translate(
        HEADER
        + """
@ensures(lambda result: result == 4)
def f() -> int:
    total = 0
    for i in range(2):
        for j in range(2):
            total += 1
    return total
"""
    )
    assert module.definition == (
        "def f  : Int :=\n  ((((0 + 1) + 1) + 1) + 1)"
    )


def test_return_inside_loop_short_circuits():
    module = translate(
        HEADER
        + """
@ensures(lambda n, result: result <= 3)
def find_first_ge(n: int) -> int:
    for i in range(4):
        if i >= n:
            return i
    return -1
"""
    )
    # Iteration 0's `if` else-branch continues into iteration 1, and so on;
    # the fallthrough -1 survives at the innermost level.
    assert module.definition.count("if") == 4
    assert "(-1)" in module.definition


def test_unroll_budget_enforced():
    with pytest.raises(UnsupportedError, match=f"budget is {MAX_UNROLL}"):
        translate(
            HEADER
            + f"""
@ensures(lambda result: result >= 0)
def f() -> int:
    total = 0
    for i in range({MAX_UNROLL + 1}):
        total += i
    return total
"""
        )


def test_variable_range_bound_refused():
    with pytest.raises(UnsupportedError, match="not an integer literal"):
        translate(
            HEADER
            + """
@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    total = 0
    for i in range(n):
        total += i
    return total
"""
        )


def test_break_refused():
    with pytest.raises(UnsupportedError, match="break/continue"):
        translate(
            HEADER
            + """
@ensures(lambda result: result >= 0)
def f() -> int:
    total = 0
    for i in range(4):
        if total > 2:
            break
        total += i
    return total
"""
        )


def test_negative_step_range_unrolls():
    module = translate(
        HEADER
        + """
@ensures(lambda result: result == 3)
def countdown_sum() -> int:
    total = 0
    for i in range(2, -1, -1):
        total += i
    return total
"""
    )
    assert "((0 + 2) + 1) + 0" in module.definition


# --- strategy depth adapts to case-analysis size ---------------------------


def test_deep_split_strategy_added_for_many_branches():
    module = translate(
        HEADER
        + """
@ensures(lambda x, result: result >= 0)
def staircase(x: int) -> int:
    y = 0
    if x > 1:
        y += 1
    if x > 2:
        y += 1
    if x > 3:
        y += 1
    if x > 4:
        y += 1
    if x > 5:
        y += 1
    return y
"""
    )
    deep = [s for s in strategies_for(module) if s.count("split") >= 5]
    assert deep, "expected a deep split strategy for 5 sequential branches"


# --- torture: scale and naming --------------------------------------------


def test_twenty_parameters_and_large_literals():
    params = ", ".join(f"x{i}: int" for i in range(20))
    lam = ", ".join(f"x{i}" for i in range(20))
    total = " + ".join(f"x{i}" for i in range(20))
    module = translate(
        HEADER
        + f"""
@requires(lambda {lam}: {" and ".join(f"x{i} >= 0" for i in range(20))})
@ensures(lambda {lam}, result: result >= 0)
@ensures(lambda {lam}, result: result >= x19 - 9223372036854775808)
def big({params}) -> int:
    return {total} + 9223372036854775807
"""
    )
    assert "9223372036854775807" in module.definition
    assert len(module.theorems) == 2


def test_lean_keywords_as_parameters_everywhere():
    module = translate(
        HEADER
        + """
def helper(then: int) -> int:
    return then + 1

@ensures(lambda then, result: result == then + 1)
def f(then: int) -> int:
    return helper(then)
""",
        name="f",
    )
    assert "py_then" in module.definition
    assert "then + 1" not in module.definition.replace("py_then", "X")


def test_industrial_examples_parse_and_translate():
    for target in parse_file(EXAMPLES / "industrial.py"):
        module = translate_function(target)
        assert module.theorems, target.name
