from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

from cp_knowledge_tools.cli.cpks import main
from cp_knowledge_tools.mcp.cp_tools.operations import resolve_standard_operation


def _specification(
    *,
    version: str,
    status: str,
    canonical_path: str,
    source_artifact: str | None = None,
) -> str:
    frontmatter = {
        "document_type": "specification",
        "specification_id": "EX-SPEC-CLI",
        "title": "CLI Specification",
        "version": version,
        "status": status,
        "evidence_class": (
            "active_constraint" if status == "active" else "committed_target"
        ),
        "owner": "Owner",
        "created": "2026-08-01",
        "revised": "2026-08-27",
        "governed_by": ["CPKS-POL-GOV-AUTH"],
        "validated_against": ["CPKS-SPEC-ART@0.5"],
        "implements_decisions": ["CPKS-DEC-032@1.0"],
        "canonical_path": canonical_path,
        "supersedes": [],
    }
    if source_artifact:
        frontmatter["source_artifact"] = source_artifact
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n# CLI Specification\n\nOwner-prepared body.\n"
    )


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _managed(
    path: str,
    stable_id: str,
    version: str,
    document_type: str,
) -> str:
    identity = {
        "policy": "policy_id",
        "specification": "specification_id",
        "process": "process_id",
        "decision_record": "decision_id",
    }[document_type]
    frontmatter = {
        "document_type": document_type,
        identity: stable_id,
        "title": "Rule Fixture",
        "version": version,
        "status": "active",
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-01",
        "effective_from": "2026-08-01",
        "canonical_path": path,
    }
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nRule.\n"


def _write_cli_authority(vault: Path, contract: dict[str, object]) -> None:
    rules = (
        ("Systems/Rules/CPKS-POL-GOV-AUTH.md", "CPKS-POL-GOV-AUTH", "1.1", "policy"),
        ("Systems/Rules/CPKS-SPEC-ART.md", "CPKS-SPEC-ART", "0.5", "specification"),
        ("Systems/Rules/CPKS-SPEC-OPS.md", "CPKS-SPEC-OPS", "0.7", "specification"),
        ("Processes/Rules/GOV-P01.md", "GOV-P01", "0.4", "process"),
        ("Systems/Rules/CPKS-DEC-016.md", "CPKS-DEC-016", "1.1", "decision_record"),
        ("Systems/Rules/CPKS-DEC-019.md", "CPKS-DEC-019", "1.0", "decision_record"),
        ("Systems/Rules/CPKS-DEC-021.md", "CPKS-DEC-021", "0.1", "decision_record"),
        ("Systems/Rules/CPKS-SPEC-WP.md", "CPKS-SPEC-WP", "0.2", "specification"),
        ("Systems/Rules/CPKS-DEC-032.md", "CPKS-DEC-032", "1.0", "decision_record"),
    )
    for path, stable_id, version, document_type in rules:
        _write(vault, path, _managed(path, stable_id, version, document_type))
    path = "Development/Test/Work Packages/CPKT-WP-CLI Authority.md"
    frontmatter = {
        "document_type": "work_package",
        "work_package_id": "CPKT-WP-CLI",
        "title": "CLI Authority",
        "version": "0.1",
        "status": "active",
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-27",
        "effective_from": "2026-08-27",
        "canonical_path": path,
        "runtime_authority": contract,
    }
    _write(
        vault,
        path,
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nAuthority.\n",
    )


