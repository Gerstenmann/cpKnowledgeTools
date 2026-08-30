from __future__ import annotations

import datetime as dt
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.operations.contracts import (
    AuthorityClass,
    AuthorityDisposition,
    EnvironmentKind,
    RuntimeAuthorityApproval,
    RuntimeAuthorityContract,
    RuntimeAuthorityEffects,
    RuntimeAuthorityTarget,
    RuntimeAuthorityValidity,
    TargetKind,
)
from cp_knowledge_tools.operations.governance.authority import (
    AuthorityRequirement,
    AuthoritySourceError,
    AuthoritySourceRecord,
    CanonicalManagedAuthoritySource,
    RuntimeAuthorityResolver,
)
from cp_knowledge_tools.validation.temporal import parse_lifecycle_temporal


def authority_mapping(
    *,
    operation: str = "artifact.activate",
    target: str = "EX-SPEC-ONE",
    target_version: str = "1.1",
    document_type: str = "specification",
    mutation_scope: str = "lifecycle_activation",
    target_kind: str = "cp-wiki",
    environment_kind: str = "local_vault",
    environment_identity: str = "file:///vault",
    mutate: bool = True,
    activate: bool = True,
    remote_effects: bool = False,
    effective_from: str = "2026-08-01T00:00:00+00:00",
    expires_at: str | None = "2026-09-01T00:00:00+00:00",
    authority_class: str = "work_package",
    approved_by: str | None = None,
    approval_required: bool = False,
    evidence_ref: str | None = None,
) -> dict[str, object]:
    return {
        "contract": "cpks.runtime_authority",
        "contract_version": "0.1",
        "authority": {
            "ref": "CPKT-WP-TEST",
            "version": "0.1",
            "class": authority_class,
            "issuer": "Owner",
        },
        "operations": [operation],
        "targets": [
            {
                "stable_id": target,
                "version": target_version,
                "artifact_class": document_type,
                "target_kind": target_kind,
            }
        ],
        "scope": {
            "document_types": [document_type],
            "mutation_scope": [mutation_scope],
        },
        "environment": {
            "kind": environment_kind,
            "identity": environment_identity,
        },
        "effects": {
            "mutate": mutate,
            "activate": activate,
            "remote_effects": remote_effects,
        },
        "validity": {
            "effective_from": effective_from,
            "expires_at": expires_at,
        },
        "approval": {
            "required": approval_required,
            "approved_by": approved_by,
            "approved_at": ("2026-08-20T10:00:00+00:00" if approved_by else None),
            "evidence_ref": evidence_ref,
        },
    }


def requirement(**changes: object) -> AuthorityRequirement:
    values: dict[str, object] = {
        "operation_id": "artifact.activate",
        "target_stable_id": "EX-SPEC-ONE",
        "target_version": "1.1",
        "artifact_class": "specification",
        "target_kind": TargetKind.CP_WIKI,
        "document_type": "specification",
        "mutation_scope": ("lifecycle_activation",),
        "environment_kind": EnvironmentKind.LOCAL_VAULT,
        "environment_identity": "file:///vault",
        "activate": True,
    }
    values.update(changes)
    return AuthorityRequirement(**values)


class StaticSource:
    def __init__(
        self,
        grant: RuntimeAuthorityContract,
        *,
        approval_verified: bool = False,
    ) -> None:
        effective = parse_lifecycle_temporal("2026-08-01")
        assert effective is not None
        self.record = AuthoritySourceRecord(
            authority_ref="CPKT-WP-TEST",
            version="0.1",
            authority_class=grant.authority.authority_class,
            issuer="Owner",
            source_path="Development/Test/Work Packages/CPKT-WP-TEST.md",
            source_fingerprint="source-fingerprint",
            effective_from=effective,
            grants=(grant,),
            approval_verified=approval_verified,
        )

    def resolve(self, authority_ref: str) -> AuthoritySourceRecord:
        if authority_ref not in {"CPKT-WP-TEST", "CPKT-WP-TEST@0.1"}:
            raise AuthoritySourceError("authority_not_found", "authority not found")
        return self.record


def resolver(
    grant: RuntimeAuthorityContract,
    *,
    approval_verified: bool = False,
) -> RuntimeAuthorityResolver:
    return RuntimeAuthorityResolver(
        StaticSource(grant, approval_verified=approval_verified),
        known_operations=("artifact.activate", "artifact.revise"),
        clock=lambda: dt.datetime(2026, 8, 28, tzinfo=dt.UTC),
    )


