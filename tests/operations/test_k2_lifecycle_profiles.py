from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.operations.governance.lifecycle_profiles import (
    UnsupportedLifecycleProfileError,
    development_path_allowed,
    get_lifecycle_profile,
)
from cp_knowledge_tools.operations.governance.managed_artifacts import (
    inspect_prepared_target,
)
from cp_knowledge_tools.operations.registry import build_standard_registry


@pytest.mark.parametrize(
    ("document_type", "identity_field", "operations", "initial_versions"),
    (
        (
            "specification",
            "specification_id",
            {"artifact.revise", "artifact.activate"},
            ("0.1",),
        ),
        (
            "decision_record",
            "decision_id",
            {"artifact.revise", "artifact.activate"},
            ("0.1", "1.0"),
        ),
        (
            "policy",
            "policy_id",
            {"artifact.revise", "artifact.activate"},
            ("0.1",),
        ),
        (
            "framework",
            "framework_id",
            {"artifact.revise", "artifact.activate"},
            ("0.1",),
        ),
        (
            "process",
            "process_id",
            {"artifact.revise", "artifact.activate"},
            ("0.1",),
        ),
        (
            "work_package",
            "work_package_id",
            {"artifact.transition"},
            ("0.1",),
        ),
    ),
)
def test_k2_profiles_are_type_bound_and_immutable(
    document_type: str,
    identity_field: str,
    operations: set[str],
    initial_versions: tuple[str, ...],
) -> None:
    profile = get_lifecycle_profile(document_type)

    assert profile.document_type == document_type
    assert profile.identity_field == identity_field
    assert set(profile.supported_operations) == operations
    assert profile.initial_versions == initial_versions
    with pytest.raises((AttributeError, TypeError)):
        profile.document_type = "specification"  # type: ignore[misc]


def test_unknown_lifecycle_profile_fails_closed() -> None:
    with pytest.raises(UnsupportedLifecycleProfileError):
        get_lifecycle_profile("manual")


def test_registry_projects_exact_k2_scope() -> None:
    registry = build_standard_registry()

    assert registry.resolve("artifact.revise").spec.supported_scope == {
        "document_types": [
            "decision_record",
            "framework",
            "policy",
            "process",
            "specification",
        ]
    }
    assert registry.resolve("artifact.activate").spec.supported_scope == {
        "document_types": [
            "decision_record",
            "framework",
            "policy",
            "process",
            "specification",
        ],
        "activation_modes": ["initial", "follow_up"],
        "activation_body_modes": [
            "draft_body",
            "owner_prepared_activation_target",
        ],
    }
    assert registry.resolve("artifact.transition").spec.supported_scope == {
        "document_types": ["work_package"],
        "transition_profiles": ["work_package.complete"],
    }


def _prepared(path: Path, frontmatter: dict[str, object]) -> Path:
    path.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n# Prepared\n",
        encoding="utf-8",
    )
    return path


def test_prepared_target_uses_profile_identity_field(tmp_path: Path) -> None:
    path = _prepared(
        tmp_path / "decision.md",
        {
            "document_type": "decision_record",
            "decision_id": "CPKS-DEC-900",
            "version": "1.0",
        },
    )

    assert inspect_prepared_target(path) == (
        "CPKS-DEC-900",
        "1.0",
        "decision_record",
    )


def test_prepared_target_rejects_wrong_identity_field(tmp_path: Path) -> None:
    path = _prepared(
        tmp_path / "decision.md",
        {
            "document_type": "decision_record",
            "specification_id": "CPKS-DEC-900",
            "version": "1.0",
        },
    )

    with pytest.raises(ValueError, match="decision_id"):
        inspect_prepared_target(path)



@pytest.mark.parametrize(
    ("process_domain", "process_id", "directory"),
    (
        ("knowledge_management", "KM-P99", "Knowledge Management"),
        ("development", "DEV-P99", "Development"),
        ("operations", "OPS-P99", "Operations"),
        ("ai_working", "AIW-P99", "Agent Integration"),
    ),
)
def test_process_development_paths_follow_current_process_domains(
    process_domain: str,
    process_id: str,
    directory: str,
) -> None:
    profile = get_lifecycle_profile("process")
    relative = (
        f"Development/cpKnowledgeSystem/Processes/{directory}/"
        f"{process_id}@0.1 Example Process.md"
    )
    frontmatter = {
        "document_type": "process",
        "process_id": process_id,
        "title": "Example Process",
        "version": "0.1",
        "process_domain": process_domain,
    }
    assert development_path_allowed(profile, relative, frontmatter)


def test_governance_process_keeps_governance_draft_context() -> None:
    profile = get_lifecycle_profile("process")
    relative = (
        "Development/cpKnowledgeSystem/Governance/Draft Processes/"
        "GOV-P99@0.1 Example Process.md"
    )
    frontmatter = {
        "document_type": "process",
        "process_id": "GOV-P99",
        "title": "Example Process",
        "version": "0.1",
        "process_domain": "governance",
    }
    assert development_path_allowed(profile, relative, frontmatter)
