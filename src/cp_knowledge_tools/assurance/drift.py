"""Read-only state comparison; findings never refresh canonical baselines."""

from __future__ import annotations

import tomllib
from pathlib import Path

from cp_knowledge_tools.mcp.cp_wiki.errors import VaultError
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.operations.governance.resolution import resolve_governance

from .report import Report
from .repository import bounded_path, file_hash, repository_state
from .supply import read_previous


def audit(
    root: Path,
    *,
    scope: str = "system",
    vault_root: Path | None = None,
    rule_ids: tuple[str, ...] = (),
    previous: str | None = None,
    project_path: str | None = None,
) -> Report:
    if scope not in {"system", "project"}:
        raise ValueError("unknown drift scope")
    state = repository_state(root)
    root = Path(state["root"])
    report = Report(
        {"operation": "drift-audit", "scope": scope},
        state,
        changed_paths=state["changed_paths"],
    )
    if previous:
        old = read_previous(root, previous)
        for key in (
            "branch",
            "head",
            "index_fingerprint",
            "input_hashes",
            "tool_versions",
        ):
            if old["repository_state"].get(key) != state[key]:
                report.findings.append(
                    {
                        "code": f"repository_{key}_changed",
                        "severity": "info",
                        "information_class": "repository_state",
                        "rule_home": "CPKS-SPEC-OPS",
                        "evidence_refs": [previous],
                        "recommended_disposition": "Review this snapshot delta.",
                    }
                )
        old_rules = {r["stable_id"]: r for r in old.get("applicable_rules", [])}
    else:
        old_rules = {}
        report.warnings.append(
            "No prior report: current inventory only, no temporal comparison."
        )
    config_path = bounded_path(root, ".codex/config.toml")
    if config_path.is_file():
        config = tomllib.loads(config_path.read_text())
        mode = config.get("sandbox_mode")
        report.check(
            "repository_sandbox_default",
            "failed" if mode == "danger-full-access" else "passed",
            configured_mode=mode,
            note="Effective runtime permissions require host verification.",
        )
    for name, present in {
        "reuse_skill": bounded_path(
            root, ".agents/skills/software-reuse-assessment/SKILL.md"
        ).is_file(),
        "ci_configuration": bounded_path(root, ".github/workflows").is_dir(),
        "lockfile": any(
            bounded_path(root, p).is_file()
            for p in ("uv.lock", "poetry.lock", "Pipfile.lock")
        ),
    }.items():
        report.check(
            name,
            "passed" if present else "not_applicable",
            present=present,
            note="Presence alone does not prove operational capability.",
        )
    if vault_root is None:
        report.check(
            "vault_resolution",
            "incomplete",
            reason="--vault-root required for live governance/baseline inspection",
        )
    else:
        vault = Vault(vault_root)
        ids = tuple(dict.fromkeys(("CPKS-BL", *rule_ids)))
        if len(ids) > 20:
            raise ValueError("at most 20 stable rule IDs per audit")
        for stable_id in ids:
            try:
                resolved = resolve_governance(vault, stable_id)
                report.applicable_rules.append(resolved)
                report.check(
                    f"active:{stable_id}",
                    "passed",
                    fingerprint=resolved["current_state_fingerprint"],
                )
                old_rule = old_rules.get(stable_id)
                if (
                    old_rule
                    and old_rule["current_state_fingerprint"]
                    != resolved["current_state_fingerprint"]
                ):
                    report.findings.append(
                        {
                            "code": "active_artifact_changed",
                            "severity": "review",
                            "subject": stable_id,
                            "information_class": resolved["evidence_class"],
                            "rule_home": stable_id,
                            "evidence_refs": [resolved["relative_path"], previous],
                            "recommended_disposition": (
                                "Read active rule and review affected consumers; "
                                "preserve historical validation references."
                            ),
                        }
                    )
            except VaultError as exc:
                report.check(f"active:{stable_id}", "failed", reason=type(exc).__name__)
                report.blockers.append(f"{stable_id}: {type(exc).__name__}")
        if scope == "project":
            if not project_path:
                report.check(
                    "project_context",
                    "incomplete",
                    reason="--project-path must identify the actual Project Home",
                )
            else:
                document = vault.read_document(project_path)
                report.check(
                    "project_context",
                    "passed",
                    path=project_path,
                    fingerprint=file_hash(vault.resolve_path(project_path)),
                    ai_autonomy_level=document.frontmatter.get("ai_autonomy_level"),
                    note="Context observed; execution eligibility is unproven.",
                )
                report.check(
                    "ready_work_eligibility",
                    "incomplete",
                    reason="Read Ready items, dependencies, authority and gates.",
                )
    report.warnings.append(
        "No prose reconciliation, canonical mutation or authority decision."
    )
    return report
