from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.cp_wiki.migrations import (
    repair_project_documents_pdoc_0_1 as repair,
)

BODY = "\n# Synthetic body\n\nBody content stays unchanged.\n"


def _frontmatter(source_path: str) -> dict[str, object]:
    return {
        "type": "project_document",
        "project_key": "synthetic-project",
        "information_role": "architecture_and_reuse_boundaries",
        "title": "Architecture",
        "status": "working",
        "owner": "Owner",
        "created": "2026-08-01",
        "revised": "2026-08-02",
        "language": "en",
        "canonical_path": source_path,
    }


def _write_document(
    vault: Path,
    relative_path: str,
    frontmatter: dict[str, object],
    body: str = BODY,
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n"
        + body,
        encoding="utf-8",
    )
    return path


def _write_report(
    tmp_path: Path,
    source_path: str,
    *,
    total: int = 1,
    current: int = 1,
    history: int = 0,
) -> tuple[Path, str]:
    report = {
        "validator": {
            "name": repair.VALIDATOR_NAME,
            "version": repair.VALIDATOR_VERSION,
        },
        "rule_basis": [repair.RULE_SOURCE],
        "profile": "project_document_complete",
        "inventory": {
            "total": total,
            "current": current,
            "history": history,
            "current_paths": [source_path] if current else [],
            "history_paths": [source_path] if history else [],
        },
    }
    raw = json.dumps(report, sort_keys=True).encode("utf-8")
    path = tmp_path / "report.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _fixture(
    tmp_path: Path,
    *,
    target_path: str | None = None,
) -> tuple[Path, Path, repair.MigrationSpec, str]:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_path = "Projects/Internal/Synthetic/Architecture.md"
    frontmatter = _frontmatter(source_path)
    _write_document(vault, source_path, frontmatter)
    spec = repair.MigrationSpec(
        source_path=source_path,
        target_path=target_path or source_path,
        expected_frontmatter=frontmatter,
        expected_body_sha256=repair._body_sha256(BODY),
        updates={
            "document_key": "architecture",
            "version": "1.0",
            "revised": "2026-08-09",
        },
    )
    report_path, report_sha256 = _write_report(tmp_path, source_path)
    return vault, report_path, spec, report_sha256


def _build(
    vault: Path,
    report_path: Path,
    spec: repair.MigrationSpec,
    report_sha256: str,
) -> repair.MigrationPlan:
    return repair.build_migration_plan(
        vault,
        report_path,
        specs=(spec,),
        expected_report_sha256=report_sha256,
        expected_inventory=(1, 1, 0),
    )


def test_dry_run_plan_is_report_bound_and_does_not_modify_source(
    tmp_path: Path,
) -> None:
    vault, report_path, spec, report_sha256 = _fixture(tmp_path)
    source = vault / spec.source_path
    before = source.read_bytes()

    plan = _build(vault, report_path, spec, report_sha256)

    assert plan.report_sha256 == report_sha256
    assert len(plan.operations) == 1
    assert "+document_key: architecture" in plan.operations[0].diff
    assert "+version: '1.0'" in plan.operations[0].diff
    assert source.read_bytes() == before


def test_preflight_rejects_report_hash_and_inventory_mismatch(
    tmp_path: Path,
) -> None:
    vault, report_path, spec, report_sha256 = _fixture(tmp_path)

    with pytest.raises(repair.MigrationError, match="SHA-256"):
        _build(vault, report_path, spec, "0" * 64)

    with pytest.raises(repair.MigrationError, match="Unexpected report inventory"):
        repair.build_migration_plan(
            vault,
            report_path,
            specs=(spec,),
            expected_report_sha256=report_sha256,
            expected_inventory=(9, 8, 1),
        )


@pytest.mark.parametrize("drift", ["frontmatter", "body"])
def test_preflight_rejects_document_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    vault, report_path, spec, report_sha256 = _fixture(tmp_path)
    if drift == "frontmatter":
        changed = _frontmatter(spec.source_path)
        changed["title"] = "Changed"
        _write_document(vault, spec.source_path, changed)
        expected_message = "Frontmatter drift"
    else:
        _write_document(
            vault,
            spec.source_path,
            _frontmatter(spec.source_path),
            BODY + "Changed\n",
        )
        expected_message = "Document body drift"

    with pytest.raises(repair.MigrationError, match=expected_message):
        _build(vault, report_path, spec, report_sha256)


def test_preflight_rejects_existing_rename_target(tmp_path: Path) -> None:
    target = "Projects/Internal/Synthetic/Architecture renamed.md"
    vault, report_path, spec, report_sha256 = _fixture(
        tmp_path,
        target_path=target,
    )
    _write_document(vault, target, _frontmatter(target))

    with pytest.raises(repair.MigrationError, match="target already exists"):
        _build(vault, report_path, spec, report_sha256)


def test_apply_requires_report_confirmation_and_performs_exact_rename(
    tmp_path: Path,
) -> None:
    target = "Projects/Internal/Synthetic/architecture@1.0 Architecture.md"
    vault, report_path, spec, report_sha256 = _fixture(
        tmp_path,
        target_path=target,
    )
    plan = _build(vault, report_path, spec, report_sha256)

    with pytest.raises(repair.MigrationError, match="confirmation"):
        repair.apply_migration(plan, "")

    repair.apply_migration(plan, report_sha256)

    assert not (vault / spec.source_path).exists()
    migrated = (vault / target).read_text(encoding="utf-8")
    raw_frontmatter, body = repair._split_frontmatter(migrated)
    frontmatter = repair._normalize(yaml.safe_load(raw_frontmatter))
    assert frontmatter["document_key"] == "architecture"
    assert frontmatter["version"] == "1.0"
    assert frontmatter["revised"] == "2026-08-09"
    assert body == BODY


def test_apply_rejects_drift_after_preview(tmp_path: Path) -> None:
    vault, report_path, spec, report_sha256 = _fixture(tmp_path)
    plan = _build(vault, report_path, spec, report_sha256)
    source = vault / spec.source_path
    source.write_bytes(source.read_bytes() + b"drift")

    with pytest.raises(repair.MigrationError, match="drifted after preview"):
        repair.apply_migration(plan, report_sha256)


def test_static_manifest_is_exactly_the_authorized_nine_document_inventory() -> None:
    assert len(repair.MIGRATIONS) == 9
    assert len({item.source_path for item in repair.MIGRATIONS}) == 9
    assert sum(
        item.source_path != item.target_path for item in repair.MIGRATIONS
    ) == 2
    assert all(item.updates["version"] == "1.0" for item in repair.MIGRATIONS)
    assert all(
        item.updates["revised"] == repair.MIGRATION_DATE
        for item in repair.MIGRATIONS
    )
