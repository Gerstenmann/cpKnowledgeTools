from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.validation import project_documents
from cp_knowledge_tools.validation.project_documents import (
    PROFILE_COMPLETE,
    PROFILE_CURRENT,
    PROFILE_HISTORY,
    ProjectDocumentValidationError,
    run_self_test,
    validate_project_documents,
    write_project_document_reports,
)


def _frontmatter(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "type": "project_document",
        "project_key": "synthetic-project",
        "document_key": "architecture",
        "information_role": "architecture_and_reuse_boundaries",
        "title": "Architecture",
        "version": "1.0",
        "status": "current",
        "owner": "Owner",
        "created": "2026-08-01",
        "revised": "2026-08-02",
        "canonical_path": "Projects/Internal/Synthetic/Architecture.md",
    }
    data.update(overrides)
    return data


def _write_document(
    vault: Path,
    relative_path: str,
    frontmatter: dict[str, object],
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n# Synthetic fixture\n",
        encoding="utf-8",
    )
    return path


def _codes(result: project_documents.ProjectDocumentValidationResult) -> set[str]:
    return {item.code for item in result.findings}


def test_valid_current_project_document_has_no_findings(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(),
    )

    result = validate_project_documents(tmp_path, PROFILE_CURRENT)

    assert result.inventory == {
        "total": 1,
        "current": 1,
        "history": 0,
        "current_paths": ["Projects/Internal/Synthetic/Architecture.md"],
        "history_paths": [],
    }
    assert result.findings == ()


def test_valid_historical_project_document_has_no_findings(tmp_path: Path) -> None:
    relative_path = (
        "Projects/Internal/Synthetic/Archive/"
        "architecture@1.0 Architecture.md"
    )
    _write_document(
        tmp_path,
        relative_path,
        _frontmatter(status="superseded", canonical_path=relative_path),
    )

    result = validate_project_documents(tmp_path, PROFILE_HISTORY)

    assert result.inventory["history"] == 1
    assert result.findings == ()


def test_profiles_filter_current_and_history_and_ignore_project_portal(
    tmp_path: Path,
) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(),
    )
    historical = (
        "Projects/Internal/Synthetic/Archive/"
        "architecture@1.0 Architecture.md"
    )
    _write_document(
        tmp_path,
        historical,
        _frontmatter(status="archived", canonical_path=historical),
    )
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Synthetic Project.md",
        {"type": "project", "title": "Synthetic Project"},
    )

    current = validate_project_documents(tmp_path, PROFILE_CURRENT)
    history = validate_project_documents(tmp_path, PROFILE_HISTORY)
    complete = validate_project_documents(tmp_path, PROFILE_COMPLETE)

    assert current.inventory["total"] == 1
    assert history.inventory["total"] == 1
    assert complete.inventory["total"] == 2


def test_missing_current_fields_are_warnings(tmp_path: Path) -> None:
    frontmatter = _frontmatter()
    del frontmatter["document_key"]
    del frontmatter["version"]
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        frontmatter,
    )

    result = validate_project_documents(tmp_path)

    missing = [
        item
        for item in result.findings
        if item.code == "project_document_missing_required_field"
    ]
    assert {item.field for item in missing} == {"document_key", "version"}
    assert all(item.severity == "warning" for item in missing)
    assert "project_document_migration_candidate" in _codes(result)


def test_invalid_keys_role_version_status_and_dates_are_reported(
    tmp_path: Path,
) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(
            project_key="Synthetic Project",
            document_key="Architecture_V1",
            information_role="Architecture Role",
            version=1.0,
            status="active",
            created="2026-08-03",
            revised="2026-08-02",
            as_of="2026-99-99",
        ),
    )

    result = validate_project_documents(tmp_path)

    assert {
        "project_document_invalid_project_key",
        "project_document_invalid_document_key",
        "project_document_invalid_information_role",
        "project_document_invalid_version",
        "project_document_invalid_status",
        "project_document_invalid_date",
        "project_document_revised_before_created",
    }.issubset(_codes(result))


def test_unknown_but_valid_information_role_is_info(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(information_role="project_specific_review"),
    )

    result = validate_project_documents(tmp_path)

    finding = next(
        item
        for item in result.findings
        if item.code == "project_document_unknown_information_role"
    )
    assert finding.severity == "info"


def test_canonical_path_and_lifecycle_placement_are_reported(
    tmp_path: Path,
) -> None:
    current_in_archive = (
        "Projects/Internal/Synthetic/Archive/"
        "architecture@1.0 Architecture.md"
    )
    _write_document(
        tmp_path,
        current_in_archive,
        _frontmatter(
            status="working",
            canonical_path="Projects/Internal/Synthetic/Old.md",
        ),
    )
    historical_outside = "Projects/Internal/Synthetic/Historical.md"
    _write_document(
        tmp_path,
        historical_outside,
        _frontmatter(
            document_key="historical",
            title="Historical",
            status="archived",
            canonical_path=historical_outside,
        ),
    )

    result = validate_project_documents(tmp_path)

    assert {
        "project_document_canonical_path_mismatch",
        "project_document_current_in_archive",
        "project_document_historical_outside_archive",
        "project_document_legacy_archive_placement",
    }.issubset(_codes(result))


