from __future__ import annotations

from dataclasses import replace

import pytest

from cp_knowledge_tools.lifecycle import (
    G5PolicyGate,
    G5PolicyGateRequest,
    G6PublicationReadinessGate,
    G6PublicationReadinessRequest,
    PublicationAuthorityEvidence,
    PublicationReviewFactory,
    PublicationReviewValidator,
    ReviewRecord,
)
from cp_knowledge_tools.policy import (
    PolicyCondition,
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
)

from .test_publication import _package


def _publication_review(candidate, package):
    requirement, request = PublicationReviewFactory().create(
        package,
        required_reviewer_authority="project_owner_default_human",
        rule_basis_refs=("CPKS-SPEC-KPR@0.3#14.5",),
        profile_refs=(),
    )
    record = ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref="SYNTHETIC-PROJECT-OWNER",
        reviewer_authority=request.required_reviewer_authority,
        result="passed",
        findings=("synthetic package binding fixture",),
        conditions=(),
        evidence_reviewed_refs=request.evidence_and_context_refs,
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T10:02:00+02:00",
        synthetic_test_fixture=True,
    )
    validation = PublicationReviewValidator().validate(
        record,
        request,
        requirement,
        package,
        candidate,
    )
    return record, validation


def _subject(package) -> PolicySubject:
    unit = package.publication_unit_binding
    return PolicySubject(
        "knowledge_object",
        unit.knowledge_object_id,
        unit.knowledge_object_version,
        "Semantic Core",
    )


def _condition(package, *, state: str = "satisfied", evidence: bool = True):
    return PolicyCondition(
        condition_ref="PCOND-G5",
        condition_type="publication_window",
        subject_refs=(_subject(package),),
        responsible_context="synthetic-test-policy-owner",
        required_evidence_refs=("COND-EVIDENCE",),
        fulfilment_evidence_refs=("COND-EVIDENCE",) if evidence else (),
        enforcement_point="g5_pre_publication",
        valid_from="2026-08-15T09:00:00+02:00",
        valid_until="2026-08-15T12:00:00+02:00",
        failure_action="deny",
        state=state,
    )


