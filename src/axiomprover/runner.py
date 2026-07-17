"""Invocation of the Lean toolchain.

The kernel's exit status is the sole source of the VERIFIED verdict. The
runner is a thin, replaceable boundary: tests substitute a fake, and any
`lean` on PATH (or pointed to by --lean-bin / AXIOMPROVER_LEAN) works as long
as it is Lean 4 with `omega` in core (v4.6.0 or later; the repo pins v4.15.0
in lean/lean-toolchain).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LeanResult:
    accepted: bool
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def diagnostics(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part).strip()


class LeanNotFoundError(Exception):
    pass


class LeanRunner:
    """Checks a .lean file by running `lean <file>` and trusting the exit
    status. A zero exit means the kernel accepted every declaration."""

    def __init__(self, lean_bin: str | None = None, timeout: float = 120.0):
        self.lean_bin = lean_bin or os.environ.get("AXIOMPROVER_LEAN") or "lean"
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.lean_bin) is not None

    def version(self) -> str | None:
        if not self.available():
            return None
        proc = subprocess.run(
            [self.lean_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.stdout.strip() or None

    def check(self, lean_file: Path) -> LeanResult:
        if not self.available():
            raise LeanNotFoundError(
                f"Lean executable {self.lean_bin!r} not found. Install elan "
                f"(https://leanprover-community.github.io/get_started.html) or "
                f"pass --lean-bin / set AXIOMPROVER_LEAN."
            )
        try:
            proc = subprocess.run(
                [self.lean_bin, str(lean_file)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=lean_file.parent,
            )
        except subprocess.TimeoutExpired as exc:
            return LeanResult(
                accepted=False,
                stdout=(exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr="proof attempt timed out",
                timed_out=True,
            )
        return LeanResult(
            accepted=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
