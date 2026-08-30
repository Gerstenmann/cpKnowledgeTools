from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.operations.application import OperationApplication
from cp_knowledge_tools.operations.contracts import (
    AuthorityDecision,
    AuthorityDisposition,
    MutationKind,
    OperationRequest,
    ResultDisposition,
)
from cp_knowledge_tools.operations.governance.managed_artifacts import (
    activate_specification,
    plan_specification_activation,
    revise_specification,
    verify_activation_postconditions,
)
from cp_knowledge_tools.operations.governance.preflight import preflight_governance
from cp_knowledge_tools.operations.governance.resolution import resolve_governance
from cp_knowledge_tools.operations.transactions.filesystem import FileTransactionEngine


def _artifact(
    *,
    stable_id: str,
    version: str,
    status: str,
    canonical_path: str,
    source_artifact: str | None = None,
    document_type: str = "specification",
    body: str = "# Example\n\nBody unchanged.\n",
) -> str:
    identity = {
        "specification": "specification_id",
        "policy": "policy_id",
        "decision_record": "decision_id",
        "process": "process_id",
        "work_package": "work_package_id",
    }[document_type]
    frontmatter = {
        "document_type": document_type,
        identity: stable_id,
        "title": "Example Specification",
        "version": version,
        "status": status,
        "evidence_class": "active_constraint"
        if status == "active"
        else "committed_target",
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
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _authority(stable_id: str = "EX-SPEC-ONE") -> AuthorityDecision:
    return AuthorityDecision(
        disposition=AuthorityDisposition.AUTHORIZED,
        authority_ref="CPKT-WP-002@0.1",
        targets=(stable_id,),
    )


def _write_reference_fixtures(vault: Path) -> None:
    fixtures = (
        (
            "Systems/Rules/CPKS-POL-GOV-AUTH Policy.md",
            "CPKS-POL-GOV-AUTH",
            "1.1",
            "policy",
        ),
        (
            "Systems/Rules/CPKS-SPEC-ART Specification.md",
            "CPKS-SPEC-ART",
            "0.5",
            "specification",
        ),
        (
            "Systems/Rules/CPKS-SPEC-OPS Specification.md",
            "CPKS-SPEC-OPS",
            "0.7",
            "specification",
        ),
        (
            "Processes/Rules/GOV-P01 Process.md",
            "GOV-P01",
            "0.4",
            "process",
        ),
        (
            "Systems/Rules/CPKS-DEC-016 Decision.md",
            "CPKS-DEC-016",
            "1.1",
            "decision_record",
        ),
        (
            "Systems/Rules/CPKS-DEC-019 Decision.md",
            "CPKS-DEC-019",
            "1.0",
            "decision_record",
        ),
        (
            "Systems/Rules/CPKS-DEC-021 Decision.md",
            "CPKS-DEC-021",
            "0.1",
            "decision_record",
        ),
        (
            "Systems/Rules/CPKS-DEC-032 Decision.md",
            "CPKS-DEC-032",
            "1.0",
            "decision_record",
        ),
    )
    for path, stable_id, version, document_type in fixtures:
        _write(
            vault,
            path,
            _artifact(
                stable_id=stable_id,
                version=version,
                status="active",
                canonical_path=path,
                document_type=document_type,
            ),
        )


def _runtime_authority(vault: Path) -> dict[str, object]:
    return {
        "contract": "cpks.runtime_authority",
        "contract_version": "0.1",
        "authority": {
            "ref": "CPKT-WP-TEST",
            "version": "0.1",
            "class": "work_package",
            "issuer": "Owner",
        },
        "operations": ["artifact.activate"],
        "targets": [
            {
                "stable_id": "EX-SPEC-ONE",
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


def _write_runtime_authority(vault: Path, contract: dict[str, object]) -> None:
    path = "Development/Test/Work Packages/CPKT-WP-TEST Test Authority.md"
    frontmatter = {
        "document_type": "work_package",
        "work_package_id": "CPKT-WP-TEST",
        "title": "Test Authority",
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


def _event_clock() -> object:
    current = -1

    def tick() -> str:
        nonlocal current
        current += 1
        return (
            dt.datetime(2026, 8, 28, tzinfo=dt.UTC) + dt.timedelta(microseconds=current)
        ).isoformat()

    return tick


def _activation_application_case(
    tmp_path: Path,
    *,
    contract_identity: str | None = None,
    target_classification: str = "test",
) -> tuple[Path, Path, dict[str, object], OperationRequest, str, str, str]:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    draft = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-ONE@1.0 Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    _write(
        vault,
        draft,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=draft,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
    )
    _write_reference_fixtures(vault)
    contract = _runtime_authority(vault)
    if contract_identity is not None:
        contract["environment"]["identity"] = contract_identity  # type: ignore[index]
    _write_runtime_authority(vault, contract)
    parameters: dict[str, object] = {
        "vault_root": str(vault),
        "run_root": str(runs),
        "stable_id": "EX-SPEC-ONE",
        "draft_path": draft,
        "archive_path": archive,
        "approved_by": "Owner",
        "approved_at": "2026-08-27",
        "effective_from": "2026-08-28",
        "runtime_authority": contract,
        "target_classification": target_classification,
    }
    request = OperationRequest(
        operation_name="artifact.activate",
        operation_version="0.1",
        targets=("EX-SPEC-ONE",),
        requested_mode="apply",
        authority_ref="CPKT-WP-TEST@0.1",
        idempotency_key="activation-key",
        parameters=parameters,
    )
    return vault, runs, parameters, request, active, draft, archive


def test_governance_resolve_reuses_active_resolver(tmp_path: Path) -> None:
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    _write(
        tmp_path,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )

    result = resolve_governance(Vault(tmp_path), "EX-SPEC-ONE")

    assert result["stable_id"] == "EX-SPEC-ONE"
    assert result["version"] == "1.0"
    assert result["integrity_ok"] is True
    assert result["current_state_fingerprint"]


def test_preflight_blocks_missing_authority_and_reports_impact(tmp_path: Path) -> None:
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    consumer = "Systems/Example/EX-SPEC-TWO Example Specification.md"
    _write(
        tmp_path,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    consumer_text = _artifact(
        stable_id="EX-SPEC-TWO", version="1.0", status="active", canonical_path=consumer
    )
    consumer_text = consumer_text.replace(
        "governed_by:\n- CPKS-POL-GOV-AUTH", "governed_by:\n- EX-SPEC-ONE"
    )
    _write(tmp_path, consumer, consumer_text)

    report = preflight_governance(
        vault_root=tmp_path,
        stable_id="EX-SPEC-ONE",
        target_version="1.1",
        authority=AuthorityDecision.evaluate(None, (), ("EX-SPEC-ONE",)),
    )

    assert report.disposition is ResultDisposition.BLOCKED
    assert report.impact_candidates["EX-SPEC-TWO"] == "review_required"


def test_revise_requires_full_prepared_specification_and_check_before_apply(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    target = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    prepared = tmp_path / "prepared.md"
    prepared.write_text(
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=target,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
        encoding="utf-8",
    )
    engine = FileTransactionEngine(vault, tmp_path / "runs")

    preview = revise_specification(
        vault_root=vault,
        prepared_file=prepared,
        target_path=target,
        authority=_authority(),
        apply=False,
        transaction_engine=engine,
        idempotency_key="revise",
    )
    assert preview.disposition is ResultDisposition.SUCCEEDED
    assert not (vault / target).exists()

    applied = revise_specification(
        vault_root=vault,
        prepared_file=prepared,
        target_path=target,
        authority=_authority(),
        apply=True,
        transaction_engine=engine,
        idempotency_key="revise",
    )

    assert applied.disposition is ResultDisposition.SUCCEEDED
    assert (vault / target).exists()
    assert (vault / active).read_text(encoding="utf-8").endswith("Body unchanged.\n")


def test_revise_rejects_other_artifact_class(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    prepared = tmp_path / "policy.md"
    prepared.write_text(
        _artifact(
            stable_id="EX-POL-ONE",
            version="1.1",
            status="draft",
            canonical_path="Development/Example/EX-POL-ONE@1.1 Example.md",
            document_type="policy",
        ),
        encoding="utf-8",
    )

    result = revise_specification(
        vault_root=vault,
        prepared_file=prepared,
        target_path="Development/Example/EX-POL-ONE@1.1 Example.md",
        authority=_authority("EX-POL-ONE"),
        apply=False,
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
        idempotency_key="policy",
    )
    assert result.disposition is ResultDisposition.UNSUPPORTED


def test_revise_blocks_missing_body_wrong_source_and_non_higher_version(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    target = "Development/Example/EX-SPEC-ONE@1.0 Example Specification.md"
    incomplete = tmp_path / "incomplete.md"
    incomplete.write_text("---\nspecification_id: EX-SPEC-ONE\n---\n", encoding="utf-8")
    bad = revise_specification(
        vault_root=vault,
        prepared_file=incomplete,
        target_path=target,
        authority=_authority(),
        apply=False,
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs-one"),
        idempotency_key="incomplete",
    )
    assert bad.disposition is ResultDisposition.UNSUPPORTED

    wrong_source = tmp_path / "wrong-source.md"
    revision_path = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    wrong_source.write_text(
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=revision_path,
            source_artifact="EX-SPEC-ONE@0.9",
        ),
        encoding="utf-8",
    )
    source_result = revise_specification(
        vault_root=vault,
        prepared_file=wrong_source,
        target_path=revision_path,
        authority=_authority(),
        apply=False,
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs-two"),
        idempotency_key="wrong-source",
    )
    assert source_result.disposition is ResultDisposition.BLOCKED

    same_version = tmp_path / "same-version.md"
    same_version.write_text(
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="draft",
            canonical_path=target,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
        encoding="utf-8",
    )
    version_result = revise_specification(
        vault_root=vault,
        prepared_file=same_version,
        target_path=target,
        authority=_authority(),
        apply=False,
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs-three"),
        idempotency_key="same-version",
    )
    assert version_result.disposition is ResultDisposition.CONFLICT


def test_activation_preserves_body_and_versioned_evidence(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    draft = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-ONE@1.0 Example Specification.md"
    predecessor_text = _artifact(
        stable_id="EX-SPEC-ONE", version="1.0", status="active", canonical_path=active
    )
    target_text = _artifact(
        stable_id="EX-SPEC-ONE",
        version="1.1",
        status="draft",
        canonical_path=draft,
        source_artifact="EX-SPEC-ONE@1.0",
        body="# Example\n\nNew owner-prepared body.\n",
    )
    _write(vault, active, predecessor_text)
    _write(vault, draft, target_text)
    _write_reference_fixtures(vault)
    engine = FileTransactionEngine(vault, tmp_path / "runs")

    plan = plan_specification_activation(
        vault_root=vault,
        stable_id="EX-SPEC-ONE",
        draft_path=draft,
        archive_path=archive,
        approved_by="Owner",
        approved_at="2026-08-27",
        effective_from="2026-08-28",
        authority=_authority(),
        transaction_engine=engine,
    )
    assert [action.kind for action in plan.mutation_plan.actions] == [
        MutationKind.REPLACE,
        MutationKind.MOVE,
        MutationKind.REPLACE,
        MutationKind.MOVE,
    ]

    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="activate",
    )
    active_text = (vault / active).read_text(encoding="utf-8")
    archived_text = (vault / archive).read_text(encoding="utf-8")

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert active_text.split("---\n", 2)[2] == target_text.split("---\n", 2)[2]
    assert archived_text.split("---\n", 2)[2] == predecessor_text.split("---\n", 2)[2]
    assert "CPKS-SPEC-ART@0.5" in active_text
    assert "CPKS-DEC-032@1.0" in active_text
    assert "source_artifact: EX-SPEC-ONE@1.0" in active_text


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ("canonical_path", "target_canonical_path"),
        ("body", "target_activation_body_matches"),
        ("validated_against", "target_evidence_preserved"),
        ("duplicate_version", "unique_id_version"),
        ("missing_predecessor", "activation_reread_failed"),
    ],
)
def test_activation_postcondition_report_diagnoses_reread_state(
    tmp_path: Path,
    tamper: str,
    expected_code: str,
) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    draft = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-ONE@1.0 Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    _write(
        vault,
        draft,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=draft,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
    )
    _write_reference_fixtures(vault)
    engine = FileTransactionEngine(vault, tmp_path / "runs")
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id="EX-SPEC-ONE",
        draft_path=draft,
        archive_path=archive,
        approved_by="Owner",
        approved_at="2026-08-27",
        effective_from="2026-08-28",
        authority=_authority(),
        transaction_engine=engine,
    )
    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="postconditions",
    )
    assert result.disposition is ResultDisposition.SUCCEEDED

    active_path = vault / active
    archive_path = vault / archive
    if tamper == "canonical_path":
        active_path.write_text(
            active_path.read_text(encoding="utf-8").replace(
                f"canonical_path: {active}", "canonical_path: Systems/Wrong.md"
            ),
            encoding="utf-8",
        )
    elif tamper == "body":
        active_path.write_text(
            active_path.read_text(encoding="utf-8") + "tampered\n",
            encoding="utf-8",
        )
    elif tamper == "validated_against":
        active_path.write_text(
            active_path.read_text(encoding="utf-8").replace(
                "CPKS-SPEC-ART@0.5", "CPKS-SPEC-ART@9.9"
            ),
            encoding="utf-8",
        )
    elif tamper == "duplicate_version":
        _write(
            vault,
            "Systems/Example/Archive/Duplicate.md",
            archive_path.read_text(encoding="utf-8").replace(
                f"canonical_path: {archive}",
                "canonical_path: Systems/Example/Archive/Duplicate.md",
            ),
        )
    else:
        archive_path.unlink()

    report = verify_activation_postconditions(plan, vault)

    assert report.passed is False
    assert any(
        item["code"] == expected_code and item["passed"] is False
        for item in report.results
    )


def test_initial_activation_and_two_active_versions_are_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    draft = "Development/Example/EX-SPEC-ONE@1.0 Example Specification.md"
    _write(
        vault,
        draft,
        _artifact(
            stable_id="EX-SPEC-ONE", version="1.0", status="draft", canonical_path=draft
        ),
    )

    no_predecessor = plan_specification_activation(
        vault_root=vault,
        stable_id="EX-SPEC-ONE",
        draft_path=draft,
        archive_path="Systems/Example/Archive/EX-SPEC-ONE@0.9 Example.md",
        approved_by="Owner",
        approved_at="2026-08-27",
        effective_from="2026-08-27",
        authority=_authority(),
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
    )
    assert no_predecessor.disposition is ResultDisposition.BLOCKED

    active_one = "Systems/One/EX-SPEC-TWO Example Specification.md"
    active_two = "Systems/Two/EX-SPEC-TWO Example Specification.md"
    draft_two = "Development/Example/EX-SPEC-TWO@1.2 Example Specification.md"
    _write(
        vault,
        active_one,
        _artifact(
            stable_id="EX-SPEC-TWO",
            version="1.0",
            status="active",
            canonical_path=active_one,
        ),
    )
    _write(
        vault,
        active_two,
        _artifact(
            stable_id="EX-SPEC-TWO",
            version="1.1",
            status="active",
            canonical_path=active_two,
        ),
    )
    _write(
        vault,
        draft_two,
        _artifact(
            stable_id="EX-SPEC-TWO",
            version="1.2",
            status="draft",
            canonical_path=draft_two,
            source_artifact="EX-SPEC-TWO@1.1",
        ),
    )
    conflict = plan_specification_activation(
        vault_root=vault,
        stable_id="EX-SPEC-TWO",
        draft_path=draft_two,
        archive_path="Systems/Example/Archive/EX-SPEC-TWO@1.1 Example.md",
        approved_by="Owner",
        approved_at="2026-08-27",
        effective_from="2026-08-27",
        authority=_authority("EX-SPEC-TWO"),
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
    )
    assert conflict.disposition is ResultDisposition.CONFLICT


def test_application_activation_replay_and_key_conflict_are_detected_before_reread(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    draft = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-ONE@1.0 Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    _write(
        vault,
        draft,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=draft,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
    )
    _write_reference_fixtures(vault)
    contract = _runtime_authority(vault)
    _write_runtime_authority(vault, contract)
    parameters = {
        "vault_root": str(vault),
        "run_root": str(runs),
        "stable_id": "EX-SPEC-ONE",
        "draft_path": draft,
        "archive_path": archive,
        "approved_by": "Owner",
        "approved_at": "2026-08-27",
        "effective_from": "2026-08-28",
        "runtime_authority": contract,
        "target_classification": "test",
    }
    request = OperationRequest(
        operation_name="artifact.activate",
        operation_version="0.1",
        targets=("EX-SPEC-ONE",),
        requested_mode="apply",
        authority_ref="CPKT-WP-TEST@0.1",
        idempotency_key="activation-key",
        parameters=parameters,
    )
    application = OperationApplication(event_clock=_event_clock())

    first = application.execute(request, **parameters)
    replay = application.execute(request, **parameters)
    conflicting_parameters = {**parameters, "effective_from": "2026-08-29"}
    conflict_request = OperationRequest(
        operation_name="artifact.activate",
        operation_version="0.1",
        targets=("EX-SPEC-ONE",),
        requested_mode="apply",
        authority_ref="CPKT-WP-TEST@0.1",
        idempotency_key="activation-key",
        parameters=conflicting_parameters,
    )
    conflict = application.execute(conflict_request, **conflicting_parameters)

    assert first.disposition is ResultDisposition.SUCCEEDED
    assert replay.disposition is ResultDisposition.IDEMPOTENT_REPLAY
    assert conflict.disposition is ResultDisposition.CONFLICT
    assert Path(first.outputs["technical_run_evidence"]).exists()
    assert first.outputs["run_state_history"] == [
        "REQUESTED",
        "CONTEXT_RESOLVED",
        "PREFLIGHT_PASSED",
        "PLANNED",
        "PREVIEWED",
        "AWAITING_AUTHORITY",
        "AUTHORIZED",
        "STAGING",
        "APPLYING",
        "VERIFYING",
        "SUCCEEDED",
    ]
    context = first.outputs["operation_context"]
    assert context["active_rule_homes"]["CPKS-SPEC-OPS"] == "0.7"
    assert context["runtime_authority"]["contract"] == "cpks.runtime_authority"
    assert context["target_environment"]["identity"] == vault.resolve().as_uri()
    evidence = json.loads(
        Path(first.outputs["technical_run_evidence"]).read_text(encoding="utf-8")
    )
    assert evidence["authority_context"]["disposition"] == "authorized"
    assert (
        evidence["event_timestamps"]["completed_at"]
        > evidence["event_timestamps"]["started_at"]
    )
    replay_evidence = json.loads(
        Path(replay.outputs["technical_run_evidence"]).read_text(encoding="utf-8")
    )
    assert (
        replay_evidence["event_timestamps"]["started_at"]
        > evidence["event_timestamps"]["completed_at"]
    )


def test_application_blocks_explicit_live_target_without_runtime_authority(
    tmp_path: Path,
) -> None:
    vault, _, parameters, request, _, draft, _ = _activation_application_case(
        tmp_path,
        target_classification="live",
    )
    (vault / "Development/Test/Work Packages/CPKT-WP-TEST Test Authority.md").unlink()

    result = OperationApplication().execute(request, **parameters)

    assert result.disposition is ResultDisposition.BLOCKED
    assert result.actual_mutations == ()
    assert (vault / draft).exists()


def test_application_does_not_create_missing_mutation_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing-vault"
    request = OperationRequest(
        operation_name="artifact.activate",
        operation_version="0.1",
        targets=("EX-SPEC-ONE",),
        requested_mode="apply",
        authority_ref="CPKT-WP-TEST@0.1",
        parameters={
            "vault_root": str(missing),
            "run_root": str(tmp_path / "runs"),
            "draft_path": "Development/Example/Draft.md",
            "target_classification": "test",
        },
    )

    result = OperationApplication().execute(request, **request.parameters)

    assert result.disposition is ResultDisposition.BLOCKED
    assert not missing.exists()


def test_caller_forged_authority_scope_and_target_cannot_authorize(
    tmp_path: Path,
) -> None:
    vault, _, parameters, request, active, _, _ = _activation_application_case(tmp_path)
    authority_path = (
        vault / "Development/Test/Work Packages/CPKT-WP-TEST Test Authority.md"
    )
    authority_path.unlink()
    forged = {
        **parameters,
        "authority_scope": ["EX-SPEC-ONE"],
        "authority_target": "EX-SPEC-ONE",
    }

    result = OperationApplication().execute(request, **forged)

    assert result.disposition is ResultDisposition.BLOCKED
    assert result.actual_mutations == ()
    assert (vault / active).exists()
    assert result.outputs["run_state_history"][-2:] == [
        "AWAITING_AUTHORITY",
        "BLOCKED",
    ]


def test_environment_identity_mismatch_blocks_without_mutation(tmp_path: Path) -> None:
    vault, _, parameters, request, active, draft, _ = _activation_application_case(
        tmp_path,
        contract_identity="file:///different-vault",
    )

    result = OperationApplication().execute(request, **parameters)

    assert result.disposition is ResultDisposition.BLOCKED
    assert result.actual_mutations == ()
    assert (vault / active).exists()
    assert (vault / draft).exists()


def test_application_reports_conflicting_active_line_before_mutation(
    tmp_path: Path,
) -> None:
    vault, _, parameters, request, _, draft, _ = _activation_application_case(tmp_path)
    second = "Systems/Other/EX-SPEC-ONE Example Specification.md"
    _write(
        vault,
        second,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="0.9",
            status="active",
            canonical_path=second,
        ),
    )

    result = OperationApplication().execute(request, **parameters)

    assert result.disposition is ResultDisposition.CONFLICT
    assert result.actual_mutations == ()
    assert (vault / draft).exists()


def test_explicit_live_classification_is_path_independent_for_valid_check(
    tmp_path: Path,
) -> None:
    _, _, parameters, request, _, draft, _ = _activation_application_case(
        tmp_path,
        target_classification="live",
    )
    check_request = OperationRequest(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        targets=request.targets,
        requested_mode="check",
        authority_ref=request.authority_ref,
        idempotency_key="live-check",
        parameters=parameters,
    )

    result = OperationApplication().execute(check_request, **parameters)

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert (
        result.outputs["operation_context"]["target_environment"]["classification"]
        == "live"
    )
    assert Path(str(parameters["vault_root"]), draft).exists()


def test_application_domain_failure_compensates_and_evidence_agrees(
    tmp_path: Path,
) -> None:
    vault, _, parameters, request, active, draft, archive = (
        _activation_application_case(tmp_path)
    )
    (vault / "Systems/Rules/CPKS-DEC-032 Decision.md").unlink()

    result = OperationApplication(event_clock=_event_clock()).execute(
        request, **parameters
    )

    assert result.disposition is ResultDisposition.COMPENSATED_FAILURE
    assert result.compensation_status == "compensated"
    assert result.recovery_record is None
    assert (vault / active).exists()
    assert (vault / draft).exists()
    assert not (vault / archive).exists()
    assert result.outputs["run_state_history"][-3:] == [
        "PARTIAL_STATE_DETECTED",
        "COMPENSATING",
        "COMPENSATED_FAILURE",
    ]
    evidence = json.loads(
        Path(result.outputs["technical_run_evidence"]).read_text(encoding="utf-8")
    )
    assert evidence["disposition"] == "compensated_failure"
    assert evidence["compensation_status"] == "compensated"
    assert evidence["recovery_status"] == "none"


def test_application_domain_failure_with_failed_compensation_requires_recovery(
    tmp_path: Path,
) -> None:
    vault, runs, parameters, request, _, _, _ = _activation_application_case(tmp_path)
    (vault / "Systems/Rules/CPKS-DEC-032 Decision.md").unlink()
    application = OperationApplication(
        transaction_engine_factory=lambda root, run_root: FileTransactionEngine(
            root, run_root, fail_compensation=True
        ),
        event_clock=_event_clock(),
    )

    result = application.execute(request, **parameters)

    assert result.disposition is ResultDisposition.RECOVERY_REQUIRED
    assert result.recovery_record is not None
    assert result.outputs["run_state_history"][-4:] == [
        "PARTIAL_STATE_DETECTED",
        "COMPENSATING",
        "FATAL_PARTIAL_STATE",
        "RECOVERY_REQUIRED",
    ]
    assert (runs / "recovery" / f"{result.recovery_record.recovery_id}.json").exists()
    evidence = json.loads(
        Path(result.outputs["technical_run_evidence"]).read_text(encoding="utf-8")
    )
    assert evidence["disposition"] == "recovery_required"
    assert evidence["recovery_status"] == "recovery_required"
    assert evidence["outputs"]["recovery_record"]["recovery_id"] == (
        result.recovery_record.recovery_id
    )


def test_evidence_persistence_failure_preserves_successful_mutation_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault, _, parameters, request, active, draft, archive = (
        _activation_application_case(tmp_path)
    )

    def fail_write(*_args, **_kwargs):
        raise OSError("injected evidence persistence failure")

    monkeypatch.setattr(
        "cp_knowledge_tools.operations.application."
        "TechnicalRunEvidenceWriter.write",
        fail_write,
    )

    result = OperationApplication(event_clock=_event_clock()).execute(
        request,
        **parameters,
    )

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert result.actual_mutations
    assert result.outputs["technical_run_evidence"] is None
    assert result.outputs["technical_run_evidence_status"] == (
        "persistence_failed_after_operation"
    )
    assert result.outputs["operation_result_preserved"] is True
    assert result.outputs["retry_operation_required"] is False
    assert (vault / active).exists()
    assert not (vault / draft).exists()
    assert (vault / archive).exists()


def test_application_revise_uses_shared_context_and_controller(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    target = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    _write_reference_fixtures(vault)
    prepared = tmp_path / "prepared.md"
    prepared.write_text(
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=target,
            source_artifact="EX-SPEC-ONE@1.0",
        ),
        encoding="utf-8",
    )
    contract = _runtime_authority(vault)
    contract["operations"] = ["artifact.revise"]
    contract["scope"]["mutation_scope"] = ["lifecycle_transition"]  # type: ignore[index]
    contract["effects"]["activate"] = False  # type: ignore[index]
    _write_runtime_authority(vault, contract)
    parameters = {
        "vault_root": str(vault),
        "run_root": str(tmp_path / "runs"),
        "stable_id": "EX-SPEC-ONE",
        "prepared_file": str(prepared),
        "target_path": target,
        "runtime_authority": contract,
        "target_classification": "test",
    }
    request = OperationRequest(
        operation_name="artifact.revise",
        operation_version="0.1",
        targets=("EX-SPEC-ONE",),
        requested_mode="apply",
        authority_ref="CPKT-WP-TEST@0.1",
        idempotency_key="revise-application",
        parameters=parameters,
    )

    result = OperationApplication(event_clock=_event_clock()).execute(
        request, **parameters
    )

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert (vault / target).exists()
    assert result.outputs["run_state_history"][-4:] == [
        "STAGING",
        "APPLYING",
        "VERIFYING",
        "SUCCEEDED",
    ]
    assert result.outputs["operation_context"]["mutation_class"] == (
        "lifecycle_transition"
    )



def test_activation_uses_owner_prepared_activation_target_body(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    active = "Systems/Example/EX-SPEC-ONE Example Specification.md"
    draft = "Development/Example/EX-SPEC-ONE@1.1 Example Specification.md"
    archive = "Systems/Example/Archive/EX-SPEC-ONE@1.0 Example Specification.md"
    target_file = tmp_path / "activation-target.md"
    _write(
        vault,
        active,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.0",
            status="active",
            canonical_path=active,
        ),
    )
    _write(
        vault,
        draft,
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="draft",
            canonical_path=draft,
            source_artifact="EX-SPEC-ONE@1.0",
            body="# Example\n\nNicht verbindlicher Draft.\n",
        ),
    )
    target_file.write_text(
        _artifact(
            stable_id="EX-SPEC-ONE",
            version="1.1",
            status="active",
            canonical_path=active,
            source_artifact="EX-SPEC-ONE@1.0",
            body="# Example\n\nAktiv und verbindlich.\n",
        ),
        encoding="utf-8",
    )
    _write_reference_fixtures(vault)
    engine = FileTransactionEngine(vault, tmp_path / "runs")
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id="EX-SPEC-ONE",
        draft_path=draft,
        archive_path=archive,
        activation_target_file=target_file,
        approved_by="Owner",
        approved_at="2026-08-30",
        effective_from="2026-08-30",
        authority=_authority(),
        transaction_engine=engine,
    )
    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="activation-target-body",
    )
    assert result.disposition is ResultDisposition.SUCCEEDED
    active_text = (vault / active).read_text(encoding="utf-8")
    assert "Aktiv und verbindlich." in active_text
    assert "Nicht verbindlicher Draft." not in active_text