def test_duplicate_current_project_document_key_is_reported(tmp_path: Path) -> None:
    for directory in ("One", "Two"):
        relative_path = f"Projects/Internal/Synthetic/{directory}/Architecture.md"
        _write_document(
            tmp_path,
            relative_path,
            _frontmatter(canonical_path=relative_path),
        )

    result = validate_project_documents(tmp_path)

    duplicates = [
        item
        for item in result.findings
        if item.code == "project_document_duplicate_current_key"
    ]
    assert len(duplicates) == 2
    assert all(item.severity == "warning" for item in duplicates)


def test_current_and_historical_filename_rules_are_reported(tmp_path: Path) -> None:
    current = "Projects/Internal/Synthetic/Wrong current name.md"
    _write_document(
        tmp_path,
        current,
        _frontmatter(canonical_path=current),
    )
    historical = "Projects/Internal/Synthetic/Archive/Wrong history name.md"
    _write_document(
        tmp_path,
        historical,
        _frontmatter(status="archived", canonical_path=historical),
    )

    result = validate_project_documents(tmp_path)

    assert {
        "project_document_filename_mismatch",
        "project_document_historical_filename_mismatch",
    }.issubset(_codes(result))


def test_versioned_general_relations_are_reported(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(
            governance_refs=["CPKS-DEC-029@1.0"],
            related_documents=["validation-plan@1.0"],
            related_work_packages=["CPKT-WP-001@0.1"],
        ),
    )

    result = validate_project_documents(tmp_path)

    versioned = [
        item
        for item in result.findings
        if item.code == "project_document_versioned_relation"
    ]
    assert len(versioned) == 3
    assert {item.field for item in versioned} == {
        "governance_refs",
        "related_documents",
        "related_work_packages",
    }


def test_dated_roles_require_as_of(tmp_path: Path) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Assessment.md",
        _frontmatter(
            document_key="assessment",
            information_role="current_state_and_gap_assessment",
            title="Assessment",
            canonical_path="Projects/Internal/Synthetic/Assessment.md",
        ),
    )

    result = validate_project_documents(tmp_path)

    assert "project_document_missing_as_of" in _codes(result)


def test_legacy_history_uses_reduced_non_blocking_profile(tmp_path: Path) -> None:
    relative_path = "Projects/Internal/Synthetic/Archive/Legacy.md"
    _write_document(
        tmp_path,
        relative_path,
        {
            "type": "project_document",
            "project_key": "synthetic-project",
            "title": "Legacy",
            "status": "completed",
            "canonical_path": relative_path,
        },
    )

    result = validate_project_documents(tmp_path, PROFILE_HISTORY)

    assert "project_document_legacy_missing_field" in _codes(result)
    assert "project_document_legacy_status" in _codes(result)
    assert "project_document_missing_required_field" not in _codes(result)
    assert {item.severity for item in result.findings} <= {"warning", "info"}


def test_unreadable_project_document_frontmatter_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "Projects/Internal/Synthetic/Broken.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\ntype: project_document\nproject_key: [broken\n---\n",
        encoding="utf-8",
    )

    result = validate_project_documents(tmp_path)

    assert "project_document_unreadable_frontmatter" in _codes(result)
    assert "project_document_migration_candidate" in _codes(result)


def test_validation_never_mutates_vault_input(tmp_path: Path) -> None:
    source = _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(),
    )
    before = source.read_bytes()

    validate_project_documents(tmp_path)

    assert source.read_bytes() == before
    engine_source = Path(project_documents.__file__).read_text(encoding="utf-8")
    assert "auto_" + "fix" not in engine_source
    assert "write_" + "back" not in engine_source


def test_reports_are_structured_and_must_remain_outside_vault(
    tmp_path: Path,
) -> None:
    _write_document(
        tmp_path,
        "Projects/Internal/Synthetic/Architecture.md",
        _frontmatter(information_role="project_specific_review"),
    )
    result = validate_project_documents(tmp_path)
    report_root = tmp_path.parent / f"{tmp_path.name}-reports"

    json_path, markdown_path = write_project_document_reports(
        result, report_root
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["validator"]["version"] == "1.0"
    assert payload["rule_basis"] == ["CPKS-SPEC-PDOC@0.1"]
    assert payload["profile"] == PROFILE_COMPLETE
    assert payload["inventory"]["total"] == 1
    assert payload["summary"]["info"] == 1
    assert "Project Document Validation Report" in markdown_path.read_text(
        encoding="utf-8"
    )

    with pytest.raises(ProjectDocumentValidationError):
        write_project_document_reports(result, tmp_path / "Generated")


def test_only_warning_and_info_severities_are_constructible() -> None:
    with pytest.raises(ValueError):
        project_documents.ProjectDocumentFinding(
            severity="error",
            code="technical",
            message="not allowed",
            path="Projects/Test.md",
        )


def test_engine_self_test_passes_without_filesystem_fixture() -> None:
    assert run_self_test() == {"documents": 1, "findings": 0}
