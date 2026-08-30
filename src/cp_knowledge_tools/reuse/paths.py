"""Bounded no-follow filesystem access; no candidate-controlled execution."""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path

from .models import InspectionLimits, ReuseError

EXCLUDED = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".ssh",
        ".aws",
        ".gnupg",
        "artifacts",
    }
)


def relative_parts(value: str) -> tuple[str, ...]:
    parts = tuple(value.split("/"))
    if (
        not parts
        or any(p in {"", ".", ".."} for p in parts)
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
        or any(p.casefold() == ".git" for p in parts)
    ):
        raise ReuseError("unsafe relative path")
    return parts


def visible(path: str) -> bool:
    parts = path.split("/")
    return not any(
        p in EXCLUDED
        or p.lower().startswith(".env")
        or p.lower() in {"credentials", "credentials.json", "secrets.json"}
        or p.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        for p in parts
    )


def verified_root(path: Path) -> Path:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ReuseError("root or parent is a symlink; supply its verified real path")
    if not path.is_dir():
        raise ReuseError("repository root must be an existing directory")
    return path.resolve()


class RootHandle:
    def __init__(self, root: Path):
        self.root = verified_root(root)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        self.identity = (info.st_dev, info.st_ino)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    def check_identity(self):
        root = verified_root(self.root)
        info = root.stat()
        if (info.st_dev, info.st_ino) != self.identity:
            raise ReuseError("target root identity drift")

    @contextmanager
    def parent(self, relative: str):
        parts = relative_parts(relative)
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                following = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = following
            yield fd, parts[-1]
        except OSError as exc:
            raise ReuseError("unsafe or missing path parent") from exc
        finally:
            os.close(fd)

    def read(self, relative: str, limit: int = 1_000_000) -> bytes:
        with self.parent(relative) as (fd, name):
            try:
                child = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
                )
            except OSError as exc:
                raise ReuseError("file missing or unsafe") from exc
            try:
                info = os.fstat(child)
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise ReuseError("file is not regular or exceeds byte limit")
                with os.fdopen(os.dup(child), "rb") as stream:
                    data = stream.read(limit + 1)
                if len(data) > limit:
                    raise ReuseError("file exceeds byte limit")
                return data
            finally:
                os.close(child)

    def optional_read(self, relative: str, limit: int = 1_000_000):
        with self.parent(relative) as (fd, name):
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
        return self.read(relative, limit)


def collect_files(root: Path, limits: InspectionLimits):
    files: dict[str, bytes] = {}
    diagnostics: list[str] = []
    total = 0
    entries = 0
    with RootHandle(root) as handle:

        def walk(fd, prefix, depth):
            nonlocal total, entries
            if depth > limits.max_depth:
                raise ReuseError("inspection depth limit exceeded")
            with os.scandir(fd) as children:
                for entry in children:
                    entries += 1
                    if entries > limits.max_files * 4:
                        raise ReuseError("inspection entry limit exceeded")
                    rel = f"{prefix}/{entry.name}" if prefix else entry.name
                    if not visible(rel):
                        continue
                    if entry.is_symlink():
                        diagnostics.append(f"skipped symlink: {rel}")
                        continue
                    relative_parts(rel)
                    if entry.is_dir(follow_symlinks=False):
                        child = os.open(
                            entry.name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd,
                        )
                        try:
                            walk(child, rel, depth + 1)
                        finally:
                            os.close(child)
                    elif entry.is_file(follow_symlinks=False):
                        if len(files) >= limits.max_files:
                            raise ReuseError("inspection file limit exceeded")
                        data = handle.read(rel, limits.max_file_bytes)
                        total += len(data)
                        if total > limits.max_total_bytes:
                            raise ReuseError("inspection total byte limit exceeded")
                        files[rel] = data
                    else:
                        diagnostics.append(f"skipped special file: {rel}")

        walk(handle.fd, "", 0)
        handle.check_identity()
    return dict(sorted(files.items())), tuple(sorted(diagnostics))
