"""Where the automation honestly stops.

These functions are *correct* and their contracts are *true*, but the
built-in tactic chain cannot prove them (nonlinear integer arithmetic is
undecidable in general; `omega` handles the linear fragment). AxiomProver
reports UNKNOWN — explicitly not a correctness claim — and emits a Lean
artifact with `sorry` placeholders for a human (or a stronger tactic via
@proof) to finish.

This asymmetry is the product working as designed: an unproved truth stays
UNKNOWN; it never gets rounded up to VERIFIED.
"""

from axiomprover import ensures, requires


@ensures(lambda x, result: result >= 0)
def square(x: int) -> int:
    # True, but x*x >= 0 is nonlinear; omega cannot see it.
    return x * x


@requires(lambda total, parts: parts >= 1)
@requires(lambda total, parts: total >= 0)
@ensures(lambda total, parts, result: result * parts <= total)
def even_split(total: int, parts: int) -> int:
    # Floor-division bound with a *variable* divisor — outside omega's
    # decidable fragment (division by a literal would be fine).
    return total // parts