def _policy(package, *, effect="permit", conditions=()):
    subject = _subject(package)
    unit = package.publication_unit_binding
    evaluation = PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-PACKAGE",
        actor_or_consumer_ref="SYNTHETIC-PUBLISHER",
        purpose="controlled_knowledge_publication",
        requested_operation="publish",
        subject_refs=(subject,),
        policy_config_ref="SYNTHETIC-PUBLISH-POLICY@0.1",
        processing_zone="synthetic_test_staging",
        profile_refs=package.profile_refs,
        profile_applicability=ProfileApplicability(resolution_status="resolved"),
        policy_anchor_ids=package.policy_anchor_refs,
        requested_at="2026-08-15T10:03:00+02:00",
        context_valid_at="2026-08-15T10:03:00+02:00",
        requested_action="publish",
        actor_roles=("synthetic_test_publisher",),
        requested_data_operations=("read_content", "transform", "create"),
        requested_effect_scope="publication_package_version",
        candidate_revision_ref=package.candidate_revision_ref,
        resolution_decision_ref=package.resolution_decision_ref,
        publication_change_set_ref=(package.change_set.publication_change_set_ref),
        publication_change_set_version_ref=(package.change_set.change_set_version_ref),
        publication_change_set_hash=package.change_set.change_set_hash.value,
        publication_package_version_ref=package.package_version_ref,
        publication_package_hash=package.package_hash.value,
        publication_finalization_plan_ref=(
            package.publication_finalization_plan.publication_finalization_plan_ref
        ),
        publication_unit_refs=(unit.publication_unit_ref,),
        knowledge_content_hash_refs=(unit.content_hash.value,),
        prepublication_representation_hash_refs=(
            unit.prepublication_representation_hash.value,
        ),
        target_refs=(
            package.publication_finalization_plan.canonical_path,
            package.publication_finalization_plan.maintenance_context_ref,
        ),
        publication_authority_ref=(
            package.publication_finalization_plan.publication_authority_ref
        ),
        publication_review_record_ref="RVR-PUBLICATION",
        review_record_refs=(*package.candidate_review_record_refs, "RVR-PUBLICATION"),
        conformance_report_refs=package.conformance_report_refs,
        risk_input_refs=("RISK-INPUT",),
        quality_input_refs=("QUALITY-INPUT",),
        agent_authority_context="synthetic_test_no_standing_authority",
    )
    configuration = PolicyConfiguration(
        policy_ref="SYNTHETIC-PUBLISH-POLICY",
        version="0.1",
        status="active",
        rules=(
            PolicyRule(
                policy_rule_ref="RULE-PUBLISH",
                actor_or_consumer_ref=evaluation.actor_or_consumer_ref,
                purpose=evaluation.purpose,
                requested_operation="publish",
                requested_action="publish",
                requested_data_operations=("read_content", "transform", "create"),
                subject_ref=subject,
                required_policy_anchor_ids=package.policy_anchor_refs,
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
    return evaluation, PolicyEvaluator().evaluate(evaluation, configuration)


def _g5(*, effect="permit", conditions=(), review=True):
    candidate, decision, package = _package()
    record, review_validation = _publication_review(candidate, package)
    evaluation, policy_decision = _policy(
        package,
        effect=effect,
        conditions=conditions,
    )
    evaluation = replace(
        evaluation, publication_review_record_ref=record.review_record_ref
    )
    evaluation = replace(
        evaluation,
        review_record_refs=(
            *package.candidate_review_record_refs,
            record.review_record_ref,
        ),
    )
    policy_decision = PolicyEvaluator().evaluate(
        evaluation,
        PolicyConfiguration(
            policy_ref="SYNTHETIC-PUBLISH-POLICY",
            version="0.1",
            status="active",
            rules=(
                PolicyRule(
                    policy_rule_ref="RULE-PUBLISH",
                    actor_or_consumer_ref=evaluation.actor_or_consumer_ref,
                    purpose=evaluation.purpose,
                    requested_operation="publish",
                    requested_action="publish",
                    requested_data_operations=(
                        "read_content",
                        "transform",
                        "create",
                    ),
                    subject_ref=_subject(package),
                    required_policy_anchor_ids=package.policy_anchor_refs,
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
        ),
    )
    result = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=evaluation,
            policy_decision=policy_decision,
            publication_review=(review_validation if review else None),
            context_valid_at="2026-08-15T10:04:00+02:00",
        )
    )
    return (
        candidate,
        decision,
        package,
        review_validation,
        evaluation,
        policy_decision,
        result,
    )


def _authority(package):
    return PublicationAuthorityEvidence(
        authority_ref="synthetic_test_publication_authority",
        authority_kind="publication_authority",
        authorized_action="publish",
        authorized_package_version_ref=package.package_version_ref,
        authorized_subject_refs=(
            package.publication_unit_binding.publication_unit_ref,
        ),
        authority_context_ref="synthetic_not_live_authority",
        valid_at="2026-08-15T10:04:00+02:00",
        explicitly_granted=True,
        synthetic_test_fixture=True,
    )


def test_g5_permit_and_satisfied_conditions_pass_without_publication() -> None:
    *_, permit = _g5()
    _, _, package, _, _, _, conditioned = _g5(
        effect="conditions",
        conditions=(_condition(_g5()[2]),),
    )

    assert permit.disposition == "passed"
    assert conditioned.disposition == "passed"
    assert package.publication_performed is False
    assert permit.execution_authorized is False


@pytest.mark.parametrize("state", ["open", "failed", "expired"])
def test_g5_blocks_non_satisfied_conditions(state: str) -> None:
    _, _, package = _package()
    *_, result = _g5(
        effect="conditions", conditions=(_condition(package, state=state),)
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "policy_conditions_not_satisfied"


def test_g5_blocks_condition_without_fulfilment_evidence() -> None:
    _, _, package = _package()
    *_, result = _g5(
        effect="conditions",
        conditions=(_condition(package, evidence=False),),
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "policy_condition_fulfilment_evidence_missing"


@pytest.mark.parametrize(
    ("effect", "reason"),
    [
        ("review", "policy_additional_review_required"),
        ("escalate", "policy_escalation_required"),
        ("deny", "policy_denied"),
    ],
)
def test_g5_blocks_non_permit_policy_results(effect: str, reason: str) -> None:
    *_, result = _g5(effect=effect)

    assert result.disposition == "blocked"
    assert result.reason_code == reason


def test_g5_requires_publication_review() -> None:
    *_, result = _g5(review=False)

    assert result.disposition == "blocked"
    assert result.reason_code == "publication_review_missing"


@pytest.mark.parametrize(
    ("foreign_basis", "reason"),
    [
        ("policy_evaluation", "policy_evaluation_not_policy_decision"),
        ("quality_gate", "quality_gate_not_publication_permit"),
        ("candidate_review", "candidate_review_not_publication_permit"),
    ],
)
def test_pg_n01_to_n03_foreign_permit_bases_fail_closed(
    foreign_basis: str,
    reason: str,
) -> None:
    candidate, _, package = _package()
    _, publication_review = _publication_review(candidate, package)
    evaluation, _ = _policy(package)
    result = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=evaluation,
            policy_decision=None,
            publication_review=publication_review,
            context_valid_at="2026-08-15T10:04:00+02:00",
            foreign_permit_basis=foreign_basis,
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == reason


def test_live_missing_policy_is_explicitly_fail_closed() -> None:
    candidate, _, package = _package()
    record, publication_review = _publication_review(candidate, package)
    evaluation, _ = _policy(package)
    evaluation = replace(
        evaluation,
        policy_config_ref="",
        publication_review_record_ref=record.review_record_ref,
        review_record_refs=(
            *package.candidate_review_record_refs,
            record.review_record_ref,
        ),
    )
    decision = PolicyEvaluator().evaluate(evaluation, None)
    result = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=evaluation,
            policy_decision=decision,
            publication_review=publication_review,
            context_valid_at="2026-08-15T10:04:00+02:00",
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "applicable_knowledge_publication_policy_missing"


def test_changed_change_set_or_resolution_after_permit_is_stale() -> None:
    *values, _ = _g5()
    _, _, package, review, evaluation, decision = values
    for changed_evaluation in (
        replace(evaluation, publication_change_set_hash="changed"),
        replace(evaluation, resolution_decision_ref="RDL-CHANGED"),
    ):
        result = G5PolicyGate().evaluate(
            G5PolicyGateRequest(
                package=package,
                policy_evaluation=changed_evaluation,
                policy_decision=decision,
                publication_review=review,
                context_valid_at="2026-08-15T10:04:00+02:00",
            )
        )
        assert result.disposition == "blocked"
        assert result.reason_code in {
            "policy_evaluation_package_binding_mismatch",
            "policy_decision_context_stale",
        }


def test_g6_synthetic_ready_is_not_execution_or_publication() -> None:
    candidate, resolution, package, review, _, _, g5 = _g5()
    readiness = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=_authority(package),
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )

    assert readiness.disposition == "ready"
    assert readiness.reason_code == "finalization_ready_for_test_isolated_execution"
    assert (
        package.publication_finalization_plan.publication_finalization_plan_ref
        in readiness.binding_refs
    )
    assert package.publication_unit_binding.content_hash.value in readiness.binding_refs
    assert (
        package.publication_unit_binding.prepublication_representation_hash.value
        in readiness.binding_refs
    )
    assert readiness.execution_performed is False
    assert readiness.publication_performed is False
    assert readiness.publication_record_created is False
    assert readiness.canonical_write_performed is False


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"candidate_reviews_satisfied": False}, "candidate_reviews_not_satisfied"),
        ({"publication_review": None}, "publication_review_missing"),
        ({"publication_authority": None}, "publication_authority_missing"),
        ({"recovery_consequences_determined": False}, "recovery_plan_incomplete"),
        ({"observed_prior_states": ()}, "expected_prior_state_mismatch"),
    ],
)
def test_g6_missing_requirements_block(
    changes: dict[str, object],
    reason: str,
) -> None:
    candidate, resolution, package, review, _, _, g5 = _g5()
    request = G6PublicationReadinessRequest(
        package=package,
        candidate_revision=candidate,
        resolution_decision=resolution,
        candidate_reviews_satisfied=True,
        publication_review=review,
        g5_result=g5,
        publication_authority=_authority(package),
        observed_prior_states=package.expected_prior_states,
        recovery_consequences_determined=True,
    )
    result = G6PublicationReadinessGate().evaluate(replace(request, **changes))

    assert result.disposition == "blocked"
    assert result.reason_code == reason


