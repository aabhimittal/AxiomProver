"""Industrial edge cases — the shapes that ship in real systems.

Saturation arithmetic, modular wraparound, fixed-window loops, branchless
tricks, calendar logic: exactly the dense little functions that get pasted
out of an LLM into firmware and billing code, and exactly where subtle
semantic bugs live (negative operands, boundary values, division rounding).

Everything here is expected to come back VERIFIED:

    axiomprover verify examples/industrial.py
"""

from axiomprover import ensures, requires


# --- saturation / clamping (control systems, DSP, quantization) -----------

@requires(lambda a, b, lo, hi: lo <= hi)
@ensures(lambda a, b, lo, hi, result: lo <= result and result <= hi)
@ensures(lambda a, b, lo, hi, result: result == a + b or result == lo or result == hi)
def saturating_add(a: int, b: int, lo: int, hi: int) -> int:
    return min(max(a + b, lo), hi)


@ensures(lambda duty, result: 0 <= result and result <= 255)
@ensures(lambda duty, result: duty < 0 or duty > 255 or result == duty)
def pwm_clamp(duty: int) -> int:
    if duty < 0:
        return 0
    if duty > 255:
        return 255
    return duty


# --- modular arithmetic (hashing, ring buffers, calendars) -----------------

@ensures(lambda n, result: 0 <= result and result <= 7)
def hash_bucket(n: int) -> int:
    # The C-port footgun: in C, n % 8 is negative for negative n. Python's
    # floor semantics (and the Lean model) keep the result in [0, 8) for
    # ALL n — note there is no @requires(n >= 0) here, and the proof still
    # goes through.
    return n % 8


@ensures(lambda day, delta, result: 0 <= result and result <= 6)
def wrap_weekday(day: int, delta: int) -> int:
    return (day + delta) % 7


@ensures(
    lambda y, result: result
    == ((y % 4 == 0 and y % 100 != 0) or y % 400 == 0)
)
def is_leap_year(y: int) -> bool:
    if y % 400 == 0:
        return True
    if y % 100 == 0:
        return False
    return y % 4 == 0


# --- division and rounding (metering, billing, sensor scaling) -------------

@requires(lambda a, b, c, d: a >= 0 and b >= 0 and c >= 0 and d >= 0)
@ensures(lambda a, b, c, d, result: result >= 0)
@ensures(lambda a, b, c, d, result: 4 * result <= a + b + c + d)
@ensures(lambda a, b, c, d, result: a + b + c + d < 4 * result + 4)
def window_average(a: int, b: int, c: int, d: int) -> int:
    return (a + b + c + d) // 4


@requires(lambda c: c >= -273)
@ensures(lambda c, result: result >= -460)
def celsius_to_fahrenheit(c: int) -> int:
    return c * 9 // 5 + 32


# --- branchless tricks proven against reference implementations ------------

def reference_min(a: int, b: int) -> int:
    # No contract: this helper exists to be inlined into specs below.
    if a <= b:
        return a
    return b


@ensures(lambda a, b, result: result == reference_min(a, b))
@ensures(lambda a, b, result: result == min(a, b))
def branchless_min(a: int, b: int) -> int:
    # (a + b - |a - b|) / 2 — the classic. The dividend is always even, so
    # floor division is exact; the kernel checks that reasoning, not us.
    return (a + b - abs(a - b)) // 2


@ensures(lambda x, result: result == abs(x))
@ensures(lambda x, result: result >= 0)
def branchless_abs_via_double_negate(x: int) -> int:
    return max(x, -x)


# --- fixed-iteration loops (checksums, unrolled kernels) -------------------

@ensures(lambda result: result == 55)
def sum_first_ten() -> int:
    total = 0
    for i in range(1, 11):
        total += i
    return total


@requires(lambda x: 0 <= x and x <= 15)
@ensures(lambda x, result: result == 16 * x)
def times_sixteen_by_doubling(x: int) -> int:
    acc = x
    for _round in range(4):
        acc = acc + acc
    return acc


@requires(lambda seed: 0 <= seed and seed <= 99)
@ensures(lambda seed, result: 0 <= result and result <= 99)
def lcg_four_steps(seed: int) -> int:
    # Four rounds of a tiny linear congruential generator; the state bound
    # is an invariant the kernel re-establishes through every unrolled step.
    state = seed
    for _step in range(4):
        state = (state * 21 + 7) % 100
    return state
