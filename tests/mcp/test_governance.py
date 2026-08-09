from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.mcp.cp_wiki.governance import (
    ActiveArtifactNotFoundError,
    ArtifactIntegrityError,
    MultipleActiveArtifactsError,
    read_active_artifact,
    resolve_active_artifact,
    resolve_governance_bundle,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault


def _write_artifact(
    root: Path,
    relative_path: str,
    *,
    artifact_id: str,
    version: str,
    status: str,
    former_ids: list[str] | None = None,
    canonical_path: str | None = None,
    document_type: str = "specification",
    title: str = "Example Specification",
) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "document_type": document_type,
        {
            "specification": "specification_id",
            "work_package": "work_package_id",
        }[document_type]: artifact_id,
        "title": title,
        "version": version,
        "status": status,
        "evidence_class": (
            "active_constraint" if status == "active" else "committed_target"
        ),
        "canonical_path": canonical_path or relative_path,
    }
    if former_ids:
        frontmatter["former_ids"] = former_ids

    content = (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n# Example Specification\n\nBody.\n"
    )
    path.write_text(content, encoding="utf-8")


def test_active_system_work_package_in_development_context_is_integral(
    tmp_path: Path,
) -> None:
    relative_path = (
        "Development/cpKnowledgeSystem/Work Packages/"
        "CPKS-WP-001 System Work Package.md"
    )
    _write_artifact(
        tmp_path,
        relative_path,
        artifact_id="CPKS-WP-001",
        version="0.1",
        status="active",
        document_type="work_package",
        title="System Work Package",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "CPKS-WP-001")

    assert resolution.integrity_ok is True
    assert resolution.relative_path == relative_path


def test_active_component_work_package_in_development_context_is_integral(
    tmp_path: Path,
) -> None:
    relative_path = (
        "Development/cpKnowledgeTools/Work Packages/"
        "CPKT-WP-001 Project Document Validation Engine für cp-wiki.md"
    )
    _write_artifact(
        tmp_path,
        relative_path,
        artifact_id="CPKT-WP-001",
        version="0.1",
        status="active",
        document_type="work_package",
        title="Project Document Validation Engine für cp-wiki",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "CPKT-WP-001")

    assert resolution.integrity_ok is True
    assert resolution.relative_path == relative_path


@pytest.mark.parametrize("closed_zone", ["Archive", "History"])
def test_active_work_package_in_closed_development_zone_fails_integrity(
    tmp_path: Path,
    closed_zone: str,
) -> None:
    relative_path = (
        f"Development/cpKnowledgeTools/Work Packages/{closed_zone}/"
        "CPKT-WP-002 Closed Work Package.md"
    )
    _write_artifact(
        tmp_path,
        relative_path,
        artifact_id="CPKT-WP-002",
        version="0.1",
        status="active",
        document_type="work_package",
        title="Closed Work Package",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "CPKT-WP-002")

    assert resolution.integrity_ok is False
    assert {issue.code for issue in resolution.integrity_issues} == {
        "active_artifact_in_inactive_zone"
    }


def test_active_specification_in_development_still_fails_integrity(
    tmp_path: Path,
) -> None:
    relative_path = (
        "Development/cpKnowledgeTools/Specifications/"
        "CPKT-SPEC-TEST Example Specification.md"
    )
    _write_artifact(
        tmp_path,
        relative_path,
        artifact_id="CPKT-SPEC-TEST",
        version="0.1",
        status="active",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "CPKT-SPEC-TEST")

    assert resolution.integrity_ok is False
    assert {issue.code for issue in resolution.integrity_issues} == {
        "active_artifact_in_inactive_zone"
    }


def test_resolve_active_artifact_ignores_newer_draft(tmp_path: Path) -> None:
    _write_artifact(
        tmp_path,
        "Systems/Example/EX-SPEC-ONE Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="active",
    )
    _write_artifact(
        tmp_path,
        "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.1",
        status="draft",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")

    assert resolution.version == "1.0"
    assert resolution.status == "active"
    assert resolution.integrity_ok is True
    assert resolution.relative_path.startswith("Systems/")


def test_resolve_active_artifact_supports_former_id(tmp_path: Path) -> None:
    _write_artifact(
        tmp_path,
        "Systems/Example/EX-SPEC-NEW Example Specification.md",
        artifact_id="EX-SPEC-NEW",
        version="1.0",
        status="active",
        former_ids=["EX-SPEC-OLD"],
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "EX-SPEC-OLD")

    assert resolution.stable_id == "EX-SPEC-NEW"
    assert resolution.resolved_via == "former_id"


def test_canonically_equivalent_unicode_paths_pass_integrity(
    tmp_path: Path,
) -> None:
    actual_path = "Systems/Example/EX-SPEC-ONE Specification fu\u0308r Test.md"
    canonical_path = "Systems/Example/EX-SPEC-ONE Specification für Test.md"
    _write_artifact(
        tmp_path,
        actual_path,
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="active",
        canonical_path=canonical_path,
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")

    assert resolution.integrity_ok is True
    assert "canonical_path_mismatch" not in {
        issue.code for issue in resolution.integrity_issues
    }
    assert resolution.canonical_path == canonical_path
    assert resolution.relative_path == actual_path


def test_duplicate_same_version_is_reported_as_integrity_issue(tmp_path: Path) -> None:
    _write_artifact(
        tmp_path,
        "Systems/Example/EX-SPEC-ONE Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="active",
    )
    _write_artifact(
        tmp_path,
        "Development/Example/EX-SPEC-ONE@1.0 Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="draft",
    )

    resolution = resolve_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")

    assert resolution.integrity_ok is False
    assert {
        issue.code for issue in resolution.integrity_issues
    } == {"duplicate_stable_id_and_version"}

    with pytest.raises(ArtifactIntegrityError):
        read_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")


def test_multiple_active_artifacts_fail_closed(tmp_path: Path) -> None:
    _write_artifact(
        tmp_path,
        "Systems/One/EX-SPEC-ONE Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="active",
    )
    _write_artifact(
        tmp_path,
        "Systems/Two/EX-SPEC-ONE Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.1",
        status="active",
    )

    with pytest.raises(MultipleActiveArtifactsError):
        resolve_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")


def test_read_active_artifact_returns_live_document(tmp_path: Path) -> None:
    _write_artifact(
        tmp_path,
        "Systems/Example/EX-SPEC-ONE Example Specification.md",
        artifact_id="EX-SPEC-ONE",
        version="1.0",
        status="active",
    )

    resolution, document = read_active_artifact(Vault(tmp_path), "EX-SPEC-ONE")

    assert resolution.integrity_ok is True
    assert document.frontmatter["specification_id"] == "EX-SPEC-ONE"
    assert "Body." in document.body


def test_resolve_governance_bundle_preserves_order_and_deduplicates(
    tmp_path: Path,
) -> None:
    for artifact_id in ("EX-SPEC-ONE", "EX-SPEC-TWO"):
        _write_artifact(
            tmp_path,
            f"Systems/Example/{artifact_id} Example Specification.md",
            artifact_id=artifact_id,
            version="1.0",
            status="active",
        )

    bundle = resolve_governance_bundle(
        Vault(tmp_path),
        ["EX-SPEC-TWO", "EX-SPEC-ONE", "EX-SPEC-TWO"],
    )

    assert [item.stable_id for item in bundle] == ["EX-SPEC-TWO", "EX-SPEC-ONE"]


def test_missing_active_artifact_fails(tmp_path: Path) -> None:
    with pytest.raises(ActiveArtifactNotFoundError):
        resolve_active_artifact(Vault(tmp_path), "EX-SPEC-MISSING")