@pytest.mark.parametrize(
    ("package_change", "reason"),
    [
        ("publication_unit", "publication_unit_missing"),
        ("publication_unit_hash", "publication_unit_hash_missing"),
        ("change_set_hash", "publication_change_set_hash_missing"),
        ("package_hash", "publication_package_hash_missing"),
        ("recovery_plan", "recovery_plan_incomplete"),
    ],
)
def test_g6_missing_package_integrity_inputs_block(
    package_change: str,
    reason: str,
) -> None:
    candidate, resolution, package, review, _, _, g5 = _g5()
    if package_change == "publication_unit":
        changed_package = replace(package, publication_unit_binding=None)
    elif package_change == "publication_unit_hash":
        changed_package = replace(
            package,
            publication_unit_binding=replace(
                package.publication_unit_binding,
                content_hash=replace(
                    package.publication_unit_binding.content_hash,
                    value="",
                ),
            ),
        )
    elif package_change == "change_set_hash":
        changed_package = replace(
            package,
            change_set=replace(
                package.change_set,
                change_set_hash=replace(package.change_set.change_set_hash, value=""),
            ),
        )
    elif package_change == "package_hash":
        changed_package = replace(
            package,
            package_hash=replace(package.package_hash, value=""),
        )
    else:
        changed_package = replace(
            package,
            change_set=replace(
                package.change_set,
                rollback_or_compensation_plan_ref="",
            ),
        )
    result = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=changed_package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=_authority(package),
            observed_prior_states=changed_package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == reason