def test_cpks_version_and_operation_resolution(capsys) -> None:
    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out

    assert main(["operation", "resolve", "artifact.activate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation_id"] == "artifact.activate"
    assert payload["supported_scope"]["document_types"] == [
        "decision_record",
        "framework",
        "policy",
        "process",
        "specification",
    ]


def test_read_only_mcp_resolves_capability_without_execution(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("MCP must not execute an operation")

    monkeypatch.setattr(
        "cp_knowledge_tools.operations.application.OperationApplication.execute",
        forbidden,
    )
    payload = resolve_standard_operation("artifact.activate", "0.1")

    assert payload["read_only"] is True
    assert payload["operation_id"] == "artifact.activate"
    assert "execute" not in payload

    completion = resolve_standard_operation("artifact.transition", "0.1")
    assert completion["read_only"] is True
    assert completion["supported_scope"] == {
        "document_types": ["work_package"],
        "transition_profiles": ["work_package.complete"],
    }

    server_source = (
        Path(__file__).parents[2] / "src/cp_knowledge_tools/mcp/cp_tools/server.py"
    ).read_text(encoding="utf-8")
    assert (
        '@mcp.tool(annotations=read_only_annotations("Resolve standard operation"))'
        in server_source
    )


def test_cli_checks_and_applies_activation_in_temp_vault(
    tmp_path: Path, capsys
) -> None:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    active = "Systems/Example/EX-SPEC-CLI CLI Specification.md"
    draft = "Development/Example/EX-SPEC-CLI@1.1 CLI Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-CLI@1.0 CLI Specification.md"
    _write(
        vault,
        active,
        _specification(version="1.0", status="active", canonical_path=active),
    )
    _write(
        vault,
        draft,
        _specification(
            version="1.1",
            status="draft",
            canonical_path=draft,
            source_artifact="EX-SPEC-CLI@1.0",
        ),
    )
    contract = {
        "contract": "cpks.runtime_authority",
        "contract_version": "0.1",
        "authority": {
            "ref": "CPKT-WP-CLI",
            "version": "0.1",
            "class": "work_package",
            "issuer": "Owner",
        },
        "operations": ["artifact.activate"],
        "targets": [
            {
                "stable_id": "EX-SPEC-CLI",
                "version": "1.1",
                "artifact_class": "specification",
                "target_kind": "cp-wiki",
            }
        ],
        "scope": {
            "document_types": ["specification"],
            "mutation_scope": ["lifecycle_activation"],
        },
        "environment": {
            "kind": "local_vault",
            "identity": vault.resolve().as_uri(),
        },
        "effects": {
            "mutate": True,
            "activate": True,
            "remote_effects": False,
        },
        "validity": {
            "effective_from": "2026-08-27T00:00:00+00:00",
            "expires_at": "2026-09-30T00:00:00+00:00",
        },
        "approval": {
            "required": False,
            "approved_by": None,
            "approved_at": None,
            "evidence_ref": None,
        },
    }
    _write_cli_authority(vault, contract)
    contract_path = tmp_path / "runtime-authority.yaml"
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    common = [
        "artifact",
        "activate",
        "EX-SPEC-CLI",
        "--draft-path",
        draft,
        "--archive-path",
        archive,
        "--approved-by",
        "Owner",
        "--approved-at",
        "2026-08-27",
        "--effective-from",
        "2026-08-28",
        "--vault-root",
        str(vault),
        "--run-root",
        str(runs),
        "--idempotency-key",
        "cli-activation",
        "--authority-ref",
        "CPKT-WP-CLI@0.1",
        "--authority-contract",
        str(contract_path),
        "--target-classification",
        "test",
    ]

    assert main([*common, "--check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["disposition"] == "succeeded"
    assert checked["outputs"]["applied"] is False
    assert (vault / draft).exists()

    assert main([*common, "--apply"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["disposition"] == "succeeded"
    evidence_path = Path(applied["outputs"]["technical_run_evidence"])
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["postconditions"]
    assert all(item["passed"] for item in evidence["postconditions"])
    assert evidence["versions"]["rule:CPKS-SPEC-ART"] == "0.5"
    assert evidence["authority_context"]["contract_id"] == (
        "cpks.runtime_authority@0.1"
    )
    assert not (vault / draft).exists()
    assert (vault / archive).exists()
    assert "version: '1.1'" in (vault / active).read_text(encoding="utf-8")


def test_cli_work_package_complete_uses_artifact_transition(
    tmp_path: Path, capsys
) -> None:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    active = (
        "Development/cpKnowledgeTools/Work Packages/CPKT-WP-CLI K2 Completion.md"
    )
    archive = (
        "Development/cpKnowledgeTools/Work Packages/Archive/"
        "CPKT-WP-CLI@0.1 K2 Completion.md"
    )
    contract = {
        "contract": "cpks.runtime_authority",
        "contract_version": "0.1",
        "authority": {
            "ref": "CPKT-WP-CLI",
            "version": "0.1",
            "class": "work_package",
            "issuer": "Owner",
        },
        "operations": ["artifact.transition"],
        "targets": [
            {
                "stable_id": "CPKT-WP-CLI",
                "version": "0.1",
                "artifact_class": "work_package",
                "target_kind": "cp-wiki",
            }
        ],
        "scope": {
            "document_types": ["work_package"],
            "mutation_scope": ["lifecycle_transition"],
        },
        "environment": {
            "kind": "local_vault",
            "identity": vault.resolve().as_uri(),
        },
        "effects": {
            "mutate": True,
            "activate": False,
            "remote_effects": False,
        },
        "validity": {
            "effective_from": "2026-08-27T00:00:00+00:00",
            "expires_at": "2026-09-30T00:00:00+00:00",
        },
        "approval": {
            "required": False,
            "approved_by": None,
            "approved_at": None,
            "evidence_ref": None,
        },
    }
    source_body = "# CPKT-WP-CLI – K2 Completion\n\n## Preserve\n\nScope.\n"
    completion_evidence = """

## Completion Evidence

### Actual Deliverables
K2.
### Deviations
None.
### Validations
Tests.
### Open Items
None.
### Completion Decision
Complete.
### Follow-up References
CPKT-SPEC-ARCH.
### Run/Report References
Local evidence.
"""
    base = {
        "document_type": "work_package",
        "work_package_id": "CPKT-WP-CLI",
        "title": "K2 Completion",
        "version": "0.1",
        "authority_scope": "component-wide",
        "owner": "Owner",
        "authority_basis": ["Owner Instruction"],
        "scope_summary": "K2",
        "runtime_authority_contracts": [contract],
        "created": dt.date(2026, 8, 27),
        "revised": "2026-08-28",
    }
    source = {
        **base,
        "status": "active",
        "evidence_class": "active_constraint",
        "approved_by": "Owner",
        "approved_at": "2026-08-27",
        "effective_from": "2026-08-27",
        "canonical_path": active,
    }
    _write(
        vault,
        active,
        "---\n" + yaml.safe_dump(source, sort_keys=False) + "---\n" + source_body,
    )
    _write_cli_authority(vault, contract)
    # The authority helper also writes a standalone authority fixture; in this
    # self-hosted case the target Work Package is the canonical authority source.
    (vault / "Development/Test/Work Packages/CPKT-WP-CLI Authority.md").unlink()
    _write(
        vault,
        active,
        "---\n" + yaml.safe_dump(source, sort_keys=False) + "---\n" + source_body,
    )
    evidence_file = tmp_path / "completion-evidence.md"
    evidence_file.write_text(completion_evidence, encoding="utf-8")
    contract_path = tmp_path / "runtime-authority.yaml"
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    common = [
        "work-package",
        "complete",
        "CPKT-WP-CLI",
        "--completion-evidence",
        str(evidence_file),
        "--archive-path",
        archive,
        "--vault-root",
        str(vault),
        "--run-root",
        str(runs),
        "--idempotency-key",
        "complete-cli",
        "--authority-ref",
        "CPKT-WP-CLI@0.1",
        "--authority-contract",
        str(contract_path),
        "--target-classification",
        "test",
    ]

    assert main([*common, "--check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["operation_name"] == "artifact.transition"
    assert checked["outputs"]["applied"] is False

    assert main([*common, "--apply"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["disposition"] == "succeeded"
    assert (vault / archive).exists()
    assert not (vault / active).exists()
    run_evidence = json.loads(
        Path(applied["outputs"]["technical_run_evidence"]).read_text(
            encoding="utf-8"
        )
    )
    preserve = next(
        item
        for item in run_evidence["postconditions"]
        if item["code"] == "completion_preserve"
    )
    assert preserve["actual"]["created"] == "2026-08-27"
    assert run_evidence["event_timestamps"]["started_at"].endswith("+00:00")
    assert run_evidence["event_timestamps"]["completed_at"].endswith("+00:00")


def test_cli_refreshes_rebuildable_derived_governance_state(
    tmp_path: Path, capsys
) -> None:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    active = "Systems/Example/EX-SPEC-CLI CLI Specification.md"
    _write(
        vault,
        active,
        _specification(version="1.0", status="active", canonical_path=active),
    )

    assert (
        main(
            [
                "derived",
                "governance",
                "refresh",
                "--vault-root",
                str(vault),
                "--run-root",
                str(runs),
                "--apply",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    derived = json.loads(
        Path(result["outputs"]["output_path"]).read_text(encoding="utf-8")
    )

    assert derived["non_normative"] is True
    assert derived["rule_versions"]["EX-SPEC-CLI"] == "1.0"
    assert derived["lifecycle_view"]["EX-SPEC-CLI@1.0"]["status"] == "active"
    assert "impact_view" in derived
