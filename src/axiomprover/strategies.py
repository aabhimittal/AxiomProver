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

_BOOL_LEMMAS = "decide_eq_true_eq, Bool.and_eq_true, Bool.or_eq_true"

# Beyond this many nested if-then-else splits, case analysis is a lost cause
# (2^16 leaves) — better to give an honest UNKNOWN quickly.
_MAX_SPLIT_DEPTH = 16


def _split_chain(depth: int) -> str:
    """`split` chained through *depth* levels of nested ite; the `try` makes
    shallower branches no-ops instead of failures."""
    return "split" + " <;> (try split)" * max(depth - 1, 0)


def _ite_depth(module: LeanModule) -> int:
    """Upper bound on nested ite depth: every `if ` in the definition and
    goals (sequential ifs become nested through continuation inlining)."""
    text = module.definition + "".join(t.statement for t in module.theorems)
    return min(text.count("if "), _MAX_SPLIT_DEPTH)


def strategies_for(module: LeanModule) -> list[str]:
    """Ordered tactic scripts to attempt for each theorem of *module*."""
    f = lean_name(module.function_name)
    chain: list[str] = []
    if module.proof_hint:
        chain.append(module.proof_hint)

    depth = _ite_depth(module)
    split3 = _split_chain(min(depth, 3) or 1)
    chain += [
        f"simp only [{f}]; try omega",
        f"simp only [{f}]; {split3} <;> omega",
        f"simp only [{f}, {_BOOL_LEMMAS}]; try omega",
        f"simp only [{f}, {_BOOL_LEMMAS}]; {split3} <;> omega",
    ]
    if depth > 3:
        # Deep case analysis for unrolled loops and desugared min/max/abs.
        chain += [
            f"simp only [{f}]; {_split_chain(depth)} <;> omega",
            f"simp only [{f}, {_BOOL_LEMMAS}]; {_split_chain(depth)} <;> omega",
        ]
    # Branchy Bool-valued goals leave equations like `true = decide p` that
    # need the default simp set (hypothesis-aware) before omega can help.
    chain.append(
        f"simp only [{f}]; {_split_chain(max(depth, 1))} <;> (try simp_all) "
        f"<;> (try omega)"
    )

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