def test_technical_write_capability_is_not_publication_authority() -> None:
    candidate, resolution, package, review, _, _, g5 = _g5()
    result = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=None,
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
            foreign_authority_basis="technical_write_capability",
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "technical_write_capability_not_publication_authority"


def test_policy_permit_is_not_a_publication_record() -> None:
    candidate, resolution, package, review, _, policy_decision, g5 = _g5()
    result = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=_authority(package),
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
            claimed_publication_record_ref=policy_decision.policy_decision_ref,
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "policy_permit_not_publication_record"


@pytest.mark.parametrize(
    ("evaluation_change", "reason"),
    [
        (
            {"publication_finalization_plan_ref": "PFP-CHANGED"},
            "policy_evaluation_package_binding_mismatch",
        ),
        (
            {"knowledge_content_hash_refs": ("changed",)},
            "policy_evaluation_package_binding_mismatch",
        ),
        (
            {"prepublication_representation_hash_refs": ("changed",)},
            "policy_evaluation_package_binding_mismatch",
        ),
        (
            {"target_refs": ("Knowledge/Changed.md", "changed-context")},
            "policy_evaluation_package_binding_mismatch",
        ),
        (
            {"publication_authority_ref": "changed-authority"},
            "policy_evaluation_package_binding_mismatch",
        ),
    ],
)
def test_g5_requires_exact_finalization_policy_context(
    evaluation_change: dict[str, object],
    reason: str,
) -> None:
    *values, _ = _g5()
    _, _, package, review, evaluation, decision = values
    result = G5PolicyGate().evaluate(
        G5PolicyGateRequest(
            package=package,
            policy_evaluation=replace(evaluation, **evaluation_change),
            policy_decision=decision,
            publication_review=review,
            context_valid_at="2026-08-15T10:04:00+02:00",
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == reason


@pytest.mark.parametrize(
    ("plan_change", "reason"),
    [
        (
            {"canonical_path": "Knowledge/Changed.md"},
            "publication_finalization_plan_integrity_invalid",
        ),
        (
            {"publication_authority_ref": "changed-authority"},
            "publication_finalization_plan_integrity_invalid",
        ),
        (
            {
                "knowledge_content_hash": None,
            },
            "publication_finalization_plan_integrity_invalid",
        ),
        (
            {"finalization_method_ref": "changed-method@0.1"},
            "publication_finalization_plan_integrity_invalid",
        ),
    ],
)
def test_g6_blocks_stale_or_incomplete_finalization_plan(
    plan_change: dict[str, object],
    reason: str,
) -> None:
    candidate, resolution, package, review, _, _, g5 = _g5()
    changed_plan = replace(package.publication_finalization_plan, **plan_change)
    changed_package = replace(package, publication_finalization_plan=changed_plan)
    result = G6PublicationReadinessGate().evaluate(
        G6PublicationReadinessRequest(
            package=changed_package,
            candidate_revision=candidate,
            resolution_decision=resolution,
            candidate_reviews_satisfied=True,
            publication_review=review,
            g5_result=g5,
            publication_authority=_authority(package),
            observed_prior_states=package.expected_prior_states,
            recovery_consequences_determined=True,
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == reason
