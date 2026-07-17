"""Proof search strategy chain.

Each strategy is a complete tactic script for one theorem. They are tried in
order until the Lean kernel accepts one. Soundness does not depend on this
list: a bad tactic yields a rejected proof, never a wrong VERIFIED verdict —
so the chain is free to be opportunistic.

Notes on the shape of the scripts:

- `simp only [f]` unfolds the model; `try omega` then discharges linear
  integer arithmetic (and the `try` absorbs the no-goals error when `simp`
  already closed everything).
- `split <;> (try split) <;> (try split)` flattens `if _ then _ else _`
  up to three levels deep before handing each leaf to `omega`; `omega`
  itself does not case-split on `ite`.
- Bool-valued goals arrive as `... = true` equations; `decide_eq_true_eq`,
  `Bool.and_eq_true`, `Bool.or_eq_true` lift them back into `Prop`.
- For Bool parameters, exhaustive `cases` turns the goal into finitely many
  closed instances that `decide` can evaluate.

`native_decide` is deliberately absent — it extends the trusted computing
base from the ~10k-line kernel to the whole Lean compiler and C toolchain,
which defeats the point of kernel-checked verification.
"""

from __future__ import annotations

from axiomprover.translator import LeanModule, lean_name

_SPLIT3 = "split <;> (try split) <;> (try split)"
_BOOL_LEMMAS = "decide_eq_true_eq, Bool.and_eq_true, Bool.or_eq_true"


def strategies_for(module: LeanModule) -> list[str]:
    """Ordered tactic scripts to attempt for each theorem of *module*."""
    f = lean_name(module.function_name)
    chain: list[str] = []
    if module.proof_hint:
        chain.append(module.proof_hint)

    chain += [
        f"simp only [{f}]; try omega",
        f"simp only [{f}]; {_SPLIT3} <;> omega",
        f"simp only [{f}, {_BOOL_LEMMAS}]; try omega",
        f"simp only [{f}, {_BOOL_LEMMAS}]; {_SPLIT3} <;> omega",
    ]

    if module.bool_params:
        cases = " <;> ".join(f"cases {lean_name(p)}" for p in module.bool_params)
        chain += [
            f"simp only [{f}]; {cases} <;> decide",
            f"simp only [{f}]; {cases} <;> simp_all <;> try omega",
        ]

    chain += [
        f"simp [{f}]",
        f"simp_all [{f}]",
        f"unfold {f}; rfl",
    ]
    return chain
