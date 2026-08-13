"""AxiomProver: Lean-based formal verification of AI-generated code.

The public surface has two halves:

1. **Spec decorators** (`requires`, `ensures`, `proof`) that annotate plain
   Python functions with contracts. At runtime they are metadata-only no-ops,
   so decorated code behaves identically to undecorated code.

2. **The verification pipeline** (`verify_file`, `verify_function`) that
   statically parses annotated source, translates it into Lean 4, and asks
   the Lean kernel to certify the contract for *all* inputs.
"""

from axiomprover.decorators import ensures, proof, requires
from axiomprover.report import FunctionReport, Verdict
from axiomprover.verifier import verify_file, verify_function

__version__ = "0.2.0"

__all__ = [
    "requires",
    "ensures",
    "proof",
    "verify_file",
    "verify_function",
    "FunctionReport",
    "Verdict",
    "__version__",
]
