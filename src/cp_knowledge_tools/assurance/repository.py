"""Read-only repository identity, scope and content evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import stat
import subprocess
import sys
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

MAX_FILE_BYTES = 10_000_000


def git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        timeout=20,
        env=env,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"git {args[0]} failed (exit {result.returncode})")
    if len(result.stdout) > MAX_FILE_BYTES:
        raise ValueError("repository metadata exceeds inspection budget")
    return result.stdout.decode("utf-8", errors="strict")


def bounded_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("scope paths must be nonempty repository-relative paths")
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink not supported in scope: {relative}")
    if not current.resolve().is_relative_to(root):
        raise ValueError("path outside repository")
    return current


def file_hash(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("only bounded regular files can be fingerprinted")
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(65536):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("file exceeds fingerprint budget")
            digest.update(chunk)
        return digest.hexdigest()


def repository_state(root: Path, *, base: str | None = None) -> dict:
    root = root.expanduser().resolve(strict=True)
    if Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve() != root:
        raise ValueError("--repo-root must be the actual repository root")
    head = git(root, "rev-parse", "--verify", "HEAD").strip()
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    base_commit = None
    if base:
        base_commit = git(
            root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"
        ).strip()
    changed = set(git(root, "diff", "--name-only", "-z", head, "--").split("\0"))
    changed.update(
        git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    )
    if base_commit:
        changed.update(
            git(root, "diff", "--name-only", "-z", base_commit, head, "--").split("\0")
        )
    changed.discard("")
    fingerprints = {}
    for name in sorted(changed):
        path = bounded_path(root, name)
        fingerprints[name] = file_hash(path) if path.exists() else "deleted"
    tools: dict[str, str | None] = {}
    for name in (
        "cp-knowledge-tools",
        "pytest",
        "ruff",
        "coverage",
        "mypy",
        "hypothesis",
    ):
        try:
            tools[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            tools[name] = None
    state = {
        "root": str(root),
        "branch": branch,
        "head": head,
        "base": base_commit,
        "status_porcelain": git(root, "status", "--porcelain=v1", "-z"),
        "index_fingerprint": sha256_bytes(
            git(root, "ls-files", "--stage", "-z").encode()
        ),
        "changed_paths": sorted(changed),
        "input_hashes": fingerprints,
        "interpreter": sys.executable,
        "python_version": sys.version.split()[0],
        "tool_versions": tools,
    }
    state["fingerprint"] = canonical_json_hash(state)
    return state
