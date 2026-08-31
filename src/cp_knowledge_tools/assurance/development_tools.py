"""Reviewed local development-tool identity; no installer or command registry."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .repository import bounded_path, file_hash

MAX_EXECUTABLE_BYTES = 100_000_000


@dataclass(frozen=True)
class DevelopmentToolBinding:
    version: str
    system: str
    machine: str
    executable_sha256: str
    manifest: dict

    def verify_executable(self, executable: Path) -> str:
        if not executable.is_absolute() or not os.access(executable, os.X_OK):
            raise ValueError("uv must be an explicit absolute executable")
        digest = file_hash(executable, max_bytes=MAX_EXECUTABLE_BYTES)
        if digest != self.executable_sha256:
            raise ValueError("uv executable hash differs from reviewed binding")
        return digest


def load_binding(root: Path, path: Path) -> DevelopmentToolBinding:
    """Read the deliberately narrow uv binding, separate from scanner admission.

    Evidence references document prior review; their presence cannot grant approval.
    An ignored admission download need not be retained on every future checkout.
    """
    path = bounded_path(root, str(path.relative_to(root)))
    file_hash(path, max_bytes=100_000)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"schema_version", "tool"}:
        raise ValueError("invalid development-tool binding envelope")
    tool = value["tool"]
    keys = {
        "id",
        "version",
        "platform",
        "source_url",
        "source_commit",
        "license_expression",
        "archive",
        "executable_sha256",
        "provenance",
        "assessment_ref",
    }
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(tool, dict)
        or set(tool) != keys
    ):
        raise ValueError("invalid development-tool binding schema")
    if (
        tool["id"] != "uv"
        or not re.fullmatch(r"\d+\.\d+\.\d+", str(tool["version"]))
        or tool["source_url"] != "https://github.com/astral-sh/uv"
        or tool["license_expression"] != "MIT OR Apache-2.0"
        or not re.fullmatch(r"[0-9a-f]{40}", str(tool["source_commit"]))
    ):
        raise ValueError("unsupported development-tool identity")
    platform = tool["platform"]
    if platform != {"system": "Darwin", "machine": "arm64"}:
        raise ValueError("development-tool platform is not the reviewed Darwin arm64")
    archive = tool["archive"]
    url = (
        "https://github.com/astral-sh/uv/releases/download/"
        f"{tool['version']}/uv-aarch64-apple-darwin.tar.gz"
    )
    if (
        not isinstance(archive, dict)
        or set(archive) != {"url", "sha256"}
        or archive["url"] != url
        or not re.fullmatch(r"[0-9a-f]{64}", str(archive["sha256"]))
        or not re.fullmatch(r"[0-9a-f]{64}", str(tool["executable_sha256"]))
    ):
        raise ValueError("invalid development-tool artifact binding")
    provenance = tool["provenance"]
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"method", "repository", "evidence_ref"}
        or provenance["method"] != "github-artifact-attestation"
        or provenance["repository"] != "astral-sh/uv"
    ):
        raise ValueError("invalid development-tool provenance reference")
    for reference in (provenance["evidence_ref"], tool["assessment_ref"]):
        if not isinstance(reference, str):
            raise ValueError("development-tool evidence references must be paths")
        bounded_path(root, reference)
    return DevelopmentToolBinding(
        tool["version"],
        platform["system"],
        platform["machine"],
        tool["executable_sha256"],
        value,
    )
