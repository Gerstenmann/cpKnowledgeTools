"""Dependency inventory and delta evidence, never dependency acceptance."""

from __future__ import annotations

import importlib.metadata
import json
import tomllib
from pathlib import Path

from .report import Report
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
) -> Report:
    if profile not in {"research", "admission", "deep-review", "delta"}:
        raise ValueError("unknown supply-chain profile")
    if profile == "research" and tools:
        raise ValueError("research profile is static; use another profile for scanners")
    state = repository_state(root)
    root = Path(state["root"])
    report = Report(
        {"operation": "supply-chain", "profile": profile},
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
    if profile != "research":
        from .scanners import SCANNERS, scan

        if set(tools or {}) - SCANNERS:
            raise ValueError("unsupported scanner")
        for name in (
            "cyclonedx",
            "pip-audit",
            "grant",
            "provenance",
            "candidate_health",
        ):
            if tools and name in tools:
                scan(
                    report,
                    root,
                    name=name,
                    executable=tools[name],
                    allow_network=allow_network,
                    sbom=sbom,
                )
                continue
            report.check(
                name,
                "incomplete",
                kind="external_tool_finding",
                reason="External evidence or applicable human assessment required.",
            )
        if tools and "gitleaks" in tools:
            scan(report, root, name="gitleaks", executable=tools["gitleaks"])
        if profile == "deep-review":
            report.check(
                "privileged_code_review",
                "incomplete",
                kind="human_review_required",
                reason="Review hooks, binaries, copied code, privileges and recovery.",
            )
    final_state = repository_state(root)
    report.check(
        "input_stability",
        "passed" if state == final_state else "incomplete",
        reason="Repository state compared before and after evidence collection.",
    )
    return report
