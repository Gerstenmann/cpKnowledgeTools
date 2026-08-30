from __future__ import annotations

from dataclasses import replace

import pytest

from cp_knowledge_tools.policy import (
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
    ProfileReferenceResolution,
)

HUMAN_SOURCE = PolicySubject(
    "human_interaction_source_record",
    "HISR-SYNTHETIC-POLICY-CONFORMANCE",
    "0.1",
    "Source and Evidence",
)
EMPTY_APPLICABLE_PROFILE_SET = ProfileApplicability(resolution_status="resolved")


def _human_policy_configuration() -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_ref="CPKS-POL-HUM-SRC",
        version="0.1",
        status="active",
        rules=(
            PolicyRule(
                policy_rule_ref="CPKS-POL-HUM-SRC@0.1#capture-synthetic-test",
                actor_or_consumer_ref="SYNTHETIC-HUMAN-SOURCE-CONSUMER",
                purpose="controlled_human_review",
                requested_operation=None,
                requested_action="capture",
                requested_data_operations=("read_content", "create"),
                subject_ref=HUMAN_SOURCE,
                required_policy_anchor_ids=("CPKS-POL-HUM-SRC@0.1",),
                effect="permit",
                reason="synthetic_human_source_capture_in_policy_scope",
                authorized_scope="synthetic_human_source_capture",
            ),
            PolicyRule(
                policy_rule_ref="CPKS-POL-HUM-SRC@0.1#process-synthetic-test",
                actor_or_consumer_ref="SYNTHETIC-HUMAN-SOURCE-CONSUMER",
                purpose="controlled_human_enrichment",
                requested_operation=None,
                requested_action="process",
                requested_data_operations=(
                    "read_content",
                    "classify",
                    "derive",
                ),
                subject_ref=HUMAN_SOURCE,
                required_policy_anchor_ids=("CPKS-POL-HUM-SRC@0.1",),
                effect="permit",
                reason="synthetic_human_source_processing_in_policy_scope",
                authorized_scope="synthetic_human_source_processing",
            ),
        ),
        decision_authority_ref="SYNTHETIC-TEST-POLICY-DECISION-AUTHORITY",
        synthetic_test_fixture=True,
    )


def _evaluation(
    *,
    action: str,
    data_operations: tuple[str, ...],
    purpose: str = "controlled_human_review",
    profile_refs: tuple[str, ...] = (),
    profile_applicability: ProfileApplicability = EMPTY_APPLICABLE_PROFILE_SET,
) -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        policy_evaluation_ref=f"PEVAL-SYNTHETIC-{action.upper()}",
        actor_or_consumer_ref="SYNTHETIC-HUMAN-SOURCE-CONSUMER",
        purpose=purpose,
        requested_operation=None,
        requested_action=action,
        requested_data_operations=data_operations,
        subject_refs=(HUMAN_SOURCE,),
        policy_config_ref="CPKS-POL-HUM-SRC@0.1",
        processing_zone="local_processing_only",
        profile_refs=profile_refs,
        profile_applicability=profile_applicability,
        policy_anchor_ids=("CPKS-POL-HUM-SRC@0.1",),
        requested_at="2026-08-27T08:00:00+02:00",
        context_valid_at="2026-08-27T08:00:00+02:00",
    )


@pytest.mark.parametrize(
    ("action", "data_operations", "purpose", "authorized_scope"),
    [
        (
            "capture",
            ("read_content", "create"),
            "controlled_human_review",
            "synthetic_human_source_capture",
        ),
        (
            "process",
            ("read_content", "classify", "derive"),
            "controlled_human_enrichment",
            "synthetic_human_source_processing",
        ),
    ],
)
def test_active_human_source_policy_patterns_are_evaluable(
    action: str,
    data_operations: tuple[str, ...],
    purpose: str,
    authorized_scope: str,
) -> None:
    evaluation = _evaluation(
        action=action,
        data_operations=data_operations,
        purpose=purpose,
    )

    decision = PolicyEvaluator().evaluate(
        evaluation,
        _human_policy_configuration(),
    )

    assert decision.result == "permit"
    assert decision.authorized_actions == (action,)
    assert decision.requested_data_operations == data_operations
    assert decision.authorized_scope == authorized_scope
    assert decision.synthetic_test_fixture is True
    assert decision.decision_authority_ref == (
        "SYNTHETIC-TEST-POLICY-DECISION-AUTHORITY"
    )