def test_runtime_authority_contract_roundtrip_and_immutability() -> None:
    contract = RuntimeAuthorityContract.from_mapping(authority_mapping())

    assert RuntimeAuthorityContract.from_mapping(contract.as_mapping()) == contract
    assert contract.contract_id == "cpks.runtime_authority@0.1"
    assert contract.fingerprint
    with pytest.raises(FrozenInstanceError):
        contract.operations = ("artifact.revise",)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "9.9"),
        ("operations", ["*"]),
        (
            "targets",
            [
                {
                    "stable_id": "all",
                    "version": "1.1",
                    "artifact_class": "specification",
                    "target_kind": "cp-wiki",
                }
            ],
        ),
    ],
)
def test_invalid_contract_shapes_are_rejected(field: str, value: object) -> None:
    payload = authority_mapping()
    payload[field] = value
    with pytest.raises(ValueError):
        RuntimeAuthorityContract.from_mapping(payload)


@pytest.mark.parametrize(
    "requirement_change",
    [
        {"operation_id": "artifact.revise"},
        {"target_stable_id": "EX-SPEC-TWO"},
        {"target_version": "1.2"},
        {"artifact_class": "policy"},
        {"document_type": "policy"},
        {"mutation_scope": ("metadata_update",)},
        {"target_kind": TargetKind.REPOSITORY},
        {"environment_kind": EnvironmentKind.LOCAL_REPOSITORY},
        {"environment_identity": "file:///other"},
        {"remote_effects": True},
    ],
)
def test_exact_contract_mismatch_blocks(requirement_change: dict[str, object]) -> None:
    grant = RuntimeAuthorityContract.from_mapping(authority_mapping())
    decision = resolver(grant).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=grant.as_mapping(),
        requirement=requirement(**requirement_change),
    )
    assert decision.disposition is AuthorityDisposition.BLOCKED


@pytest.mark.parametrize(
    "contract_change",
    [
        {"effects": RuntimeAuthorityEffects(False, True, False)},
        {"effects": RuntimeAuthorityEffects(True, False, False)},
        {
            "validity": RuntimeAuthorityValidity(
                "2026-08-29T00:00:00+00:00", "2026-09-01T00:00:00+00:00"
            )
        },
        {
            "validity": RuntimeAuthorityValidity(
                "2026-08-01T00:00:00+00:00", "2026-08-27T00:00:00+00:00"
            )
        },
    ],
)
def test_effect_and_validity_fail_closed(contract_change: dict[str, object]) -> None:
    contract = RuntimeAuthorityContract.from_mapping(authority_mapping())
    contract = replace(contract, **contract_change)
    decision = resolver(contract).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=contract.as_mapping(),
        requirement=requirement(),
    )
    assert decision.disposition is AuthorityDisposition.BLOCKED


def test_caller_contract_cannot_expand_canonical_authority() -> None:
    grant = RuntimeAuthorityContract.from_mapping(authority_mapping())
    forged = replace(
        grant,
        targets=(
            RuntimeAuthorityTarget(
                "EX-SPEC-TWO", "1.1", "specification", TargetKind.CP_WIKI
            ),
        ),
    )
    decision = resolver(grant).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=forged.as_mapping(),
        requirement=requirement(target_stable_id="EX-SPEC-TWO"),
    )
    assert decision.disposition is AuthorityDisposition.BLOCKED
    assert "uniquely covered" in decision.reasons[0]


def test_required_approval_and_forged_approved_by_fail_closed() -> None:
    grant = RuntimeAuthorityContract.from_mapping(
        authority_mapping(
            approval_required=True,
            approved_by="Owner",
            evidence_ref="CPKT-WP-TEST@0.1",
        )
    )
    unverified = resolver(grant).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=grant.as_mapping(),
        requirement=requirement(),
    )
    forged = replace(
        grant,
        approval=RuntimeAuthorityApproval(
            True,
            "Caller",
            "2026-08-20T10:00:00+00:00",
            "CPKT-WP-TEST@0.1",
        ),
    )
    forged_decision = resolver(grant, approval_verified=True).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=forged.as_mapping(),
        requirement=requirement(),
    )
    verified = resolver(grant, approval_verified=True).resolve(
        authority_ref="CPKT-WP-TEST@0.1",
        contract_value=grant.as_mapping(),
        requirement=requirement(),
    )

    assert unverified.disposition is AuthorityDisposition.BLOCKED
    assert forged_decision.disposition is AuthorityDisposition.BLOCKED
    assert verified.disposition is AuthorityDisposition.AUTHORIZED


