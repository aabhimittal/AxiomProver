import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Allow running the tests from a fresh checkout without installation.
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXAMPLES = REPO_ROOT / "examples"