@pytest.mark.parametrize(
    ("evaluation", "reason"),
    [
        (
            _evaluation(action="analyze_everything", data_operations=("derive",)),
            "policy_action_unknown",
        ),
        (
            _evaluation(action="process", data_operations=("enrich_magic",)),
            "policy_data_operation_unknown",
        ),
        (
            _evaluation(action="capture_snapshot", data_operations=("create",)),
            "contract_operation_used_as_policy_action",
        ),
        (
            _evaluation(action="claim_read", data_operations=("read_content",)),
            "policy_action_unknown",
        ),
        (
            _evaluation(action="publish", data_operations=("publish",)),
            "policy_data_operation_unknown",
        ),
    ],
)
def test_closed_policy_vocabularies_fail_closed(
    evaluation: PolicyEvaluationInput,
    reason: str,
) -> None:
    decision = PolicyEvaluator().evaluate(
        evaluation,
        _human_policy_configuration(),
    )

    assert decision.result == "deny"
    assert decision.authorized_actions == ()
    assert decision.decision_reasons == (reason,)


@pytest.mark.parametrize(
    "additional_action",
    ["publish", "export", "write_back", "store_in_memory"],
)
def test_allowed_create_data_operation_grants_no_additional_action(
    additional_action: str,
) -> None:
    evaluation = _evaluation(
        action=additional_action,
        data_operations=("create",),
    )

    decision = PolicyEvaluator().evaluate(
        evaluation,
        _human_policy_configuration(),
    )

    assert decision.result == "deny"
    assert decision.authorized_actions == ()


def test_context_package_inclusion_grants_no_memory_action() -> None:
    evaluation = _evaluation(
        action="store_in_memory",
        data_operations=("include_in_context_package",),
    )

    decision = PolicyEvaluator().evaluate(
        evaluation,
        _human_policy_configuration(),
    )

    assert decision.result == "deny"
    assert decision.authorized_actions == ()


def test_canonical_action_requires_explicit_data_operations() -> None:
    decision = PolicyEvaluator().evaluate(
        _evaluation(action="capture", data_operations=()),
        _human_policy_configuration(),
    )

    assert decision.result == "deny"
    assert decision.decision_reasons == ("policy_data_operations_missing",)


def test_profile_cannot_extend_closed_policy_vocabulary() -> None:
    profile_ref = "test.profile.policy-conformance@1.0"
    profile_context = ProfileApplicability(
        resolution_status="resolved",
        reference_resolutions=(
            ProfileReferenceResolution(
                concrete_ref=profile_ref,
                artifact_type="profile_manifest",
                lifecycle_status="active",
                applicable=True,
                compatible=True,
            ),
        ),
    )
    evaluation = _evaluation(
        action="profile_custom_action",
        data_operations=("profile_custom_operation",),
        profile_refs=(profile_ref,),
        profile_applicability=profile_context,
    )

    decision = PolicyEvaluator().evaluate(
        evaluation,
        _human_policy_configuration(),
    )

    assert decision.result == "deny"
    assert decision.authorized_actions == ()
    assert decision.decision_reasons == ("policy_action_unknown",)


def test_capture_decision_does_not_silently_authorize_process() -> None:
    capture = _evaluation(
        action="capture",
        data_operations=("read_content", "create"),
    )
    process = replace(
        capture,
        policy_evaluation_ref="PEVAL-SYNTHETIC-PROCESS",
        requested_action="process",
        requested_data_operations=("read_content", "classify", "derive"),
        purpose="controlled_human_enrichment",
    )

    capture_decision = PolicyEvaluator().evaluate(
        capture,
        _human_policy_configuration(),
    )

    assert capture_decision.authorized_actions == ("capture",)
    assert "process" not in capture_decision.authorized_actions
    assert capture.context_fingerprint != process.context_fingerprint
