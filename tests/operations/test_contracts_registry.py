from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cp_knowledge_tools.operations.contracts import (
    AuthorityDecision,
    AuthorityDisposition,
    MutationAction,
    MutationKind,
    MutationPlan,
    OperationClass,
    OperationContext,
    OperationPlan,
    OperationRequest,
    OperationResult,
    OperationSpec,
    ResultDisposition,
)
from cp_knowledge_tools.operations.registry import build_standard_registry


def test_core_contracts_are_versioned_and_immutable() -> None:
    request = OperationRequest(
        operation_name="governance.resolve",
        operation_version="0.1",
        targets=("CPKS-SPEC-ART",),
        requested_mode="check",
        requester_ref="owner",
        correlation_id="corr-1",
    )
    context = OperationContext(
        operation_name=request.operation_name,
        operation_version=request.operation_version,
        target_system="cp-wiki",
        vault_root="/vault",
        repo_root="/repo",
        run_root="/runs",
        verified_roots={"mutation_root": "/vault"},
        target_environment={
            "target_kind": "cp-wiki",
            "kind": "local_vault",
            "identity": "file:///vault",
            "classification": "test",
        },
        targets=request.targets,
        actual_current_state={"version": "0.5"},
        active_rule_homes={"CPKS-SPEC-ART": "0.5"},
        rule_home_integrity={"CPKS-SPEC-ART": True},
        authority_basis=("CPKT-WP-002@0.1",),
        authority_scope=("CPKS-SPEC-ART",),
        runtime_authority={"disposition": "authorized"},
        preserve=("body",),
        out_of_scope=("policy",),
        lifecycle_profile="specification",
        validation_profile="active_governance",
        mutation_class="QUERY",
        remote_boundaries=("no_push",),
        implementation_versions={"contract": "0.1"},
        expected_source_fingerprints={"active": "abc"},
        correlation_id="corr-1",
        run_id="run-1",
    )
    plan = OperationPlan(
        plan_id="plan-1",
        request_fingerprint=request.fingerprint,
        inputs={"stable_id": "CPKS-SPEC-ART"},
        expected_source_fingerprints={"active": "abc"},
        targets=request.targets,
        actions=("resolve",),
        dependencies=(),
        expected_new_states={"status": "active"},
        precommit_validations=("integrity",),
        postconditions=(),
        compensation_actions=(),
        derived_actions=(),
        authority_gates=("read_only",),
    )
    result = OperationResult(
        operation_name=request.operation_name,
        operation_version="0.1",
        disposition=ResultDisposition.SUCCEEDED,
        run_id="run-1",
        correlation_id="corr-1",
        message="resolved",
    )

    assert request.contract_version == context.contract_version == "0.1"
    assert plan.request_fingerprint == request.fingerprint
    assert result.disposition is ResultDisposition.SUCCEEDED
    with pytest.raises(FrozenInstanceError):
        request.operation_name = "other"  # type: ignore[misc]


def test_registry_exposes_tested_k2_operations() -> None:
    registry = build_standard_registry()

    assert set(registry.operation_ids()) == {
        "governance.resolve",
        "governance.preflight",
        "artifact.revise",
        "artifact.transition",
        "artifact.activate",
        "derived.governance.refresh",
        "incident.capture",
    }
    activation = registry.resolve("artifact.activate", "0.1")
    assert activation.spec.operation_class is OperationClass.MUTATE_LOCAL
    assert activation.spec.supported_modes == ("check", "apply")
    assert activation.spec.supported_scope["document_types"] == [
        "decision_record",
        "framework",
        "policy",
        "process",
        "specification",
    ]
    assert activation.spec.supported_scope["activation_modes"] == [
        "initial",
        "follow_up",
    ]
    assert "cli" in activation.spec.surface_mappings


def test_registry_rejects_missing_handler() -> None:
    registry = build_standard_registry()
    invalid = OperationSpec(
        operation_id="invalid.operation",
        operation_version="0.1",
        operation_class=OperationClass.QUERY,
        supported_modes=("check",),
        target_classes=("test",),
        required_inputs=(),
        supported_scope={},
        unsupported_scope=(),
        surface_mappings={"cli": "invalid"},
        handler_ref="missing.module:handler",
    )

    with pytest.raises(ValueError, match="handler"):
        registry.register(invalid)


def test_authority_scope_is_not_inferred_from_write_capability() -> None:
    missing = AuthorityDecision.evaluate(
        authority_ref=None,
        authority_scope=(),
        targets=("CPKS-SPEC-ART",),
    )
    wrong_scope = AuthorityDecision.evaluate(
        authority_ref="CPKT-WP-002@0.1",
        authority_scope=("CPKS-SPEC-TST",),
        targets=("CPKS-SPEC-ART",),
    )

    assert missing.disposition is AuthorityDisposition.BLOCKED
    assert wrong_scope.disposition is AuthorityDisposition.BLOCKED


def test_mutation_plan_uses_explicit_file_actions() -> None:
    mutation = MutationPlan(
        plan_id="mut-1",
        request_fingerprint="req",
        actions=(
            MutationAction(
                kind=MutationKind.CREATE,
                path="Development/Example.md",
                content="body",
                expected_fingerprint=None,
            ),
        ),
        expected_source_fingerprints={},
    )

    assert mutation.actions[0].kind is MutationKind.CREATE
