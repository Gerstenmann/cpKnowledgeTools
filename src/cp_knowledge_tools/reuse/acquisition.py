"""Ephemeral snapshots using Git plumbing, never checkout, hooks or builds."""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .models import CandidateSnapshot, CandidateSource, InspectionLimits, ReuseError
from .paths import collect_files, relative_parts, verified_root, visible


def git_read(
    root: Path,
    args: list[str],
    *,
    output_limit: int = 2_000_000,
    timeout: float = 30,
    network: bool = False,
) -> bytes:
    """Internal fixed-command runner. No inherited Git config or credentials.

    Callers must not expose arbitrary args to an untrusted input surface.
    Git itself and OS/network isolation remain trusted platform prerequisites.
    """
    executable = shutil.which("git")
    if executable is None:
        raise ReuseError("Git executable unavailable")
    with tempfile.TemporaryDirectory(prefix="reuse-git-home-") as private_home:
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": private_home,
            "XDG_CONFIG_HOME": private_home,
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_ALLOW_PROTOCOL": "https" if network else "",
        }
        command = [
            executable,
            "--no-pager",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "credential.helper=",
            "-c",
            "http.followRedirects=false",
            "-c",
            "http.sslVerify=true",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=" + ("always" if network else "never"),
            "-c",
            "submodule.recurse=false",
            "-c",
            "gc.auto=0",
            "-C",
            str(root),
            *args,
        ]
        process = subprocess.Popen(
            command,
            env=env,
            cwd=private_home,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        output = bytearray()
        total = 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        raise ReuseError("Git time limit exceeded")
                    for key, _ in selector.select(min(0.1, timeout)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(chunk)
                        if total > output_limit:
                            raise ReuseError("Git output limit exceeded")
                        if key.data:
                            output.extend(chunk)
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if process.returncode:
                # Candidate-controlled stderr can contain secrets or instructions.
                raise ReuseError("Git failed; candidate or repository unavailable")
            return bytes(output)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdout.close()
            process.stderr.close()


def repository_commit(root: Path) -> str:
    root = verified_root(root)
    top = git_read(root, ["rev-parse", "--show-toplevel"]).decode().strip()
    if Path(top).resolve() != root:
        raise ReuseError("root must be the exact Git repository top level")
    return commit_id(root)


def commit_id(root: Path) -> str:
    commit = git_read(root, ["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ReuseError("unresolvable commit identity")
    return commit


def git_tree(root: Path, commit: str, limits: InspectionLimits):
    raw = git_read(
        root, ["ls-tree", "-rz", "-l", commit], output_limit=limits.max_files * 1000
    )
    entries = {}
    diagnostics = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        path = name.decode("utf-8", errors="strict")
        mode, kind, oid, size = metadata.decode().split()
        if not visible(path):
            continue
        relative_parts(path)
        if len(path.split("/")) - 1 > limits.max_depth:
            raise ReuseError("candidate tree exceeds depth limit")
        if kind != "blob" or mode not in {"100644", "100755"}:
            diagnostics.append(f"skipped symlink/submodule: {path}")
            continue
        if len(entries) >= limits.max_files or int(size) > limits.max_file_bytes:
            raise ReuseError("candidate tree exceeds inspection limits")
        entries[path] = (oid, int(size))
    if sum(size for _, size in entries.values()) > limits.max_total_bytes:
        raise ReuseError("candidate tree exceeds total byte limit")
    return entries, diagnostics


class ResearchWorkspace:
    """Owns temporary data outside the target; context exit removes it.

    HTTPS access requires an explicit allowlist from the host's research scope.
    This is an egress constraint, not a grant of network authority.
    """

    def __init__(
        self,
        target_repository: Path,
        *,
        allowed_https_hosts: tuple[str, ...] = (),
        limits: InspectionLimits = InspectionLimits(),
    ):
        self.target = verified_root(target_repository)
        repository_commit(self.target)
        self.allowed_hosts = allowed_https_hosts
        self.limits = limits
        self._temp = None

    def __enter__(self):
        self._temp = tempfile.TemporaryDirectory(prefix="cpkt-reuse-")
        self.root = Path(self._temp.name).resolve()
        if self.root.is_relative_to(self.target):
            self._temp.cleanup()
            self._temp = None
            raise ReuseError("research workspace must be outside target repository")
        return self

    def __exit__(self, *args):
        if self._temp:
            self._temp.cleanup()
            self._temp = None

    def acquire(self, source: CandidateSource) -> CandidateSnapshot:
        from urllib.parse import urlsplit

        if self._temp is None:
            raise ReuseError("research workspace is not open")
        # Revalidate even when a deserializer or caller bypassed the constructors.
        CandidateSource(source.kind, source.location, source.expected_commit)
        diagnostics = []
        if source.kind == "local":
            original = verified_root(Path(source.location))
            if original == self.target or original.is_relative_to(self.target):
                raise ReuseError("external candidate must be outside target")
            commit = repository_commit(original)
            files, notes = collect_files(original, self.limits)
            diagnostics.extend(notes)
            tree, notes = git_tree(original, commit, self.limits)
            diagnostics.extend(notes)

            def blob_id(data):
                payload = b"blob " + str(len(data)).encode() + b"\0" + data
                return (
                    hashlib.sha1(payload).hexdigest()
                    if len(commit) == 40
                    else hashlib.sha256(payload).hexdigest()
                )

            dirty = {p: blob_id(b) for p, b in files.items()} != {
                p: oid for p, (oid, _) in tree.items()
            }
            if repository_commit(original) != commit:
                raise ReuseError("source commit drift during acquisition")
        else:
            if urlsplit(source.location).hostname not in self.allowed_hosts:
                raise ReuseError("HTTPS host outside authorized research scope")
            bare = Path(tempfile.mkdtemp(prefix="objects-", dir=self.root))
            git_read(
                self.root,
                [
                    "clone",
                    "--bare",
                    "--depth=1",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "--template=",
                    "--",
                    source.location,
                    str(bare),
                ],
                network=True,
            )
            commit = commit_id(bare)
            tree, diagnostics = git_tree(bare, commit, self.limits)
            files = {
                p: git_read(
                    bare,
                    ["cat-file", "blob", oid],
                    output_limit=self.limits.max_file_bytes + 1024,
                )
                for p, (oid, _) in tree.items()
            }
            dirty = False
        if source.expected_commit and source.expected_commit != commit:
            raise ReuseError("candidate commit does not match expected commit")
        fingerprints = tuple(
            (p, sha256_bytes(data)) for p, data in sorted(files.items())
        )
        fingerprint = canonical_json_hash(fingerprints)
        snapshot_root = Path(tempfile.mkdtemp(prefix="snapshot-", dir=self.root))
        for path, data in files.items():
            dest = snapshot_root.joinpath(*relative_parts(path))
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(data)
            dest.chmod(0o400)
        return CandidateSnapshot(
            candidate_id=canonical_json_hash(
                {"source": source.location, "snapshot": fingerprint, "commit": commit}
            )[:24],
            source=source,
            root=snapshot_root,
            commit=commit,
            fingerprint=fingerprint,
            file_fingerprints=fingerprints,
            dirty=dirty,
            diagnostics=tuple(sorted(diagnostics)),
            limits=self.limits,
        )
