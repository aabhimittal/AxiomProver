"""Plausible-looking code with real bugs — the case AxiomProver exists for.

Each function below passes casual spot-checks and would sail through a thin
test suite, yet violates its contract on inputs a reviewer is unlikely to
try. `axiomprover verify examples/buggy.py` refutes all three with concrete
witnesses (exit code 1, so CI fails).
"""

from axiomprover import ensures, requires


@ensures(lambda a, b, result: result >= a and result >= b)
@ensures(lambda a, b, result: result == a or result == b)
def max2_buggy(a: int, b: int) -> int:
    # Classic LLM off-by-strictness: ties return b... which is fine, but the
    # comparison direction below is inverted for negatives-only inputs.
    if a > 0 and a >= b:
        return a
    return b


@ensures(lambda a, b, result: result == ((a >= 0) == (b >= 0)))
def same_sign_buggy(a: int, b: int) -> bool:
    # The product trick is the first thing autocomplete reaches for, and it
    # is wrong the moment either argument is zero.
    return a * b > 0


@requires(lambda n: n >= 0)
@ensures(lambda n, result: result % 2 == 0)
@ensures(lambda n, result: result >= n)
def round_up_to_even_buggy(n: int) -> int:
    # "Round up to the nearest even number" — except for odd n this rounds
    # *down*, violating result >= n on every odd input.
    return n - n % 2
