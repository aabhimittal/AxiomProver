"""Industrial-flavored bugs — plausible ports and refactors that are wrong.

Each of these mirrors a real bug class from production code. All are
expected to come back REFUTED with a concrete witness (exit code 1):

    axiomprover verify examples/industrial_buggy.py
"""

from axiomprover import ensures, requires


@requires(lambda value, total: total >= 1)
@ensures(lambda value, total, result: 0 <= result and result <= 100)
def percentage_buggy(value: int, total: int) -> int:
    # The spec forgot to require 0 <= value <= total — billing code meets
    # refunds (negative values) and over-delivery (value > total) eventually.
    return value * 100 // total


@ensures(lambda a, b, result: -32768 <= result and result <= 32767)
def saturating_add16_buggy(a: int, b: int) -> int:
    # Clamps the top but not the bottom — the negative overflow path is the
    # one nobody's unit test exercises.
    if a + b > 32767:
        return 32767
    return a + b


@ensures(lambda h, result: 0 <= result and result <= 23)
def wrap_hour_c_port_buggy(h: int) -> int:
    # A faithful port of C's truncating division: for negative hours the
    # "remainder" is negative. Python's own h % 24 would have been correct —
    # the port preserved the bug the original C had.
    if h >= 0:
        q = h // 24
    else:
        q = -((-h) // 24)
    return h - q * 24
