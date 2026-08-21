from __future__ import annotations

from dataclasses import replace

import pytest

from cp_knowledge_tools.policy import (
    PolicyCondition,
    PolicyConfiguration,
    PolicyDecisionValidator,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)

SUBJECT = PolicySubject("knowledge_object", "KO-TEST", "0.2", "Semantic Core")


def _condition(*, state: str = "satisfied") -> PolicyCondition:
    return PolicyCondition(
        condition_ref="PCOND-TEST",
        condition_type="publication_window",
        subject_refs=(SUBJECT,),
        responsible_context="synthetic-test-policy-owner",
        required_evidence_refs=("COND-EVIDENCE",),
        fulfilment_evidence_refs=("COND-EVIDENCE",),
        enforcement_point="g5_pre_publication",
        valid_from="2026-08-15T09:00:00+02:00",
        valid_until="2026-08-15T12:00:00+02:00",
        failure_action="deny",
        state=state,
    )


def _evaluation(**changes: object) -> PolicyEvaluationInput:
    values = {
        "policy_evaluation_ref": "PEVAL-PUBLISH",
        "actor_or_consumer_ref": "SYNTHETIC-PUBLISHER",
        "purpose": "controlled_knowledge_publication",
        "requested_operation": "publish",
        "subject_refs": (SUBJECT,),
        "policy_config_ref": "SYNTHETIC-PUBLISH-POLICY@0.1",
        "processing_zone": "synthetic_test_staging",
        "profile_refs": (),
        "profile_applicability": ProfileApplicability(resolution_status="resolved"),
        "policy_anchor_ids": ("PA-SYNTHETIC",),
        "requested_at": "2026-08-15T10:03:00+02:00",
        "context_valid_at": "2026-08-15T10:03:00+02:00",
        "requested_action": "publish",
        "actor_roles": ("synthetic_test_publisher",),
        "requested_data_operations": ("publish",),
        "requested_effect_scope": "publication_package_version",
        "candidate_revision_ref": "LCR-TEST@0.1",
        "resolution_decision_ref": "RDL-TEST",
        "publication_change_set_ref": "PCS-TEST",
        "publication_change_set_version_ref": "PCS-TEST@0.1",
        "publication_change_set_hash": "change-set-hash",
        "publication_package_version_ref": "PPK-TEST@0.1",
        "publication_package_hash": "package-hash",
        "publication_finalization_plan_ref": "PFP-TEST",
        "publication_unit_refs": ("KO-TEST@0.2",),
        "knowledge_content_hash_refs": ("knowledge-hash",),
        "prepublication_representation_hash_refs": ("prepublication-hash",),
        "target_refs": (
            "Knowledge/Synthetic/KO-TEST@0.2.md",
            "synthetic-test-target",
        ),
        "publication_authority_ref": "synthetic_test_publication_authority",
        "publication_review_record_ref": "RVR-PUBLICATION",
        "review_record_refs": ("RVR-CANDIDATE", "RVR-PUBLICATION"),
        "conformance_report_refs": ("CONF-CORE", "CONF-CROSS-VIEW"),
        "risk_input_refs": ("RISK-INPUT",),
        "quality_input_refs": ("QUALITY-INPUT",),
        "agent_authority_context": "synthetic_test_no_standing_authority",
    }
    values.update(changes)
    return PolicyEvaluationInput(**values)


def _configuration(
    *,
    effect: str = "permit",
    conditions: tuple[PolicyCondition, ...] = (),
) -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_ref="SYNTHETIC-PUBLISH-POLICY",
        version="0.1",
        status="active",
        rules=(
            PolicyRule(
                policy_rule_ref="RULE-PUBLISH",
                actor_or_consumer_ref="SYNTHETIC-PUBLISHER",
                purpose="controlled_knowledge_publication",
                requested_operation="publish",
                subject_ref=SUBJECT,
                required_policy_anchor_ids=("PA-SYNTHETIC",),
                effect=effect,
                reason=f"synthetic_{effect}",
                conditions=conditions,
                authorized_scope="publication_package_version",
            ),
        ),
        decision_authority_ref="synthetic_test_policy_decision_authority",
        valid_from="2026-08-15T09:00:00+02:00",
        valid_until="2026-08-15T12:00:00+02:00",
        synthetic_test_fixture=True,
    )


def test_publish_evaluation_carries_full_context_and_exact_decision_binding() -> None:
    evaluation = _evaluation()
    decision = PolicyEvaluator().evaluate(evaluation, _configuration())

    assert decision.result == "permit"
    assert decision.authorized_actions == ("publish",)
    assert decision.authorized_subject_refs == (SUBJECT,)
    assert decision.authorized_scope == "publication_package_version"
    assert decision.policy_configuration_ref == "SYNTHETIC-PUBLISH-POLICY@0.1"
    assert decision.context_fingerprint == evaluation.context_fingerprint
    assert decision.publication_record_created is False
    assert decision.synthetic_test_fixture is True
    assert (
        PolicyDecisionValidator()
        .validate(
            decision,
            evaluation,
        )
        .disposition
        == "valid"
    )


