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

CONSUMER = "consumer-test"
PURPOSE = "retrieve-status"
PROFILE_REF = "test.profile.delivery@1.0"
KO = PolicySubject("knowledge_object", "KO-TEST", "0.1", "Semantic Core")
EVIDENCE = PolicySubject(
    "evidence_address",
    "EA-RESTRICTED",
    "0.1",
    "Source and Evidence",
)
RESOLVED_EMPTY_PROFILES = ProfileApplicability(resolution_status="resolved")


def _profile_resolution(
    concrete_ref: str = PROFILE_REF,
    *,
    artifact_type: str = "profile_manifest",
    lifecycle_status: str = "active",
    applicable: bool = True,
    compatible: bool = True,
) -> ProfileReferenceResolution:
    return ProfileReferenceResolution(
        concrete_ref=concrete_ref,
        artifact_type=artifact_type,
        lifecycle_status=lifecycle_status,
        applicable=applicable,
        compatible=compatible,
    )


def _profile_context(
    *resolutions: ProfileReferenceResolution,
    resolution_status: str = "resolved",
    required_profile_refs: tuple[str, ...] = (),
    conflicting_profile_refs: tuple[str, ...] = (),
) -> ProfileApplicability:
    return ProfileApplicability(
        resolution_status=resolution_status,
        reference_resolutions=resolutions,
        required_profile_refs=required_profile_refs,
        conflicting_profile_refs=conflicting_profile_refs,
    )


def _configuration(*, status: str = "active") -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_ref="TEST-POLICY",
        version="0.1",
        status=status,
        rules=(
            PolicyRule(
                policy_rule_ref="RULE-CLAIM-READ",
                actor_or_consumer_ref=CONSUMER,
                purpose=PURPOSE,
                requested_operation="claim_read",
                subject_ref=KO,
                required_policy_anchor_ids=("PA-KO",),
                effect="permit",
                reason="claim_read_allowed",
            ),
            PolicyRule(
                policy_rule_ref="RULE-EVIDENCE-DENY",
                actor_or_consumer_ref=CONSUMER,
                purpose=PURPOSE,
                requested_operation="evidence_resolution",
                subject_ref=EVIDENCE,
                required_policy_anchor_ids=("PA-RESTRICTED",),
                effect="deny",
                reason="restricted_evidence_denied",
            ),
        ),
    )


def _evaluation(
    operation: str,
    subject: PolicySubject,
    anchors: tuple[str, ...],
    *,
    policy_config_ref: str = "TEST-POLICY@0.1",
    profile_refs: tuple[str, ...] = (),
    profile_applicability: ProfileApplicability = RESOLVED_EMPTY_PROFILES,
) -> PolicyEvaluationInput:
    return PolicyEvaluationInput(
        policy_evaluation_ref=f"PEVAL-{operation}",
        actor_or_consumer_ref=CONSUMER,
        purpose=PURPOSE,
        requested_operation=operation,
        subject_refs=(subject,),
        policy_config_ref=policy_config_ref,
        processing_zone="local_test",
        profile_refs=profile_refs,
        profile_applicability=profile_applicability,
        policy_anchor_ids=anchors,
        requested_at="2026-08-09T00:00:00+02:00",
        context_valid_at="2026-08-09T00:00:00+02:00",
    )


def test_resolved_empty_profile_set_keeps_policy_operations_independent() -> None:
    evaluator = PolicyEvaluator()
    configuration = _configuration()

    claim_decision = evaluator.evaluate(
        _evaluation("claim_read", KO, ("PA-KO",)),
        configuration,
    )
    evidence_decision = evaluator.evaluate(
        _evaluation(
            "evidence_resolution",
            EVIDENCE,
            ("PA-RESTRICTED",),
        ),
        configuration,
    )

    assert claim_decision.result == "permit"
    assert claim_decision.authorized_actions == ("claim_read",)
    assert claim_decision.authorized_subject_refs == (KO,)
    assert evidence_decision.result == "deny"
    assert evidence_decision.authorized_actions == ()
    assert evidence_decision.authorized_subject_refs == ()


def test_resolved_applicable_profile_is_accepted_but_does_not_decide() -> None:
    evaluation = _evaluation(
        "claim_read",
        KO,
        ("PA-KO",),
        profile_refs=(PROFILE_REF,),
        profile_applicability=_profile_context(_profile_resolution()),
    )

    decision = PolicyEvaluator().evaluate(evaluation, _configuration())

    assert decision.result == "permit"
    assert decision.decision_reasons == ("claim_read_allowed",)


