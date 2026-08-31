"""Dependency inventory and delta evidence, never dependency acceptance."""

from __future__ import annotations

import importlib.metadata
import json
import os
import tempfile
import tomllib
from pathlib import Path

from .report import Report, persist_blob
from .repository import bounded_path, file_hash, repository_state


def inventory(root: Path) -> dict:
    path = bounded_path(root, "pyproject.toml")
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    project = document.get("project", {})
    installed = []
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        installed.append(
            {
                "name": metadata.get("Name", "unknown"),
                "version": distribution.version,
                "license_expression": metadata.get("License-Expression"),
            }
        )
    locks = {
        name: file_hash(bounded_path(root, name))
        for name in ("uv.lock", "poetry.lock", "Pipfile.lock")
        if bounded_path(root, name).is_file()
    }
    return {
        "manifest_hash": file_hash(path),
        "runtime_dependencies": project.get("dependencies", []),
        "optional_dependencies": project.get("optional-dependencies", {}),
        "build_dependencies": document.get("build-system", {}).get("requires", []),
        "lock_hashes": locks,
        "installed": sorted(
            installed, key=lambda item: (item["name"].casefold(), item["version"])
        ),
        "inventory_scope": "current interpreter snapshot; not a complete SBOM",
        "acceptance": "not_evaluated",
        "vulnerabilities": "not_checked",
        "provenance": "not_verified",
        "candidate_health": "not_checked",
    }


def read_previous(root: Path, path: str) -> dict:
    target = bounded_path(root, path)
    if not target.is_relative_to(root / "artifacts" / "assurance"):
        raise ValueError("previous evidence must be under artifacts/assurance")
    file_hash(target)  # bounded regular-file preflight
    payload = json.loads(target.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "cpks.assurance/1"
    ):
        raise ValueError("unsupported previous evidence schema")
    if not isinstance(payload.get("repository_state"), dict):
        raise ValueError("previous evidence repository_state must be an object")
    for key in ("checks", "applicable_rules"):
        items = payload.get(key)
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise ValueError(f"previous evidence {key} must be a list of objects")
    for rule in payload["applicable_rules"]:
        if not all(
            isinstance(rule.get(k), str)
            for k in ("stable_id", "current_state_fingerprint")
        ):
            raise ValueError("previous rule evidence is incomplete")
    if payload.get("repository_state", {}).get("root") != str(root):
        raise ValueError("previous evidence belongs to another repository")
    return payload


