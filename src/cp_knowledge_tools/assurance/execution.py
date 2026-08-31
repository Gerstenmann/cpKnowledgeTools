"""Finite subprocess transport shared by local checks and reviewed scanners."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    code: int | None
    output: bytes
    duration: float
    problem: str | None = None


def execute(
    command: list[str], root: Path, timeout: int, *, max_bytes: int = 10_000_000
) -> ProcessResult:
    if not 1 <= timeout <= 3600 or not 1 <= max_bytes <= 20_000_000:
        raise ValueError("execution budget outside supported bounds")
    env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT"}
    }
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        problem = None
        try:
            while process.poll() is None:
                if time.monotonic() - started >= timeout:
                    problem = "timeout"
                    break
                if (
                    os.fstat(stdout.fileno()).st_size
                    + os.fstat(stderr.fileno()).st_size
                    > max_bytes
                ):
                    problem = "output_budget_exceeded"
                    break
                time.sleep(0.02)
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if (
            os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
            > max_bytes
        ):
            problem = "output_budget_exceeded"
        stdout.seek(0)
        output = stdout.read(max_bytes) if problem is None else b""
    return ProcessResult(
        process.returncode, output, round(time.monotonic() - started, 3), problem
    )