@pytest.mark.parametrize(
    ("evaluation", "reason"),
    [
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_applicability=_profile_context(
                    resolution_status="unresolved"
                ),
            ),
            "policy_profile_reference_unresolved",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_applicability=_profile_context(_profile_resolution()),
            ),
            "policy_applicable_profile_missing",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=("CPKS-SPEC-MEM@0.3",),
                profile_applicability=_profile_context(
                    _profile_resolution(
                        "CPKS-SPEC-MEM@0.3",
                        artifact_type="specification",
                    )
                ),
            ),
            "policy_profile_reference_type_invalid",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=(PROFILE_REF,),
                profile_applicability=_profile_context(
                    _profile_resolution(compatible=False)
                ),
            ),
            "policy_profile_not_applicable",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=(PROFILE_REF,),
                profile_applicability=_profile_context(
                    _profile_resolution(lifecycle_status="withdrawn")
                ),
            ),
            "policy_profile_not_applicable",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=(PROFILE_REF,),
                profile_applicability=_profile_context(
                    _profile_resolution(applicable=False)
                ),
            ),
            "policy_profile_not_applicable",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=("test.profile.delivery",),
                profile_applicability=_profile_context(
                    _profile_resolution("test.profile.delivery")
                ),
            ),
            "policy_profile_reference_unresolved",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                profile_refs=(PROFILE_REF,),
                profile_applicability=_profile_context(
                    _profile_resolution(),
                    conflicting_profile_refs=(PROFILE_REF,),
                ),
            ),
            "policy_profile_conflict",
        ),
    ],
)
def test_profile_context_failures_deny(
    evaluation: PolicyEvaluationInput,
    reason: str,
) -> None:
    decision = PolicyEvaluator().evaluate(evaluation, _configuration())

    assert decision.result == "deny"
    assert decision.authorized_actions == ()
    assert decision.authorized_subject_refs == ()
    assert decision.decision_reasons == (reason,)


@pytest.mark.parametrize(
    ("evaluation", "configuration", "reason"),
    [
        (
            _evaluation("claim_read", KO, ("PA-KO",)),
            None,
            "policy_configuration_missing",
        ),
        (
            _evaluation("claim_read", KO, ("PA-KO",)),
            _configuration(status="draft"),
            "policy_configuration_not_active",
        ),
        (
            _evaluation(
                "claim_read",
                KO,
                ("PA-KO",),
                policy_config_ref="OTHER@0.1",
            ),
            _configuration(),
            "policy_configuration_not_applicable",
        ),
        (
            _evaluation("claim_read", KO, ()),
            _configuration(),
            "no_applicable_policy_rule",
        ),
        (
            _evaluation("export", KO, ("PA-KO",)),
            _configuration(),
            "requested_operation_unsupported",
        ),
    ],
)
def test_policy_evaluation_fails_closed(
    evaluation: PolicyEvaluationInput,
    configuration: PolicyConfiguration | None,
    reason: str,
) -> None:
    decision = PolicyEvaluator().evaluate(evaluation, configuration)

    assert decision.result == "deny"
    assert decision.authorized_actions == ()
    assert decision.authorized_subject_refs == ()
    assert decision.decision_reasons == (reason,)


def test_conflicting_applicable_rules_fail_closed() -> None:
    configuration = _configuration()
    permit_rule = configuration.rules[0]
    conflicting = PolicyRule(
        policy_rule_ref="RULE-CLAIM-DENY",
        actor_or_consumer_ref=permit_rule.actor_or_consumer_ref,
        purpose=permit_rule.purpose,
        requested_operation=permit_rule.requested_operation,
        subject_ref=permit_rule.subject_ref,
        required_policy_anchor_ids=permit_rule.required_policy_anchor_ids,
        effect="deny",
        reason="conflicting_rule",
    )
    configuration = PolicyConfiguration(
        policy_ref=configuration.policy_ref,
        version=configuration.version,
        status=configuration.status,
        rules=(*configuration.rules, conflicting),
    )

    decision = PolicyEvaluator().evaluate(
        _evaluation("claim_read", KO, ("PA-KO",)),
        configuration,
    )

    assert decision.result == "deny"
    assert decision.decision_reasons == ("unresolved_policy_rule_conflict",)


def test_partial_subject_policy_does_not_authorize_broader_scope() -> None:
    other_subject = PolicySubject(
        "knowledge_object",
        "KO-OTHER",
        "0.1",
        "Semantic Core",
    )
    evaluation = _evaluation("claim_read", KO, ("PA-KO",))
    evaluation = replace(
        evaluation,
        subject_refs=(KO, other_subject),
    )

    decision = PolicyEvaluator().evaluate(evaluation, _configuration())

    assert decision.result == "deny"
    assert decision.authorized_subject_refs == ()
    assert decision.decision_reasons == ("policy_subject_scope_incomplete",)
