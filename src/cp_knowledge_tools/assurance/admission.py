"""Technical bindings to reviewed scanner artifacts; never an acceptance engine."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from datetime import datetime
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .repository import file_hash

MODULES = {"cyclonedx": "cyclonedx_py", "pip-audit": "pip_audit"}
TOOL_IDS = {*MODULES, "grant", "gitleaks"}


def tree_hash(root: Path) -> str:
    """Hash installed source/data, excluding relocatable RECORD and bytecode.

    Bytecode is forbidden: execution uses -B after a no-compile installation.
    RECORD is installer bookkeeping, never imported; all other bytes are bound.
    """
    if root.is_symlink() or not root.is_dir():
        raise ValueError("scanner site-packages must be a real directory")
    files: dict[str, str] = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        if any((parent / d).is_symlink() for d in dirs):
            raise ValueError("symlink in scanner environment")
        for name in names:
            path = parent / name
            if path.is_symlink():
                raise ValueError("symlink in scanner environment")
            if name.endswith((".pyc", ".pyo", ".pth")) or name in {
                "sitecustomize.py",
                "usercustomize.py",
            }:
                raise ValueError("unreviewed scanner startup or bytecode file")
            if name == "RECORD" and parent.name.endswith(".dist-info"):
                continue
            total += path.stat().st_size
            if total > 300_000_000 or len(files) >= 30_000:
                raise ValueError("scanner environment exceeds fingerprint budget")
            files[path.relative_to(root).as_posix()] = file_hash(
                path, max_bytes=100_000_000
            )
    if not files:
        raise ValueError("empty scanner environment")
    return canonical_json_hash(files)


def load_manifest(path: Path) -> dict[str, dict]:
    """Read engineering evidence explicitly selected by the trusted operator.

    This is not a signature, permission grant or generic third-party register.
    No arbitrary commands, environment variables or acceptance rules are loaded.
    """
    digest = file_hash(path)
    content = path.read_bytes()
    if sha256_bytes(content) != digest:
        raise ValueError("scanner admission changed while reading")
    try:
        document = json.loads(content)
    except RecursionError as exc:
        raise ValueError("scanner admission JSON exceeds nesting limit") from exc
    if not isinstance(document, dict) or document.get("schema_version") != (
        "cpks.scanner-admission/1"
    ):
        raise ValueError("unsupported scanner admission schema")
    entries = document.get("tools")
    if not isinstance(entries, list) or not entries:
        raise ValueError("admission requires concrete tools")
    result = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("tool_id"), str)
            or entry["tool_id"] not in TOOL_IDS
        ):
            raise ValueError("unsupported admitted tool")
        name = entry["tool_id"]
        if name in result:
            raise ValueError("duplicate admitted tool")
        for key in (
            "version",
            "executable_sha256",
            "license",
            "upstream",
            "accepted_use_context",
            "verified_at",
            "assessment_ref",
        ):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ValueError("incomplete scanner admission")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["executable_sha256"]):
            raise ValueError("invalid executable fingerprint")
        timestamp = datetime.fromisoformat(entry["verified_at"])
        if timestamp.tzinfo is None:
            raise ValueError("admission timestamp requires timezone")
        if (
            entry.get("disposition") != "WRAP"
            or not isinstance(entry.get("acceptance"), str)
            or entry.get("acceptance") not in {"accepted", "accepted_with_conditions"}
            or not isinstance(entry.get("conditions"), list)
        ):
            raise ValueError("no reviewed scanner use disposition")
        if not isinstance(entry.get("execution"), dict):
            raise ValueError("missing scanner execution form")
        result[name] = {**entry, "_manifest_hash": digest}
    return result


def binding(executable: Path, entry: dict, name: str) -> tuple[list[str], dict]:
    """Verify bytes before executing even --version; return a fixed argv prefix."""
    if entry.get("tool_id") != name or name not in TOOL_IDS:
        raise ValueError("scanner admission identity mismatch")
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("scanner requires an explicit absolute executable")
    if entry.get("platform") != f"{platform.system().lower()}-{platform.machine()}":
        raise ValueError("scanner platform differs from admission")
    digest = file_hash(executable.resolve(strict=True), max_bytes=512_000_000)
    if digest != entry.get("executable_sha256"):
        raise ValueError("scanner executable fingerprint differs from admission")
    execution = entry["execution"]
    prefix = [str(executable)]
    evidence = {
        "executable_hash": digest,
        "admission_hash": entry.get("_manifest_hash"),
    }
    if execution.get("kind") == "python_module" and name in MODULES:
        root = executable.parent.parent
        if root.resolve() == Path(sys.prefix).resolve():
            raise ValueError("scanner environment must be separate from target")
        config = (root / "pyvenv.cfg").read_text(encoding="utf-8")
        values = dict(
            line.split(" = ", 1) for line in config.splitlines() if " = " in line
        )
        if values.get("include-system-site-packages") != "false":
            raise ValueError("scanner venv must exclude system site-packages")
        if Path(values.get("home", "")).resolve() != executable.resolve().parent:
            raise ValueError("scanner venv base interpreter differs from binding")
        version = execution.get("python_version")
        if values.get("version") != version or not isinstance(version, str):
            raise ValueError("scanner interpreter version differs from admission")
        site = (
            root / "lib" / f"python{'.'.join(version.split('.')[:2])}" / "site-packages"
        )
        digest = tree_hash(site)
        if digest != execution.get("site_packages_sha256"):
            raise ValueError("scanner environment fingerprint differs from admission")
        evidence["environment_hash"] = digest
        prefix += ["-I", "-B", "-m", MODULES[name]]
    elif execution.get("kind") != "binary" or name in MODULES:
        raise ValueError("unsupported scanner execution form")
    return prefix, evidence
