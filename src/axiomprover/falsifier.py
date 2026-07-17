"""Counterexample search by execution.

Testing occupies exactly one seat in this pipeline: it can *refute* a
contract with a concrete witness, cheaply and before any Lean is generated.
It can never produce VERIFIED — that verdict is reserved for the kernel.

This is the only module that executes the target file. It runs the module in
a fresh namespace (same trust model as pytest running your test file), then
drives the decorated function on boundary values and random inputs.
"""

from __future__ import annotations

import contextlib
import itertools
import random
import signal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from axiomprover.decorators import ENSURES_ATTR, REQUIRES_ATTR
from axiomprover.parser import TargetFunction

_INT_BOUNDARIES = [0, 1, -1, 2, -2, 3, -3, 7, -7, 10, -10, 100, -100, 2**31, -(2**31)]


@dataclass
class Counterexample:
    args: dict[str, Any]
    result: Any
    failed_clause: str  # source text of the violated ensures clause


def load_function(path: Path, name: str) -> Callable[..., Any]:
    """Execute *path* as a module and return the named function object."""
    namespace: dict[str, Any] = {"__name__": "__axiomprover_target__"}
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, namespace)  # noqa: S102 - user's own file, opt-in execution
    fn = namespace.get(name)
    if not callable(fn):
        raise RuntimeError(f"{path}: executing the module did not produce a function {name!r}")
    return fn


class _CallTimeout(Exception):
    pass


@contextlib.contextmanager
def _deadline(seconds: float):
    """Interrupt a single call after *seconds*. SIGALRM is only available on
    Unix main threads; elsewhere this degrades to no protection, matching
    what test runners like pytest offer by default."""
    can_alarm = hasattr(signal, "SIGALRM") and (
        threading.current_thread() is threading.main_thread()
    )
    if not can_alarm:
        yield
        return
    def _raise_timeout(signum, frame):
        raise _CallTimeout()

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def falsify(
    fn_obj: Callable[..., Any],
    target: TargetFunction,
    trials: int = 2000,
    seed: int = 0,
    call_timeout: float = 2.0,
) -> Counterexample | None:
    """Search for inputs that satisfy every @requires but violate some
    @ensures. Returns the first counterexample found, else None.

    A call exceeding *call_timeout* seconds aborts the whole search: the
    function may be non-terminating on that input, which execution can
    neither confirm nor refute — the verdict is left to later stages.
    """
    requires = getattr(fn_obj, REQUIRES_ATTR, [])
    ensures = getattr(fn_obj, ENSURES_ATTR, [])
    if not ensures:
        return None
    # Decorators apply bottom-up, so runtime order is reversed relative to
    # the source; report clauses using static order via the parsed target.
    ensures = list(reversed(ensures))
    clause_sources = [clause.source for clause in target.ensures]

    rng = random.Random(seed)
    for args in _candidate_inputs(target, trials, rng):
        if not all(_safe_bool(pre, args.values()) for pre in requires):
            continue
        try:
            with _deadline(call_timeout):
                result = fn_obj(*args.values())
        except _CallTimeout:
            return None
        except Exception as exc:  # a crash on a legal input also refutes
            return Counterexample(
                args=args, result=f"raised {type(exc).__name__}: {exc}",
                failed_clause="(function must not raise on inputs satisfying @requires)",
            )
        for post, source in zip(ensures, clause_sources):
            if not _safe_bool(post, [*args.values(), result]):
                return Counterexample(args=args, result=result, failed_clause=source)
    return None


def _safe_bool(predicate: Callable[..., Any], args: Any) -> bool:
    try:
        return bool(predicate(*args))
    except Exception:
        return False


def _candidate_inputs(target: TargetFunction, trials: int, rng: random.Random):
    names = target.param_names
    domains = []
    for _, ty in target.params:
        domains.append([True, False] if ty == "bool" else _INT_BOUNDARIES)

    # Exhaustive boundary grid first (capped), then random search.
    grid = itertools.product(*domains) if names else [()]
    for i, values in enumerate(grid):
        if i >= trials:
            return
        yield dict(zip(names, values))

    for _ in range(trials):
        values = []
        for _, ty in target.params:
            if ty == "bool":
                values.append(rng.choice([True, False]))
            else:
                magnitude = rng.choice([10, 1000, 10**6, 10**12])
                values.append(rng.randint(-magnitude, magnitude))
        yield dict(zip(names, values))
