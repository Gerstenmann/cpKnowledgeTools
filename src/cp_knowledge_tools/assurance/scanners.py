"""Opt-in CLI wrappers for separately admitted external tools.

No package-manager or acceptance behavior. Output is normalized before retention.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

from cp_knowledge_tools.platform.hashing import sha256_bytes

from .execution import execute
from .report import Report
from .repository import file_hash

SCANNERS = {"cyclonedx", "pip-audit", "gitleaks", "grant"}


def _text(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 4096


def normalize(name: str, code: int, payload: object) -> dict:
    if name == "cyclonedx":
        if (
            code != 0
            or not isinstance(payload, dict)
            or payload.get("bomFormat") != "CycloneDX"
            or payload.get("specVersion") != "1.6"
            or type(payload.get("version")) is not int
            or payload["version"] < 1
            or not isinstance(payload.get("components"), list)
        ):
            raise ValueError("invalid or unsuccessful CycloneDX result")
        if any(
            not isinstance(component, dict)
            or not _text(component.get("type"))
            or not _text(component.get("name"))
            or not _text(component.get("version"))
            for component in payload["components"]
        ):
            raise ValueError("malformed CycloneDX component inventory")
        return {
            "result": "inventory",
            "component_count": len(payload["components"]),
            "spec_version": payload.get("specVersion"),
        }
    if name == "pip-audit":
        if (
            code not in {0, 1}
            or not isinstance(payload, dict)
            or not isinstance(payload.get("dependencies"), list)
        ):
            raise ValueError("invalid or unsuccessful pip-audit result")
        dependencies = payload["dependencies"]
        if not dependencies or any(
            not isinstance(d, dict)
            or not isinstance(d.get("vulns"), list)
            or not _text(d.get("name"))
            or not _text(d.get("version"))
            or d.get("skip_reason")
            for d in dependencies
        ):
            raise ValueError("empty, malformed or skipped dependency inventory")
        findings = []
        for dependency in dependencies:
            for vuln in dependency["vulns"]:
                if not isinstance(vuln, dict) or not _text(vuln.get("id")):
                    raise ValueError("malformed vulnerability")
                findings.append(
                    {
                        "package": dependency["name"],
                        "version": dependency["version"],
                        "id": vuln["id"],
                    }
                )
        if bool(findings) != (code == 1):
            raise ValueError("exit/result mismatch")
        return {
            "result": "findings" if findings else "no_known_findings",
            "findings": findings,
            "dependency_count": len(dependencies),
        }
    if name == "gitleaks":
        if (
            code not in {0, 10}
            or not isinstance(payload, list)
            or any(
                not isinstance(f, dict)
                or not _text(f.get("RuleID"))
                or not _text(f.get("File"))
                for f in payload
            )
        ):
            raise ValueError("invalid or unsuccessful Gitleaks result")
        if bool(payload) != (code == 10):
            raise ValueError("exit/result mismatch")
        fields = ("RuleID", "File", "StartLine", "EndLine", "StartColumn", "EndColumn")
        if any(
            type(f[key]) is not int or f[key] < 0
            for f in payload
            for key in fields[2:]
            if key in f
        ):
            raise ValueError("malformed Gitleaks positions")
        return {
            "result": "findings" if payload else "no_known_findings",
            "findings": [{k: f[k] for k in fields if k in f} for f in payload],
        }
    if name == "grant":
        # CLI versions have different inventory shapes. Preserve a fingerprint,
        # but do not turn unknown JSON or exit 1 into a clean license decision.
        if code != 0 or not isinstance(payload, (dict, list)):
            raise ValueError("invalid or unsuccessful Grant result")
        return {"result": "uninterpreted_inventory", "review_required": True}
    raise ValueError("unsupported scanner")


def scan(
    report: Report,
    root: Path,
    *,
    name: str,
    executable: Path,
    allow_network: bool = False,
    sbom: Path | None = None,
    timeout: int = 300,
) -> None:
    if name not in SCANNERS:
        raise ValueError("unsupported scanner")
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError(
            "scanner executable must be an explicit installed absolute path"
        )
    if name == "pip-audit" and not allow_network:
        report.check(
            name,
            "incomplete",
            kind="external_tool_finding",
            reason="Explicit vulnerability-service egress authorization required.",
        )
        return
    if name == "grant" and (
        sbom is None or not sbom.is_absolute() or not sbom.is_file()
    ):
        raise ValueError("Grant requires an explicit local SBOM")
    binary_hash = file_hash(executable.resolve(), max_bytes=512_000_000)
    version_result = execute(
        [str(executable), "--version"], root, 20, max_bytes=100_000
    )
    version = re.search(rb"\b\d+\.\d+(?:\.\d+)?\b", version_result.output)
    if version_result.problem or version_result.code != 0 or version is None:
        report.check(
            name,
            "incomplete",
            kind="external_tool_finding",
            reason="Scanner version could not be verified.",
        )
        return
    with tempfile.TemporaryDirectory(prefix="cpks-scanner-") as directory:
        work = Path(directory)
        if name == "cyclonedx":
            command = [
                str(executable),
                "environment",
                sys.executable,
                "-S",
                "--output-format",
                "JSON",
                "--spec-version",
                "1.6",
                "--output-reproducible",
                "--validate",
                "--output-file",
                "-",
            ]
        elif name == "pip-audit":
            # Freeze only distribution names/versions in the caller's interpreter.
            from importlib.metadata import distributions

            requirements = work / "requirements.txt"
            items = []
            for dist in distributions():
                package, version_text = dist.metadata.get("Name", ""), dist.version
                if package == "cp-knowledge-tools":
                    continue  # local first-party project, not a PyPI package
                if not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]*", package
                ) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]*", version_text):
                    raise ValueError(
                        "dependency cannot be represented as a pinned requirement"
                    )
                items.append(f"{package}=={version_text}")
            requirements.write_text("\n".join(sorted(set(items))) + "\n")
            command = [
                str(executable),
                "-r",
                str(requirements),
                "--no-deps",
                "--disable-pip",
                "--strict",
                "--format",
                "json",
                "--progress-spinner",
                "off",
                "--vulnerability-service",
                "pypi",
                "--cache-dir",
                str(work / "cache"),
            ]
        elif name == "gitleaks":
            command = [
                str(executable),
                "dir",
                str(root),
                "--redact=100",
                "--exit-code",
                "10",
                "--report-format",
                "json",
                "--report-path",
                "-",
                "--no-banner",
                "--no-color",
                "--log-level",
                "error",
            ]
        else:
            assert sbom is not None  # checked before scanner execution
            file_hash(sbom)
            command = [
                str(executable),
                "list",
                str(sbom),
                "--disable-file-search",
                "--output",
                "json",
            ]
        try:
            result = execute(command, root, timeout)
            if result.problem:
                report.check(
                    name,
                    "incomplete",
                    kind="external_tool_finding",
                    reason=result.problem,
                    tool_version=version.group().decode(),
                    executable_hash=binary_hash,
                )
                return
            if result.code is None:
                raise ValueError("scanner did not finish")
            raw = result.output
            normalized = normalize(name, result.code, json.loads(raw))
        except (OSError, ValueError) as exc:
            report.check(
                name,
                "incomplete",
                kind="external_tool_finding",
                reason=type(exc).__name__,
                tool_version=version.group().decode(),
                executable_hash=binary_hash,
            )
            return
        # Scanner findings do not decide acceptance; they require contextual review.
        status = (
            "incomplete"
            if normalized["result"] in {"findings", "uninterpreted_inventory"}
            else "passed"
        )
        report.check(
            name,
            status,
            kind="external_tool_finding",
            tool_version=version.group().decode(),
            executable_hash=binary_hash,
            output_hash=sha256_bytes(raw),
            summary=normalized,
        )
        if normalized["result"] == "findings":
            report.findings.append(
                {
                    "code": f"{name}_findings",
                    "severity": "review",
                    "information_class": "external_tool_finding",
                    "rule_home": "CPKS-POL-SW-SUPPLY",
                    "evidence_refs": [sha256_bytes(raw)],
                    "recommended_disposition": "Review relevance and exposure.",
                }
            )