@pytest.mark.parametrize("effect", ["conditions", "review", "escalate", "deny"])
def test_active_sec_policy_results_are_preserved(effect: str) -> None:
    conditions = (_condition(),) if effect == "conditions" else ()
    decision = PolicyEvaluator().evaluate(
        _evaluation(),
        _configuration(effect=effect, conditions=conditions),
    )

    assert decision.result == effect
    assert decision.conditions == conditions
    assert decision.publication_record_created is False


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"actor_or_consumer_ref": ""}, "policy_actor_or_consumer_missing"),
        ({"purpose": ""}, "policy_purpose_missing"),
        ({"processing_zone": ""}, "processing_zone_unknown"),
        ({"candidate_revision_ref": None}, "candidate_revision_ref_missing"),
        ({"resolution_decision_ref": None}, "resolution_decision_ref_missing"),
        (
            {"publication_change_set_hash": None},
            "publication_change_set_hash_missing",
        ),
        (
            {"publication_package_version_ref": None},
            "publication_package_version_ref_missing",
        ),
        (
            {"publication_review_record_ref": None},
            "publication_review_record_ref_missing",
        ),
        (
            {"publication_finalization_plan_ref": None},
            "publication_finalization_plan_ref_missing",
        ),
        ({"publication_unit_refs": ()}, "publication_unit_refs_missing"),
        (
            {"knowledge_content_hash_refs": ()},
            "knowledge_content_hash_refs_missing",
        ),
        (
            {"prepublication_representation_hash_refs": ()},
            "prepublication_representation_hash_refs_missing",
        ),
        ({"target_refs": ()}, "publication_target_refs_missing"),
        (
            {"publication_authority_ref": None},
            "publication_authority_ref_missing",
        ),
        ({"risk_input_refs": ()}, "risk_inputs_missing"),
        ({"quality_input_refs": ()}, "quality_inputs_missing"),
        ({"agent_authority_context": None}, "agent_authority_context_missing"),
    ],
)
def test_publish_context_required_inputs_fail_closed(
    changes: dict[str, object],
    reason: str,
) -> None:
    decision = PolicyEvaluator().evaluate(
        _evaluation(**changes),
        _configuration(),
    )

    assert decision.result == "deny"
    assert decision.decision_reasons == (reason,)


def test_missing_live_publication_policy_fails_closed() -> None:
    decision = PolicyEvaluator().evaluate(_evaluation(policy_config_ref=""), None)

    assert decision.result == "deny"
    assert decision.authorized_actions == ()
    assert decision.decision_reasons == ("policy_configuration_missing",)
    assert decision.synthetic_test_fixture is False


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_revision_ref": "LCR-CHANGED@0.2"},
        {"resolution_decision_ref": "RDL-CHANGED"},
        {"publication_change_set_hash": "changed-hash"},
        {"publication_package_version_ref": "PPK-TEST@0.2"},
        {"subject_refs": (replace(SUBJECT, version="0.3"),)},
        {"actor_or_consumer_ref": "OTHER-ACTOR"},
        {"purpose": "other-purpose"},
        {"processing_zone": "other-zone"},
        {"requested_action": "write_back", "requested_operation": "write_back"},
        {"profile_refs": ("test.profile@1.0",)},
        {"agent_authority_context": "changed-authority"},
        {"risk_input_refs": ("RISK-CHANGED",)},
        {"quality_input_refs": ("QUALITY-CHANGED",)},
        {"publication_review_record_ref": "RVR-CHANGED"},
        {"publication_finalization_plan_ref": "PFP-CHANGED"},
        {"publication_unit_refs": ("KO-TEST@0.3",)},
        {"knowledge_content_hash_refs": ("knowledge-hash-changed",)},
        {
            "prepublication_representation_hash_refs": (
                "prepublication-hash-changed",
            )
        },
        {"target_refs": ("Knowledge/Changed.md", "changed-context")},
        {"publication_authority_ref": "changed-authority"},
    ],
)
def test_material_policy_context_changes_require_reevaluation(
    changes: dict[str, object],
) -> None:
    original = _evaluation()
    decision = PolicyEvaluator().evaluate(original, _configuration())

    validation = PolicyDecisionValidator().validate(
        decision,
        replace(original, **changes),
    )

    assert validation.disposition == "stale"
    assert validation.reason_code == "policy_decision_context_stale"


def test_publish_is_not_write_back() -> None:
    evaluation = _evaluation(
        requested_operation="write_back",
        requested_action="write_back",
        requested_data_operations=("write_back",),
    )
    decision = PolicyEvaluator().evaluate(evaluation, _configuration())

    assert decision.result == "deny"
    assert decision.decision_reasons == ("requested_operation_unsupported",)