def _managed_authority(
    path: str,
    *,
    document_type: str,
    identity_field: str,
    status: str,
    runtime_authority: dict[str, object] | None,
) -> str:
    frontmatter: dict[str, object] = {
        "document_type": document_type,
        identity_field: "CPKT-WP-TEST",
        "title": "Test Authority",
        "version": "0.1",
        "status": status,
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-01",
        "effective_from": "2026-08-01",
        "canonical_path": path,
    }
    if runtime_authority is not None:
        frontmatter["runtime_authority"] = runtime_authority
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nBody\n"


def test_canonical_source_distinguishes_unknown_inactive_and_non_authoritative(
    tmp_path: Path,
) -> None:
    inactive_path = "Development/Test/Work Packages/CPKT-WP-TEST@0.1 Test.md"
    target = tmp_path / inactive_path
    target.parent.mkdir(parents=True)
    target.write_text(
        _managed_authority(
            inactive_path,
            document_type="work_package",
            identity_field="work_package_id",
            status="superseded",
            runtime_authority=authority_mapping(),
        ),
        encoding="utf-8",
    )
    source = CanonicalManagedAuthoritySource(tmp_path)

    with pytest.raises(AuthoritySourceError, match="No active") as inactive:
        source.resolve("CPKT-WP-TEST@0.1")
    with pytest.raises(AuthoritySourceError) as unknown:
        source.resolve("CPKT-WP-MISSING@0.1")

    assert inactive.value.code == "authority_not_active"
    assert unknown.value.code == "authority_not_found"


def test_active_policy_cannot_authorize_mutation(tmp_path: Path) -> None:
    path = "Systems/Test/CPKT-WP-TEST Test Authority.md"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(
        _managed_authority(
            path,
            document_type="policy",
            identity_field="policy_id",
            status="active",
            runtime_authority=authority_mapping(),
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuthoritySourceError) as error:
        CanonicalManagedAuthoritySource(tmp_path).resolve("CPKT-WP-TEST@0.1")

    assert error.value.code == "authority_class_not_permitted"


def test_owner_approval_without_trusted_evidence_source_is_blocked() -> None:
    payload = authority_mapping(authority_class="owner_approval")
    payload["authority"]["ref"] = "OWNER-APPROVAL-001"  # type: ignore[index]
    grant = RuntimeAuthorityContract.from_mapping(payload)
    decision = RuntimeAuthorityResolver(
        StaticSource(grant),
        known_operations=("artifact.activate",),
        clock=lambda: dt.datetime(2026, 8, 28, tzinfo=dt.UTC),
    ).resolve(
        authority_ref="OWNER-APPROVAL-001@0.1",
        contract_value=payload,
        requirement=requirement(),
    )

    assert decision.disposition is AuthorityDisposition.BLOCKED
    assert decision.checks[-1]["code"] == "owner_approval_unverifiable"


def test_canonical_decision_record_with_exact_structured_scope_resolves(
    tmp_path: Path,
) -> None:
    path = "Systems/Test/Decisions/CPKS-DEC-TEST Test Authority.md"
    payload = authority_mapping(authority_class="decision_record")
    payload["authority"]["ref"] = "CPKS-DEC-TEST"  # type: ignore[index]
    frontmatter = {
        "document_type": "decision_record",
        "decision_id": "CPKS-DEC-TEST",
        "title": "Test Authority",
        "version": "0.1",
        "status": "active",
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-01",
        "effective_from": "2026-08-01",
        "canonical_path": path,
        "runtime_authority": payload,
    }
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nDecision.\n",
        encoding="utf-8",
    )

    record = CanonicalManagedAuthoritySource(tmp_path).resolve("CPKS-DEC-TEST@0.1")

    assert record.authority_class is AuthorityClass.DECISION_RECORD
    assert record.grants[0].operations == ("artifact.activate",)


def test_process_without_explicit_structured_delegation_is_blocked(
    tmp_path: Path,
) -> None:
    path = "Processes/Test/CPKT-WP-TEST Process.md"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(
        _managed_authority(
            path,
            document_type="process",
            identity_field="process_id",
            status="active",
            runtime_authority=None,
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuthoritySourceError) as error:
        CanonicalManagedAuthoritySource(tmp_path).resolve("CPKT-WP-TEST@0.1")

    assert error.value.code == "authority_scope_unavailable"


def test_canonical_authority_integrity_failure_is_distinct(tmp_path: Path) -> None:
    path = "Development/Test/Work Packages/CPKT-WP-TEST Test.md"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(
        _managed_authority(
            "Development/Test/Work Packages/Wrong.md",
            document_type="work_package",
            identity_field="work_package_id",
            status="active",
            runtime_authority=authority_mapping(),
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuthoritySourceError) as error:
        CanonicalManagedAuthoritySource(tmp_path).resolve("CPKT-WP-TEST@0.1")

    assert error.value.code == "authority_integrity_invalid"
