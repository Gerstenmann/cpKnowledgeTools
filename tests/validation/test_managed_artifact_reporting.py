"""Managed-artifact diagnostics and operation gates at the public scan/CLI seams."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest
import yaml

VALIDATOR = runpy.run_path(
    str(
        Path(__file__).parents[2]
        / "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
    )
)
POLICIES = "Systems/cpKnowledgeSystem/Governance/Policies"


def artifact(
    vault: Path,
    identity: str = "TEST-POL",
    *,
    version: str = "0.1",
    status: str = "active",
    relative: str | None = None,
    extra: dict | None = None,
) -> Path:
    name = identity if status == "active" else f"{identity}@{version}"
    relative = relative or f"{POLICIES}/{name} Policy.md"
    metadata = {
        "document_type": "policy",
        "policy_id": identity,
        "title": "Policy",
        "version": version,
        "status": status,
        "evidence_class": (
            "active_constraint" if status == "active" else "historical_evidence"
        ),
        "owner": "Synthetic Owner",
        "created": "2026-07-20",
        "revised": "2026-07-20",
        "canonical_path": relative,
    }
    if status == "active":
        metadata.update(
            approved_by="Synthetic Owner",
            approved_at="2026-07-20",
            effective_from="2026-07-20",
        )
    metadata.update(extra or {})
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n# Policy\n",
        encoding="utf-8",
    )
    return path


def run_cli(monkeypatch, tmp_path: Path, vault: Path, *arguments: str):
    reports = tmp_path / "reports"
    monkeypatch.setattr(
        sys,
        "argv",
        ["validator", "--vault", str(vault), "--report-root", str(reports), *arguments],
    )
    result = VALIDATOR["main"]()
    report = next(reports.glob("*/validation-report-v3-2.json"))
    markdown = report.with_suffix(".md").read_text()
    return result, json.loads(report.read_text()), markdown


@pytest.mark.parametrize("value", ['"1.2.3" # release', "1.2.3"])
def test_valid_yaml_version_string_is_not_a_formatting_error(tmp_path, value):
    path = artifact(tmp_path, version="1.2.3")
    text = path.read_text().replace("version: 1.2.3", f"version: {value}")
    path.write_text(text)
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert not any(item.code == "version_must_be_yaml_string" for item in findings)


def test_yaml_number_version_is_still_an_error(tmp_path):
    path = artifact(tmp_path)
    path.write_text(path.read_text().replace("version: '0.1'", "version: 0.1"))
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert any(
        item.code == "version_must_be_yaml_string" and item.severity == "error"
        for item in findings
    )


def test_current_alias_is_advisory_but_missing_target_remains_error(tmp_path):
    artifact(tmp_path, extra={"depends_on": ["TEST-OLD"]})
    target = artifact(tmp_path, "TEST-NEW", extra={"former_ids": ["TEST-OLD"]})
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert not [item for item in findings if item.severity == "error"]
    assert any(
        item.code == "legacy_artifact_id_in_current_reference" for item in findings
    )
    target.unlink()
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert any(
        item.code == "no_active_reference_target" and item.severity == "error"
        for item in findings
    )


def test_central_archive_resolves_provenance_and_reports_real_path_drift(tmp_path):
    artifact(tmp_path, extra={"validated_against": ["TEST-HISTORY@0.1"]})
    historical = artifact(
        tmp_path,
        "TEST-HISTORY",
        status="superseded",
        relative="Archive/Systems/TEST-HISTORY@0.1 Policy.md",
        extra={"canonical_path": "Systems/Archive/TEST-HISTORY@0.1 Policy.md"},
    )
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert not any(item.code == "unresolved_versioned_reference" for item in findings)
    assert any(
        item.code == "canonical_path_mismatch"
        and item.path == historical.relative_to(tmp_path).as_posix()
        and item.severity == "error"
        for item in findings
    )


@pytest.mark.parametrize(
    "history_path",
    [
        "Archive/Systems/TEST-POL@0.1 Policy.md",
        "Systems/Other/Archive/TEST-POL@0.1 Policy.md",
    ],
)
def test_initial_version_uses_full_lifecycle_inventory(tmp_path, history_path):
    artifact(
        tmp_path,
        version="0.2",
        extra={"created": "2026-08-01", "revised": "2026-08-01"},
    )
    artifact(
        tmp_path,
        status="superseded",
        relative=history_path,
        extra={"created": "2026-07-30", "revised": "2026-07-30"},
    )
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert not any(item.code == "invalid_initial_artifact_version" for item in findings)


def test_missing_predecessor_is_incomplete_history_not_proven_wrong_start(tmp_path):
    artifact(
        tmp_path,
        version="0.2",
        extra={
            "created": "2026-08-01",
            "revised": "2026-08-01",
            "source_artifact": "TEST-POL@0.1",
        },
    )
    _, findings, _, _ = VALIDATOR["validate_vault"](tmp_path)
    assert not any(item.code == "invalid_initial_artifact_version" for item in findings)
    assert any(
        item.code == "version_history_incomplete"
        and item.finding_status == "incomplete"
        for item in findings
    )
    assert any(item.code == "unresolved_versioned_reference" for item in findings)


def test_report_mode_does_not_claim_errors_stop_work(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    artifact(vault, extra={"version": 0.1})
    code, report, markdown = run_cli(monkeypatch, tmp_path, vault)
    assert code == 0
    assert report["summary"]["error"] > 0
    assert report["conformance"]["status"] == "nonconformant"
    assert report["gate"]["status"] == "not_requested"
    assert "contains blocking findings" not in markdown
    assert all(item["blocking_operation"] is None for item in report["findings"])
    assert all(item["rule_source"] for item in report["findings"])
    assert all(item["validation_profile"] for item in report["findings"])


def test_gate_preserves_unrelated_errors_without_stopping_target(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = artifact(vault)
    unrelated = artifact(vault, "TEST-OTHER", extra={"version": 0.1})
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 0
    assert report["gate"]["status"] == "clear"
    assert report["gate"]["authority_evaluated"] is False
    assert report["conformance"]["status"] == "nonconformant"
    errors = [item for item in report["findings"] if item["severity"] == "error"]
    assert errors and all(
        item["path"] == unrelated.relative_to(vault).as_posix() for item in errors
    )
    assert all(item["gate_effect"] == "out_of_scope" for item in errors)


def test_gate_blocks_actual_target_error_with_rule_and_reason(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = artifact(vault, extra={"version": 0.1})
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 1
    assert report["gate"]["status"] == "blocked"
    blocking = [item for item in report["findings"] if item["gate_effect"] == "blocks"]
    assert blocking
    assert all(item["blocking_operation"] == "artifact.activate" for item in blocking)
    assert all(item["gate_reason"] and item["rule_source"] for item in blocking)


def test_gate_does_not_ignore_integrity_of_required_reference(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = artifact(vault, extra={"depends_on": ["TEST-DEPENDENCY"]})
    dependency = artifact(
        vault, "TEST-DEPENDENCY", extra={"canonical_path": "wrong.md"}
    )
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 1
    assert any(
        item["path"] == dependency.relative_to(vault).as_posix()
        and item["code"] == "canonical_path_mismatch"
        and item["gate_effect"] == "blocks"
        for item in report["findings"]
    )


def test_historical_reference_does_not_pull_obsolete_dependencies_into_gate(
    monkeypatch, tmp_path
):
    vault = tmp_path / "vault"
    target = artifact(vault, extra={"implements_decisions": ["TEST-DECISION@1.0"]})
    artifact(
        vault,
        "TEST-DECISION",
        version="1.0",
        status="superseded",
        relative="Archive/Systems/TEST-DECISION@1.0 Policy.md",
        extra={
            "document_type": "decision_record",
            "decision_id": "TEST-DECISION",
            "depends_on": ["TEST-NO-LONGER-ACTIVE"],
        },
    )
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 0
    assert report["gate"]["status"] == "clear"


def test_gate_allows_alias_warning_but_blocks_ambiguous_alias(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    target = artifact(vault, extra={"depends_on": ["TEST-OLD"]})
    artifact(vault, "TEST-NEW", extra={"former_ids": ["TEST-OLD"]})
    inventory = VALIDATOR["validate_inventory"](vault)
    gate, findings = VALIDATOR["evaluate_operation_gate"](
        inventory, "artifact.activate", [target.relative_to(vault).as_posix()]
    )
    assert gate.status == "clear"
    assert any(
        item.code == "legacy_artifact_id_in_current_reference"
        and item.gate_effect == "non_blocking"
        for item in findings
    )

    artifact(vault, "TEST-CONFLICT", extra={"former_ids": ["TEST-OLD"]})
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 1
    assert any(
        item["code"] == "former_id_claimed_by_multiple_artifacts"
        and item["gate_effect"] == "blocks"
        for item in report["findings"]
    )


@pytest.mark.parametrize("consumer", [False, True])
def test_bootstrap_alias_conflict_on_draft_blocks_affected_line(tmp_path, consumer):
    baseline = artifact(tmp_path, "CPKS-BL")
    target = (
        artifact(tmp_path, extra={"depends_on": ["CPKS-BASELINE"]})
        if consumer
        else baseline
    )
    conflict = artifact(
        tmp_path,
        "TEST-CONFLICT",
        status="draft",
        relative="Development/cpKnowledgeSystem/Governance/TEST-CONFLICT@0.1 Policy.md",
        extra={"former_ids": ["CPKS-BASELINE"]},
    )
    inventory = VALIDATOR["validate_inventory"](tmp_path)
    gate, findings = VALIDATOR["evaluate_operation_gate"](
        inventory, "artifact.activate", [target.relative_to(tmp_path).as_posix()]
    )
    assert gate.status == "blocked"
    assert any(
        item.path == conflict.relative_to(tmp_path).as_posix()
        and item.code == "former_id_claimed_by_multiple_artifacts"
        and item.gate_effect == "blocks"
        for item in findings
    )


@pytest.mark.parametrize("referenced", [False, True])
def test_historical_path_error_blocks_only_its_consumer(
    monkeypatch, tmp_path, referenced
):
    vault = tmp_path / "vault"
    target = artifact(
        vault,
        extra={"validated_against": ["TEST-HISTORY@0.1"]} if referenced else {},
    )
    artifact(
        vault,
        "TEST-HISTORY",
        status="superseded",
        relative="Archive/TEST-HISTORY@0.1 Policy.md",
        extra={"canonical_path": "wrong.md"},
    )
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == (1 if referenced else 0)
    assert any(item["code"] == "canonical_path_mismatch" for item in report["findings"])


def test_gate_exposes_missing_lifecycle_profile_for_required_reference(
    monkeypatch, tmp_path
):
    vault = tmp_path / "vault"
    target = artifact(vault, extra={"depends_on": ["TEST-DEPENDENCY"]})
    artifact(
        vault,
        "TEST-DEPENDENCY",
        relative="Systems/Other/TEST-DEPENDENCY Policy.md",
    )
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.activate",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == 2
    assert report["gate"]["status"] == "incomplete"
    assert report["gate"]["incomplete"][0]["code"] == "reference_profile_incomplete"


@pytest.mark.parametrize("selected", [False, True])
def test_unreadable_file_is_incomplete_only_when_selected(
    monkeypatch, tmp_path, selected
):
    vault = tmp_path / "vault"
    good = artifact(vault)
    unreadable = artifact(vault, "TEST-UNREADABLE")
    unreadable.write_bytes(b"\xff\xfe")
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}
    target = unreadable if selected else good
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.revise",
        "--target",
        target.relative_to(vault).as_posix(),
    )
    assert code == (2 if selected else 0)
    assert any(
        item["code"] == "document_read_incomplete" for item in report["findings"]
    )
    assert {path: path.read_bytes() for path in vault.rglob("*.md")} == before


@pytest.mark.parametrize("relative", ["missing.md", "Projects/unmanaged.md"])
def test_unvalidated_gate_target_is_incomplete(monkeypatch, tmp_path, relative):
    vault = tmp_path / "vault"
    vault.mkdir()
    if relative.startswith("Projects"):
        path = vault / relative
        path.parent.mkdir()
        path.write_text("# Not a managed artifact\n")
    code, report, _ = run_cli(
        monkeypatch,
        tmp_path,
        vault,
        "--gate-operation",
        "artifact.revise",
        "--target",
        relative,
    )
    assert code == 2
    assert report["gate"]["status"] == "incomplete"


def test_explicit_global_conformance_exit_remains_compatible(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    artifact(vault, extra={"version": 0.1})
    code, report, _ = run_cli(monkeypatch, tmp_path, vault, "--strict-exit")
    assert code == 1
    assert report["gate"]["status"] == "not_requested"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--gate-operation", "artifact.activate"],
        ["--target", "target.md"],
        ["--gate-operation", "artifact.activate", "--target", "../outside.md"],
        [
            "--gate-operation",
            "artifact.activate",
            "--target",
            "target.md",
            "--strict-exit",
        ],
    ],
)
def test_invalid_gate_invocation_never_reports_success(
    monkeypatch, tmp_path, arguments
):
    monkeypatch.setattr(
        sys, "argv", ["validator", "--vault", str(tmp_path), *arguments]
    )
    with pytest.raises(SystemExit) as raised:
        VALIDATOR["main"]()
    assert raised.value.code == 2
