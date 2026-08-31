"""Opt-in CLI wrappers for separately admitted external tools.

No package-manager or acceptance behavior. Output is normalized before retention.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_bytes, sha256_bytes

from .admission import binding
from .execution import execute
from .report import Report
from .repository import file_hash

SCANNERS = {"cyclonedx", "pip-audit", "gitleaks", "grant"}
DIRECTORY_EXCLUSIONS = {
    ".git",
    ".venv",
    "artifacts",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def directory_input(root: Path) -> dict:
    """Fingerprint the directory view, including git-ignored regular files."""
    files: dict[str, str] = {}
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = [
            d
            for d in dirs
            if d not in DIRECTORY_EXCLUSIONS and not (parent / d).is_symlink()
        ]
        for name in names:
            path = parent / name
            info = path.lstat()
            if name in DIRECTORY_EXCLUSIONS or stat.S_ISLNK(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("unsupported file type in scanner input")
            total += info.st_size
            if len(files) >= 20_000 or total > 500_000_000:
                raise ValueError("scanner input exceeds fingerprint budget")
            files[path.relative_to(root).as_posix()] = file_hash(
                path, max_bytes=100_000_000
            )
    return {
        "input_hash": sha256_bytes(canonical_json_bytes(files)),
        "input_file_count": len(files),
        "input_bytes": total,
    }


def _text(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 4096
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


def _package(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+!-]{0,199}", value) is not None
    )


def package_set(items: list[dict]) -> set[tuple[str, str]]:
    if any(
        not _package(i.get("name")) or not _package(i.get("version")) for i in items
    ):
        raise ValueError("invalid package identity")
    return {(re.sub(r"[-_.]+", "-", i["name"]).lower(), i["version"]) for i in items}


def environment_packages() -> list[dict]:
    return [
        {"name": d.metadata.get("Name"), "version": d.version}
        for d in importlib.metadata.distributions()
    ]


def metadata_input() -> dict[str, bytes]:
    """Copy only installed metadata, never a target import/startup surface."""
    records: list[bytes] = []
    total = 0
    for distribution in importlib.metadata.distributions():
        value = distribution.read_text("METADATA") or distribution.read_text("PKG-INFO")
        if value is None:
            raise ValueError("installed distribution metadata unavailable")
        record = value.encode("utf-8")
        total += len(record)
        if len(record) > 2_000_000 or len(records) >= 10_000 or total > 10_000_000:
            raise ValueError("distribution metadata exceeds snapshot budget")
        records.append(record)
    if not records:
        raise ValueError("empty installed distribution metadata")
    return {
        f"distribution{index}.dist-info/METADATA": value
        for index, value in enumerate(sorted(records))
    }


def metadata_hash(records: dict[str, bytes]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {name: sha256_bytes(value) for name, value in records.items()}
        )
    )


def safe_sbom(payload: object) -> bytes:
    """Minimal CycloneDX projection: no paths, URLs, descriptions or license text."""
    normalize("cyclonedx", 0, payload)
    assert isinstance(payload, dict)
    components = []
    for index, component in enumerate(payload["components"]):
        licenses = []
        for item in component.get("licenses", []):
            if not isinstance(item, dict):
                raise ValueError("invalid CycloneDX license")
            expression = item.get("expression")
            license_data = item.get("license", {})
            if not isinstance(license_data, dict):
                raise ValueError("invalid CycloneDX license")
            value = expression or license_data.get("id")
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(
                    r"[A-Za-z0-9().+_ -]{1,512}", value
                ):
                    raise ValueError("unsupported license label")
                licenses.append(
                    {"expression": value} if expression else {"license": {"id": value}}
                )
            # Free-form license names/text remain unresolved, never copied.
        components.append(
            {
                "type": "library",
                "name": component["name"],
                "version": component["version"],
                "bom-ref": f"component-{index}",
                "licenses": licenses,
            }
        )
    return canonical_json_bytes(
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": components,
        }
    )


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
            or not payload["components"]
        ):
            raise ValueError("invalid or unsuccessful CycloneDX result")
        if any(
            not isinstance(component, dict)
            or not _text(component.get("type"))
            or not _package(component.get("name"))
            or not _package(component.get("version"))
            or not isinstance(component.get("licenses", []), list)
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
            or not _package(d.get("name"))
            or not _package(d.get("version"))
            or "skip_reason" in d
            for d in dependencies
        ):
            raise ValueError("empty, malformed or skipped dependency inventory")
        findings = []
        for dependency in dependencies:
            for vuln in dependency["vulns"]:
                if not isinstance(vuln, dict) or not _text(vuln.get("id")):
                    raise ValueError("malformed vulnerability")
                fixes = vuln.get("fix_versions", [])
                if not isinstance(fixes, list) or any(not _package(v) for v in fixes):
                    raise ValueError("malformed fix versions")
                findings.append(
                    {
                        "package": dependency["name"],
                        "version": dependency["version"],
                        "id": vuln["id"],
                        "fix_versions": fixes,
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
        return _grant(code, payload)
    raise ValueError("unsupported scanner")


def _grant(code: int, payload: object) -> dict:
    # Observed 0.6.8 list contract. Do not guess shapes or interpret Grant policy.
    if (
        code != 0
        or not isinstance(payload, dict)
        or payload.get("tool") != "grant"
        or payload.get("version") != "0.6.8"
    ):
        raise ValueError("unsupported Grant result")
    run = payload.get("run")
    targets = run.get("targets") if isinstance(run, dict) else None
    if (
        not isinstance(targets, list)
        or len(targets) != 1
        or not isinstance(targets[0], dict)
    ):
        raise ValueError("unsupported Grant targets")
    evaluation = targets[0].get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("status") != "unevaluated":
        raise ValueError("Grant did not complete list inventory")
    findings = evaluation.get("findings")
    packages = findings.get("packages") if isinstance(findings, dict) else None
    if not isinstance(packages, list) or not packages:
        raise ValueError("missing Grant packages")
    result: dict[tuple[str, str], set[str]] = {}
    for package in packages:
        if not isinstance(package, dict) or package.get("decision") != "unevaluated":
            raise ValueError("not a Grant list package")
        package_set([package])
        licenses = package.get("licenses")
        if not isinstance(licenses, list):
            raise ValueError("invalid Grant licenses")
        key = (package["name"], package["version"])
        values = result.setdefault(key, set())
        for license in licenses:
            if not isinstance(license, dict) or not isinstance(license.get("id"), str):
                raise ValueError("invalid Grant license")
            label = license["id"]
            if label:
                if not re.fullmatch(r"[A-Za-z0-9().+_ -]{1,512}", label):
                    raise ValueError("unsupported Grant license label")
                values.add(label)
    return {
        "result": "inventory",
        "package_count": len(result),
        "packages": [
            {"name": n, "version": v, "licenses": sorted(ls)}
            for (n, v), ls in sorted(result.items())
        ],
        "unresolved_license_count": sum(not ls for ls in result.values()),
        "policy_evaluated": False,
    }


def scan(
    report: Report,
    root: Path,
    *,
    name: str,
    executable: Path,
    allow_network: bool = False,
    sbom: Path | None = None,
    timeout: int = 300,
    admission: dict | None = None,
) -> bytes | None:
    if name not in SCANNERS:
        raise ValueError("unsupported scanner")
    started = datetime.now(UTC).isoformat()
    evidence: dict = {"started_at": started, "acceptance": "not_evaluated"}
    if admission is None:
        report.check(
            name,
            "incomplete",
            kind="external_tool_finding",
            reason="Explicit reviewed scanner admission required.",
        )
        return None
    if name == "pip-audit" and not allow_network:
        report.check(
            name,
            "incomplete",
            kind="external_tool_finding",
            reason="Explicit vulnerability-service egress authorization required.",
        )
        return None
    try:
        prefix, bound = binding(executable, admission, name)
        evidence.update(bound)
        with tempfile.TemporaryDirectory(prefix="cpks-scanner-") as directory:
            work = Path(directory)
            env = {
                "PATH": "/usr/bin:/bin",
                "HOME": directory,
                "XDG_CONFIG_HOME": directory,
                "XDG_CONFIG_DIRS": directory,
                "XDG_CACHE_HOME": directory,
                "TMPDIR": directory,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }
            version_result = execute(
                prefix + ["--version"], work, 20, max_bytes=100_000, environment=env
            )
            version = re.search(rb"\b\d+\.\d+\.\d+\b", version_result.output)
            if (
                version_result.problem
                or version_result.code != 0
                or version is None
                or version.group().decode() != admission["version"]
            ):
                raise ValueError("scanner version differs from admission")
            evidence["tool_version"] = version.group().decode()
            expected: set[tuple[str, str]] | None = None
            target_input: bytes | None = None
            directory_before = None
            metadata_before = None
            if name == "cyclonedx":
                # CycloneDX's -S child imports json before returning sys.path.
                # Target site-packages on PYTHONPATH could shadow stdlib code.
                # Export only METADATA files into a new private directory, never
                # target modules, .pth files, direct URLs or entry points.
                records = metadata_input()
                metadata_before = metadata_hash(records)
                snapshot = work / "metadata"
                snapshot.mkdir()
                for relative, value in records.items():
                    target = snapshot / relative
                    target.parent.mkdir()
                    target.write_bytes(value)
                env["PYTHONPATH"] = str(snapshot)
                expected = package_set(environment_packages())
                evidence.update(
                    target_interpreter=sys.executable,
                    target_interpreter_hash=file_hash(
                        Path(sys.executable).resolve(), max_bytes=512_000_000
                    ),
                    input_hash=sha256_bytes(canonical_json_bytes(sorted(expected))),
                    metadata_input_hash=metadata_before,
                    coverage=(
                        "current interpreter distribution METADATA snapshot; "
                        "-S child reads no target code or .pth; "
                        "no claim of complete environment coverage"
                    ),
                    metadata_only=True,
                )
                command = prefix + [
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
                expected = package_set(environment_packages())
                expected = {p for p in expected if p[0] != "cp-knowledge-tools"}
                if not expected:
                    raise ValueError("no pinned public distributions")
                target_input = (
                    "\n".join(f"{n}=={v}" for n, v in sorted(expected)) + "\n"
                ).encode()
                requirements = work / "requirements.txt"
                requirements.write_bytes(target_input)
                evidence.update(
                    input_hash=sha256_bytes(target_input),
                    vulnerability_service="pypi",
                    service_url="https://pypi.org/pypi/{name}/{version}/json",
                    advisory_db_revision=None,
                    target_interpreter=sys.executable,
                    scope=(
                        "public distribution name/version snapshot; "
                        "local first-party distribution excluded"
                    ),
                )
                command = prefix + [
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
                    "--timeout",
                    "15",
                    "--cache-dir",
                    str(work / "cache"),
                ]
            elif name == "gitleaks":
                # Upstream loads this file even with --gitleaks-ignore-path.
                if (root / ".gitleaksignore").exists() or (
                    root / ".gitleaksignore"
                ).is_symlink():
                    raise ValueError(
                        "target .gitleaksignore needs explicit scope review"
                    )
                config = work / "gitleaks.toml"
                config.write_text(
                    "[extend]\nuseDefault = true\n"
                    '[[allowlists]]\ndescription = "Explicit tool/cache exclusions"\n'
                    "paths = ['''(^|/)(\\.git|\\.venv|artifacts|__pycache__|"
                    "\\.mypy_cache|\\.pytest_cache|\\.ruff_cache)(/|$)''']\n"
                )
                ignore = work / "empty.ignore"
                ignore.write_text("")
                directory_before = directory_input(root)
                evidence.update(directory_before)
                evidence.update(
                    config_hash=file_hash(config),
                    scope=(
                        "directory working tree; no history, symlink following, "
                        "archive or encoded-content expansion"
                    ),
                    exclusions=sorted(DIRECTORY_EXCLUSIONS),
                )
                command = prefix + [
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
                    "--ignore-gitleaks-allow",
                    "--config",
                    str(config),
                    "--gitleaks-ignore-path",
                    str(ignore),
                ]
            else:
                if sbom is None or not sbom.is_absolute():
                    raise ValueError("Grant requires an explicit local SBOM")
                source_hash = file_hash(sbom)
                source = sbom.read_bytes()
                if sha256_bytes(source) != source_hash:
                    raise ValueError("SBOM changed while reading")
                target_input = safe_sbom(json.loads(source))
                expected = package_set(json.loads(target_input)["components"])
                local = work / "input.sbom.json"
                local.write_bytes(target_input)
                evidence.update(
                    input_hash=sha256_bytes(target_input),
                    source_hash=source_hash,
                    scope=(
                        "Grant 0.6.8 list on local sanitized CycloneDX1.6; "
                        "no Grant policy decision"
                    ),
                )
                command = prefix + [
                    "list",
                    str(local),
                    "--disable-file-search",
                    "--output",
                    "json",
                ]
            result = execute(
                command, work, timeout, environment=env, work_budget=(work, 20_000_000)
            )
            evidence.update(
                finished_at=datetime.now(UTC).isoformat(),
                duration_seconds=result.duration,
            )
            if result.problem:
                report.check(
                    name,
                    "incomplete",
                    kind="external_tool_finding",
                    reason=result.problem,
                    **evidence,
                )
                return None
            if result.code is None:
                raise ValueError("scanner did not finish")
            payload = json.loads(result.output)
            normalized = normalize(name, result.code, payload)
            if expected is not None:
                items = (
                    payload["components"]
                    if name == "cyclonedx"
                    else (
                        payload["dependencies"]
                        if name == "pip-audit"
                        else normalized["packages"]
                    )
                )
                observed = package_set(items)
                if observed != expected:
                    raise ValueError(
                        "scanner package coverage differs from bound input"
                    )
                evidence["package_coverage"] = "matches_bound_name_version_snapshot"
            # Rebind bytes after execution; no success survives tool/environment drift.
            if binding(executable, admission, name)[1] != bound:
                raise ValueError("scanner changed during execution")
            if (
                directory_before is not None
                and directory_input(root) != directory_before
            ):
                raise ValueError("directory input changed during scanner execution")
            if (
                metadata_before is not None
                and metadata_hash(metadata_input()) != metadata_before
            ):
                raise ValueError(
                    "distribution metadata changed during scanner execution"
                )
            output = safe_sbom(payload) if name == "cyclonedx" else None
            if output is not None:
                evidence["sbom_hash"] = sha256_bytes(output)
                evidence["sbom_projection"] = (
                    "minimal component/license metadata; "
                    "free-form license names omitted"
                )
            report.check(
                name,
                "passed",
                kind="external_tool_finding",
                output_hash=sha256_bytes(result.output),
                summary=normalized,
                execution_status="completed",
                protocol_status="compatible",
                **evidence,
            )
            if normalized["result"] == "findings" or normalized.get(
                "unresolved_license_count"
            ):
                report.findings.append(
                    {
                        "code": f"{name}_findings",
                        "severity": "review",
                        "information_class": "external_tool_finding",
                        "rule_home": "CPKS-POL-SW-SUPPLY",
                        "evidence_refs": [sha256_bytes(result.output)],
                        "recommended_disposition": (
                            "Review actual use, relevance "
                            "and exposure; no automatic rejection."
                        ),
                    }
                )
                report.check(
                    f"{name}_contextual_review",
                    "review_required",
                    required=False,
                    kind="external_tool_finding",
                    reason="Scanner finding needs contextual disposition.",
                )
            return output
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        report.check(
            name,
            "incomplete",
            kind="external_tool_finding",
            reason=str(exc)
            if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError)
            else type(exc).__name__,
            **evidence,
        )
        return None
