# AxiomProver

**Lean-based formal verification of AI-generated code.**

Tests can only prove the *absence of observed errors*. AxiomProver takes small
AI-generated Python functions with declared contracts, models them in Lean 4's
type theory, and asks the **Lean kernel** to certify — with a machine-checkable
proof — that the contract holds for **all** inputs, not just sampled ones.

```python
from axiomprover import ensures, requires

@requires(lambda lo, hi: lo <= hi)
@ensures(lambda lo, hi, result: lo <= result and result <= hi)
def clamp_zero(lo: int, hi: int) -> int:
    x = 0
    if x < lo:
        x = lo
    if x > hi:
        x = hi
    return x
```

```console
$ axiomprover verify examples/arithmetic.py
[✓] clamp_zero: VERIFIED
    all ensures clauses kernel-checked for all inputs
    - ensures lo <= result and result <= hi  [proved]
      by simp only [clamp_zero]; split <;> (try split) <;> (try split) <;> omega
    lean: examples/.axiomprover/clamp_zero.lean
```

The emitted `.lean` file is a standalone, re-checkable certificate.

## What this is — and what it is not

Being direct about the epistemics, because the value of the tool depends on it:

- **You cannot "verify Python in Lean."** AxiomProver *models* the semantic
  behavior of the Python function as a Lean definition, proves theorems about
  that model, and trusts that the translation faithfully captures the original
  semantics. That trust — the **translation gap** — is the Achilles' heel of
  the whole approach, so the translator is deliberately tiny, explicit, and
  auditable (see [The supported subset](#the-supported-subset)), and every
  generated artifact embeds the model right next to the theorems so a human
  can diff it against the source.
- **The trusted computing base is small.** A `VERIFIED` verdict rests on:
  the Lean kernel (a small, battle-tested C++ core — everything else in Lean,
  including all tactics, is *untrusted* search that merely produces terms the
  kernel re-checks), plus AxiomProver's translation rules, plus your reading
  of the contract. Notably **not** trusted: the tactic strategies, the LLM
  that wrote the code, and the test suite you didn't write. `native_decide`
  is deliberately never used — it would extend trust to the whole compiler.
- **Verdicts never round up.** Testing can refute; only the kernel can
  verify; everything else is honestly `UNKNOWN` or `UNSUPPORTED`.

## Verdicts

| Verdict | Meaning | Who says so |
|---|---|---|
| `VERIFIED` | every `@ensures` holds for **all** inputs satisfying `@requires` | Lean kernel |
| `REFUTED` | concrete counterexample included in the report | execution |
| `UNKNOWN` | modeled, but no tactic closed the goal — **not** a correctness claim | proof search gave up |
| `UNSUPPORTED` | outside the translatable subset; nothing was modeled or checked | translator |
| `ERROR` | environment problem (no `lean`, timeout, module crashed on import) | pipeline |

Exit codes: `0` all verified · `1` something refuted · `3` gaps (unknown /
unsupported / error) — so `axiomprover verify` drops straight into CI.

## Pipeline

```
             ┌──────────────┐   counterexample   ┌─────────┐
  parse ───► │  falsifier   ├───────────────────►│ REFUTED │
  (ast,      │ (execution:  │                    └─────────┘
   static)   │ refute only) │
             └──────┬───────┘
                    │ survived boundary + random search
                    ▼
             ┌──────────────┐   outside subset   ┌─────────────┐
             │  translator  ├───────────────────►│ UNSUPPORTED │
             │ (Python→Lean │                    └─────────────┘
             │    model)    │
             └──────┬───────┘
                    │ definition + one theorem per @ensures
                    ▼
             ┌──────────────┐   no tactic won    ┌─────────┐
             │ proof search │───────────────────►│ UNKNOWN │ (+ .lean with sorry)
             │ (strategy    │                    └─────────┘
             │    chain)    │
             └──────┬───────┘
                    │ kernel accepts final combined artifact
                    ▼
               ┌──────────┐
               │ VERIFIED │  + standalone re-checkable .lean certificate
               └──────────┘
```

The falsifier runs *first*: a cheap concrete witness beats an expensive proof
attempt, and it works even for functions the translator can't model. The
proof search tries an ordered chain of tactic scripts (`omega` after
unfolding, `if`-splitting, Bool case analysis, `simp`…) — unsound strategies
are impossible by construction, since every candidate proof is re-checked by
the kernel. A `@proof("…")` decorator injects your own tactic script at the
front of the chain for goals automation can't reach (e.g. nonlinear
arithmetic).

## Install & use

```bash
pip install -e .
axiomprover check-env                 # is a Lean 4 toolchain visible?
axiomprover verify examples/arithmetic.py
axiomprover verify examples/buggy.py  # exit 1, with counterexamples
axiomprover translate mycode.py       # just print the Lean model
```

Verification needs Lean 4 (≥ 4.6, for core `omega`; the repo pins
`v4.15.0` in `lean/lean-toolchain`). Install via
[elan](https://leanprover-community.github.io/get_started.html); no mathlib
required — generated files depend only on the Lean prelude. Without Lean,
translation and refutation still work; `VERIFIED` is simply unreachable.

## The supported subset

The translator accepts a purely functional core of Python and **refuses
everything else** — a wrong model would be worse than no model.

| Python | Lean model | Note |
|---|---|---|
| `int` | `Int` | both unbounded: no overflow gap |
| `bool` | `Bool` | |
| `+ - *`, unary `-` | same on `Int` | |
| `// k`, `% k` (literal `k ≥ 1`) | Lean's `/`, `%` (Euclidean) | floor and Euclidean division coincide for positive divisors, and `omega` reasons about the notation by literals; `lean/AxiomProver/Reference.lean` pins the notation's semantics with kernel-checked examples |
| `//`, `%` (other divisors) | `Int.fdiv`, `Int.fmod` | floor-based like Python (Lean's naive `Int.div` truncates — the obvious model would be *wrong* on negatives); beyond `omega`, so expect `UNKNOWN`. Lean division is total (`x // 0 = 0`) where Python raises — the falsifier covers that gap by treating a raise on legal inputs as refutation |
| comparisons (incl. chained) | `Prop` (or `decide (…)` as a value) | |
| `if` / `elif` / `else` / ternary | `if _ then _ else _` | |
| (re)assignment, `+=` … | inlined by substitution | body becomes one pure expression |
| `and or not` in contracts | `∧ ∨ ¬` | |

Not yet: loops, recursion, calls, strings, floats, containers, exceptions.
That's the honest cost of a small trusted translator; the subset is still
enough for the dense little functions LLMs get subtly wrong (see
`examples/buggy.py` — all three look plausible and all three are refuted
with witnesses like `same_sign(0, 0)`).

`examples/limits.py` shows the other honest edge: true contracts that
automation can't prove (nonlinear arithmetic) stay `UNKNOWN`, and the tool
emits the goal with `sorry` for a human to finish rather than pretending.

## Repository layout

```
src/axiomprover/     the pipeline: parser → falsifier → translator → strategies → runner
examples/            arithmetic.py (all VERIFIED) · buggy.py (all REFUTED) · limits.py (all UNKNOWN)
lean/                pinned toolchain + hand-written reference models (regression anchor, `lake build` in CI)
tests/               unit + verdict-logic tests (no Lean needed) and kernel integration tests (skip without Lean)
```

CI runs both halves: the Python matrix without Lean, and an end-to-end job
that installs the pinned toolchain, `lake build`s the reference models, and
requires `examples/arithmetic.py` to come back fully `VERIFIED` — and
`examples/limits.py` to *not* be.

## Roadmap

- **Recursion** via structural recursion on `Nat`, with termination goals
  surfaced instead of hidden.
- **Loops** as invariant-annotated folds (`@invariant(...)`).
- **LLM-in-the-loop proof repair**: feed the kernel's error back to a model
  to propose the next tactic — safe by construction, since every attempt is
  kernel-checked.
- **Calls between contracted functions**, using the callee's `@ensures` as
  lemmas.
- Verified translation validation (shrinking the translation gap with
  differential testing between CPython and compiled Lean models).

## License

MIT — see [LICENSE](LICENSE).
