"""Contract decorators.

These are deliberately boring: they attach metadata to the function object and
return it unchanged. The static pipeline reads the *source* of the lambdas via
`ast`; the dynamic falsifier calls the attached lambdas directly. Nothing here
alters runtime behavior of the decorated function.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

REQUIRES_ATTR = "__axiom_requires__"
ENSURES_ATTR = "__axiom_ensures__"
PROOF_ATTR = "__axiom_proof__"


def requires(predicate: Callable[..., bool]) -> Callable[[F], F]:
    """Declare a precondition.

    The predicate must accept exactly the decorated function's parameters and
    return a boolean. Verification only promises the postconditions on inputs
    satisfying every precondition.
    """

    def wrap(fn: F) -> F:
        if not hasattr(fn, REQUIRES_ATTR):
            setattr(fn, REQUIRES_ATTR, [])
        getattr(fn, REQUIRES_ATTR).append(predicate)
        return fn

    return wrap


def ensures(predicate: Callable[..., bool]) -> Callable[[F], F]:
    """Declare a postcondition.

    The predicate must accept the decorated function's parameters plus a final
    ``result`` parameter. Each `ensures` clause becomes one Lean theorem.
    """

    def wrap(fn: F) -> F:
        if not hasattr(fn, ENSURES_ATTR):
            setattr(fn, ENSURES_ATTR, [])
        getattr(fn, ENSURES_ATTR).append(predicate)
        return fn

    return wrap


def proof(tactic_script: str) -> Callable[[F], F]:
    """Supply a Lean tactic script to try before the built-in strategy chain.

    Use this when automation (`omega`, `simp`, ...) cannot close the goal on
    its own — e.g. nonlinear arithmetic. The script is used verbatim as the
    body of ``by`` in the generated theorem.
    """

    def wrap(fn: F) -> F:
        setattr(fn, PROOF_ATTR, tactic_script)
        return fn

    return wrap
