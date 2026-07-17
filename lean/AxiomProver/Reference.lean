/-!
# Reference models

Hand-written versions of what the translator generates, kept as a regression
anchor: if these stop compiling on a toolchain bump, generated artifacts
would too. `lake build` checks this file in CI.

Each pair below mirrors `examples/arithmetic.py`.
-/

set_option linter.unusedVariables false

/-!
## Semantic pins

The translator maps Python's `// k` / `% k` (literal `k ≥ 1`) to Lean's
`/` / `%` notation on `Int`, relying on that notation being *Euclidean*
division — which coincides with Python's floor division for positive
divisors. If a toolchain ever changes what the notation means (e.g. to
truncating division, where `(-7) % 2 = -1`), these examples fail the build
instead of letting the translator silently model the wrong function.
-/

example : (-7 : Int) % 2 = 1 := by decide
example : (-7 : Int) / 2 = -4 := by decide
example : (7 : Int) % 2 = 1 := by decide
example : (7 : Int) / 2 = 3 := by decide

-- ...and omega must be able to reason about the notation form, since the
-- strategy chain leans on it for every function using `// k` / `% k`.
example (n : Int) : (n + n) % 2 = 0 := by omega
example (n : Int) (_h : n ≥ 0) : 0 ≤ n % 10 ∧ n % 10 ≤ 9 := by omega

-- max2: `if a >= b: return a` / `return b`
def max2 (a : Int) (b : Int) : Int :=
  (if (a ≥ b) then a else b)

theorem max2_spec_1 (a : Int) (b : Int) :
    ((max2 a b) ≥ a ∧ (max2 a b) ≥ b) := by
  simp only [max2]; split <;> (try split) <;> (try split) <;> omega

theorem max2_spec_2 (a : Int) (b : Int) :
    ((max2 a b) = a ∨ (max2 a b) = b) := by
  simp only [max2]; split <;> (try split) <;> (try split) <;> omega

-- int_abs with sequential ifs and inlined assignment
def int_abs (n : Int) : Int :=
  (if (n < 0) then (-n) else n)

theorem int_abs_spec_1 (n : Int) : ((int_abs n) ≥ 0) := by
  simp only [int_abs]; split <;> (try split) <;> (try split) <;> omega

-- double, with a precondition hypothesis and %-by-literal in the goal
-- (Python `% k` with a literal k >= 1 is modeled with Lean's `%` notation,
-- which omega understands; Int.fmod is reserved for non-literal divisors
-- and is beyond omega — see examples/limits.py)
def double (n : Int) : Int :=
  (n + n)

theorem double_spec_1 (n : Int) (_h1 : (n ≥ 0)) : ((double n) ≥ n) := by
  simp only [double]; try omega

theorem double_spec_2 (n : Int) (_h1 : (n ≥ 0)) :
    (((double n) % 2) = 0) := by
  simp only [double]; try omega

-- Bool-valued result modeled via `decide`
def is_ge (a : Int) (b : Int) : Bool :=
  (decide (a ≥ b))

theorem is_ge_spec_1 (a : Int) (b : Int) :
    ((is_ge a b) = (decide (a ≥ b))) := by
  simp [is_ge]

-- Bool parameters discharged by exhaustive cases + decide
def bool_xor (a : Bool) (b : Bool) : Bool :=
  ((a || b) && (!(a && b)))

theorem bool_xor_spec_1 (a : Bool) (b : Bool) :
    ((bool_xor a b) = (decide (a ≠ b))) := by
  simp only [bool_xor]; cases a <;> cases b <;> decide
