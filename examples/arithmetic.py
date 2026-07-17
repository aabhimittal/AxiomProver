"""Contracted functions in the supported subset.

Every function here is the kind of small, self-contained unit an LLM emits
constantly — and each carries a machine-checkable contract. Run:

    axiomprover verify examples/arithmetic.py
"""

from axiomprover import ensures, requires


@ensures(lambda a, b, result: result >= a and result >= b)
@ensures(lambda a, b, result: result == a or result == b)
def max2(a: int, b: int) -> int:
    if a >= b:
        return a
    return b


@ensures(lambda n, result: result >= 0)
@ensures(lambda n, result: result == n or result == -n)
def int_abs(n: int) -> int:
    if n < 0:
        return -n
    return n


@requires(lambda n: n >= 0)
@ensures(lambda n, result: result >= n)
@ensures(lambda n, result: result % 2 == 0)
def double(n: int) -> int:
    return n + n


@ensures(lambda x, lo, hi, result: result == x or result == lo or result == hi)
def clamp(x: int, lo: int, hi: int) -> int:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


@requires(lambda lo, hi: lo <= hi)
@ensures(lambda lo, hi, result: lo <= result and result <= hi)
def clamp_zero(lo: int, hi: int) -> int:
    x = 0
    if x < lo:
        x = lo
    if x > hi:
        x = hi
    return x


@ensures(lambda a, b, result: result == (a >= b))
def is_ge(a: int, b: int) -> bool:
    return a >= b


@ensures(lambda a, b, result: result == (a != b))
def bool_xor(a: bool, b: bool) -> bool:
    return (a or b) and not (a and b)


@requires(lambda n: n >= 0)
@ensures(lambda n, result: 0 <= result and result <= 9)
def last_digit(n: int) -> int:
    return n % 10
