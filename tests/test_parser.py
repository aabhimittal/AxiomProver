import pytest

from axiomprover.parser import SpecSyntaxError, parse_source


def test_extracts_contracted_function():
    targets = parse_source(
        """
from axiomprover import ensures, requires

@requires(lambda n: n >= 0)
@ensures(lambda n, result: result >= n)
def double(n: int) -> int:
    return n + n

def helper(x: int) -> int:  # no contract: ignored
    return x
"""
    )
    assert len(targets) == 1
    t = targets[0]
    assert t.name == "double"
    assert t.params == [("n", "int")]
    assert t.return_type == "int"
    assert len(t.requires) == 1
    assert len(t.ensures) == 1
    assert t.ensures[0].source == "result >= n"


def test_multiple_ensures_kept_in_source_order():
    targets = parse_source(
        """
from axiomprover import ensures

@ensures(lambda a, b, result: result >= a)
@ensures(lambda a, b, result: result >= b)
def f(a: int, b: int) -> int:
    return a + b
"""
    )
    assert [c.source for c in targets[0].ensures] == ["result >= a", "result >= b"]


def test_proof_hint():
    targets = parse_source(
        """
from axiomprover import ensures, proof

@proof("simp [square]; nlinarith")
@ensures(lambda x, result: result >= 0)
def square(x: int) -> int:
    return x * x
"""
    )
    assert targets[0].proof_hint == "simp [square]; nlinarith"


def test_qualified_decorator_names():
    targets = parse_source(
        """
import axiomprover

@axiomprover.ensures(lambda n, result: result == n)
def ident(n: int) -> int:
    return n
"""
    )
    assert len(targets) == 1


def test_ensures_lambda_params_must_match():
    with pytest.raises(SpecSyntaxError, match="plus 'result'"):
        parse_source(
            """
from axiomprover import ensures

@ensures(lambda n: n >= 0)
def f(n: int) -> int:
    return n
"""
        )


def test_requires_lambda_params_must_match():
    with pytest.raises(SpecSyntaxError, match="exactly the function"):
        parse_source(
            """
from axiomprover import ensures, requires

@requires(lambda m: m >= 0)
@ensures(lambda n, result: result >= 0)
def f(n: int) -> int:
    return n
"""
        )


def test_non_lambda_spec_rejected():
    with pytest.raises(SpecSyntaxError, match="lambda literal"):
        parse_source(
            """
from axiomprover import ensures

pred = lambda n, result: result >= 0

@ensures(pred)
def f(n: int) -> int:
    return n
"""
        )


def test_unannotated_params_rejected():
    with pytest.raises(SpecSyntaxError, match="must be annotated"):
        parse_source(
            """
from axiomprover import ensures

@ensures(lambda n, result: result >= 0)
def f(n) -> int:
    return n
"""
        )


def test_unsupported_type_rejected():
    with pytest.raises(SpecSyntaxError, match="return type"):
        parse_source(
            """
from axiomprover import ensures

@ensures(lambda s, result: result >= 0)
def f(s: int) -> str:
    return "x"
"""
        )