def supply_chain(
    root: Path,
    *,
    profile: str,
    previous: str | None = None,
    tools: dict[str, Path] | None = None,
    allow_network: bool = False,
    sbom: Path | None = None,
    admission_manifest: Path | None = None,
    retain_sbom: bool = False,
    timeout: int = 300,
) -> Report:
    if profile not in {"research", "admission", "deep-review", "delta"}:
        raise ValueError("unknown supply-chain profile")
    if profile == "research" and tools:
        raise ValueError("research profile is static; use another profile for scanners")
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be between 1 and 3600 seconds per scanner")
    if retain_sbom and (profile == "research" or not tools or "cyclonedx" not in tools):
        raise ValueError("SBOM retention requires an explicit CycloneDX scanner")
    state = repository_state(root)
    root = Path(state["root"])
    report = Report(
        {
            "operation": "supply-chain",
            "profile": profile,
            "inventory_target": "current_interpreter",
            "scanner_environment": "separately_admitted_tools",
            "sbom_retention": "sanitized_generated_only" if retain_sbom else "none",
        },
        state,
        changed_paths=state["changed_paths"],
    )
    current = inventory(root)
    report.check("dependency_inventory", "passed", inventory=current)
    if not current["lock_hashes"]:
        report.warnings.append(
            "No supported lockfile: dependency resolution is not reproducible."
        )
    report.warnings.append(
        "License strings and scanner findings are evidence, never adoption approval."
    )
    if profile == "delta":
        if previous is None:
            report.check(
                "dependency_delta",
                "incomplete",
                reason="--previous evidence is required",
            )
        else:
            old = read_previous(root, previous)
            prior = next(
                (
                    c.get("inventory")
                    for c in old.get("checks", [])
                    if c.get("name") == "dependency_inventory"
                ),
                None,
            )
            if not isinstance(prior, dict):
                raise ValueError("previous evidence has no dependency inventory")
            changed = [name for name in current if current[name] != prior.get(name)]
            report.check(
                "dependency_delta",
                "passed",
                changed_dimensions=changed,
                previous_hash=file_hash(root / previous),
            )
            if changed:
                report.findings.append(
                    {
                        "code": "dependency_delta",
                        "severity": "review",
                        "information_class": "dependency_state",
                        "rule_home": "CPKS-POL-SW-SUPPLY",
                        "evidence_refs": [previous],
                        "dimensions": changed,
                        "recommended_disposition": "Review material delta only.",
                    }
                )
    generated_sbom = None
    if profile != "research":
        generated_sbom = _scanner_stack(
            report,
            root,
            tools=tools or {},
            required_stack=profile in {"admission", "deep-review"},
            admission_manifest=admission_manifest,
            allow_network=allow_network,
            sbom=sbom,
            timeout=timeout,
        )
        for name, reason in (
            ("provenance", "Assess source identity, origin and integrity context."),
            ("candidate_health", "Assess maintenance and project health context."),
            ("license_legal", "Review license obligations against intended use."),
            ("human_acceptance", "Acceptance remains with the applicable authority."),
        ):
            report.check(
                name,
                "review_required",
                kind="human_review_required",
                required=False,
                reason=reason,
            )
        if profile == "deep-review":
            report.check(
                "privileged_code_review",
                "review_required",
                kind="human_review_required",
                required=False,
                reason="Review hooks, binaries, copied code, privileges and recovery.",
            )
    try:
        final_state = repository_state(root)
        final_inventory = inventory(root)
        report.check(
            "input_stability",
            "passed"
            if state == final_state and current == final_inventory
            else "incomplete",
            repository_unchanged=state == final_state,
            inventory_unchanged=current == final_inventory,
            reason="Repository and interpreter inventory compared before/after.",
        )
    except OSError, ValueError:
        report.check(
            "input_stability",
            "incomplete",
            reason="Repository or interpreter inventory could not be rechecked.",
        )
    if retain_sbom:
        if generated_sbom is None:
            report.check(
                "sbom_retention",
                "incomplete",
                reason="No validated generated CycloneDX SBOM is available to retain.",
            )
        else:
            path = persist_blob(root, generated_sbom)
            report.evidence_refs.append(str(path))
            report.check(
                "sbom_retention",
                "passed",
                evidence_ref=str(path),
                source="generated_cyclonedx",
                grant_input="explicit_sbom" if sbom is not None else "generated_sbom",
                content_hash=file_hash(path),
            )
    return report


def _scanner_stack(
    report: Report,
    root: Path,
    *,
    tools: dict[str, Path],
    required_stack: bool,
    admission_manifest: Path | None,
    allow_network: bool,
    sbom: Path | None,
    timeout: int,
) -> bytes | None:
    """Run the explicit stack with a private, temporary CycloneDX-to-Grant input."""
    from .admission import load_manifest
    from .scanners import SCANNERS, scan

    if set(tools) - SCANNERS:
        raise ValueError("unsupported scanner")
    admissions = {}
    if tools:
        manifest_path = admission_manifest or (
            root / "config" / "assurance" / "scanner-admission.json"
        )
        try:
            admissions = load_manifest(manifest_path)
        except OSError, ValueError:
            report.check(
                "scanner_admission",
                "incomplete",
                reason="Admission manifest is missing or invalid; no tool executed.",
            )
    generated_sbom = None
    with tempfile.TemporaryDirectory(prefix="cpks-supply-sbom-") as directory:
        generated_path = Path(directory) / "environment.sbom.json"
        for name in ("cyclonedx", "pip-audit", "grant", "gitleaks"):
            if name not in tools:
                if required_stack:
                    report.check(
                        name,
                        "incomplete",
                        kind="external_tool_finding",
                        reason="An explicitly configured admitted scanner is required.",
                    )
                continue
            admission = admissions.get(name)
            if admission is None:
                report.check(
                    name,
                    "incomplete",
                    kind="external_tool_finding",
                    reason="No admitted tool entry is available; tool not executed.",
                )
                continue
            grant_sbom = sbom
            if name == "grant" and grant_sbom is None:
                if generated_sbom is None:
                    report.check(
                        name,
                        "incomplete",
                        kind="external_tool_finding",
                        reason="No validated generated or explicit SBOM is available.",
                    )
                    continue
                grant_sbom = generated_path
            output = scan(
                report,
                root,
                name=name,
                executable=tools[name],
                allow_network=allow_network,
                sbom=grant_sbom if name == "grant" else None,
                timeout=timeout,
                admission=admission,
            )
            if name == "cyclonedx" and output is not None:
                generated_sbom = output
                fd = os.open(
                    generated_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(generated_sbom)
    return generated_sbom
