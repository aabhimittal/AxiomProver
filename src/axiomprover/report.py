"""Verdicts and reports.

The verdict lattice is deliberately asymmetric:

  VERIFIED     only the Lean kernel can produce this.
  REFUTED      a concrete counterexample exists (execution witnessed it).
  UNKNOWN      the model was built but no tactic closed the goal. This is
               *not* evidence of correctness — automation has limits
               (nonlinear arithmetic, missing lemmas).
  UNSUPPORTED  the code is outside the translatable subset; nothing was
               modeled, so nothing was checked.
  ERROR        environment problems (Lean missing, timeout on every attempt).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


@dataclass
class TheoremReport:
    name: str
    clause: str  # Python source of the ensures clause
    proved: bool
    tactic: str | None = None  # the script that closed it, if proved


@dataclass
class FunctionReport:
    function: str
    verdict: Verdict
    detail: str = ""
    theorems: list[TheoremReport] = field(default_factory=list)
    counterexample: dict | None = None
    lean_file: str | None = None

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "verdict": self.verdict.value,
            "detail": self.detail,
            "theorems": [
                {
                    "name": t.name,
                    "clause": t.clause,
                    "proved": t.proved,
                    "tactic": t.tactic,
                }
                for t in self.theorems
            ],
            "counterexample": self.counterexample,
            "lean_file": self.lean_file,
        }


_ICONS = {
    Verdict.VERIFIED: "✓",
    Verdict.REFUTED: "✗",
    Verdict.UNKNOWN: "?",
    Verdict.UNSUPPORTED: "–",
    Verdict.ERROR: "!",
}


def render_text(reports: list[FunctionReport]) -> str:
    lines = []
    for r in reports:
        lines.append(f"[{_ICONS[r.verdict]}] {r.function}: {r.verdict.value}")
        if r.detail:
            lines.append(f"    {r.detail}")
        for t in r.theorems:
            mark = "proved" if t.proved else "open"
            lines.append(f"    - ensures {t.clause}  [{mark}]")
            if t.proved and t.tactic:
                lines.append(f"      by {t.tactic}")
        if r.counterexample:
            lines.append(f"    counterexample: {r.counterexample}")
        if r.lean_file:
            lines.append(f"    lean: {r.lean_file}")
    verified = sum(r.verdict is Verdict.VERIFIED for r in reports)
    lines.append("")
    lines.append(
        f"{verified}/{len(reports)} functions verified "
        f"(kernel-checked; everything else is not a correctness claim)"
    )
    return "\n".join(lines)


def render_json(reports: list[FunctionReport]) -> str:
    return json.dumps([r.to_dict() for r in reports], indent=2)
