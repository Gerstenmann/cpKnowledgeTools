from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cp_knowledge_tools.lifecycle import (
    ReviewCarryForwardRequest,
    ReviewCondition,
    ReviewOrchestrator,
    ReviewRecord,
    ReviewRecordValidator,
    ReviewRequestFactory,
    ReviewRequirementRouter,
    ReviewRoutingContext,
    ReviewRoutingPolicy,
)

from .test_resolution import _registered

KPR_REVIEW_RULES = ("CPKS-SPEC-KPR@0.3#10-12",)
HR005_POLICY = ReviewRoutingPolicy.from_rules(
    baseline_review_types=("technical_validation", "source_and_evidence_review"),
    operation_requirements={
        "add": ("domain_review",),
        "qualify": ("domain_review",),
        "temporal_progression": ("domain_review",),
        "constrain": ("domain_review",),
        "extend_scope": ("domain_review", "independent_quality_review"),
        "register_conflict": ("domain_review", "independent_quality_review"),
        "correct": ("domain_review", "independent_quality_review"),
        "update_epistemic_state": ("domain_review",),
        "update_evidence_basis": ("domain_review",),
    },
    identity_sensitive_operations=(
        "qualify",
        "temporal_progression",
        "constrain",
        "extend_scope",
        "correct",
    ),
    baseline_only_when_evidence_basis_unchanged=("update_evidence_basis",),
    policy_ref="GT-S2K-ENRICHMENT-01@0.8:review-routing",
)


def _authorities() -> dict[str, str]:
    return {
        "technical_validation": "authorized_validator",
        "source_and_evidence_review": "project_owner_default_human",
        "domain_review": "project_owner_default_human",
        "entity_and_identity_review": "project_owner_default_human",
        "independent_quality_review": "authorized_independent_human",
        "privacy_and_security_review": "specialized_privacy_security_authority",
        "policy_review": "trust_policy_review_authority",
    }


def _route(
    *,
    operation: str = "add",
    candidate=None,
    identity_relevant: bool = False,
    identity_ambiguous: bool = False,
    evidence_basis_only: bool = False,
    privacy_triggered: bool = False,
    authorities: dict[str, str] | None = None,
):
    candidate = candidate or _registered(operation=operation)
    context = ReviewRoutingContext(
        candidate_revision=candidate,
        semantic_change_operation=operation,
        same_object_relevant=identity_relevant,
        identity_ambiguous=identity_ambiguous,
        evidence_basis_only=evidence_basis_only,
        privacy_or_security_triggered=privacy_triggered,
        evidence_and_context_refs=("EVIDENCE-TEST", "CONTEXT-TEST"),
        known_questions_gaps_conflicts=("synthetic_question",),
        profile_refs=(),
        rule_basis_refs=KPR_REVIEW_RULES,
        authority_by_review_type=authorities or _authorities(),
    )
    return candidate, ReviewRequirementRouter(HR005_POLICY).route(context)


def _requests(requirement_set):
    return ReviewRequestFactory().create_requests(
        requirement_set,
        evidence_and_context_refs=("EVIDENCE-TEST",),
        known_questions_gaps_conflicts=("synthetic_question",),
    )


def _record(
    request,
    *,
    reviewer_ref: str = "SYNTHETIC-HUMAN-REVIEWER",
    reviewer_authority: str | None = None,
    result: str = "passed",
    conditions: tuple[ReviewCondition, ...] = (),
    asserted_effects: tuple[str, ...] = (),
    selects_conflict_winner: bool = False,
    synthetic: bool = True,
) -> ReviewRecord:
    return ReviewRecord.create(
        review_request_ref=request.review_request_ref,
        review_type=request.review_type,
        subject_ref=request.subject_ref,
        subject_version=request.subject_version,
        review_scope=request.review_scope,
        reviewer_ref=reviewer_ref,
        reviewer_authority=(
            reviewer_authority
            if reviewer_authority is not None
            else request.required_reviewer_authority
        ),
        result=result,
        findings=("synthetic finding: contract exercised",),
        conditions=conditions,
        evidence_reviewed_refs=("EVIDENCE-TEST",),
        rule_basis_refs=request.rule_basis_refs,
        profile_refs=request.profile_refs,
        reviewed_at="2026-08-15T02:10:00+02:00",
        synthetic_test_fixture=synthetic,
        asserted_effects=asserted_effects,
        selects_conflict_winner=selects_conflict_winner,
    )


def _valid_records(candidate, requirement_set):
    records = []
    validator = ReviewRecordValidator()
    for request in _requests(requirement_set):
        record = _record(request)
        validation = validator.validate(record, request, candidate)
        assert validation.disposition == "accepted"
        records.append(record)
    return tuple(records)


@pytest.mark.parametrize(
    ("operation", "identity_relevant", "expected"),
    [
        (
            "add",
            False,
            {"technical_validation", "source_and_evidence_review", "domain_review"},
        ),
        (
            "qualify",
            True,
            {
                "technical_validation",
                "source_and_evidence_review",
                "domain_review",
                "entity_and_identity_review",
            },
        ),
        (
            "temporal_progression",
            False,
            {"technical_validation", "source_and_evidence_review", "domain_review"},
        ),
        (
            "constrain",
            True,
            {
                "technical_validation",
                "source_and_evidence_review",
                "domain_review",
                "entity_and_identity_review",
            },
        ),
        (
            "extend_scope",
            True,
            {
                "technical_validation",
                "source_and_evidence_review",
                "domain_review",
                "independent_quality_review",
                "entity_and_identity_review",
            },
        ),
        (
            "register_conflict",
            False,
            {
                "technical_validation",
                "source_and_evidence_review",
                "domain_review",
                "independent_quality_review",
            },
        ),
        (
            "correct",
            True,
            {
                "technical_validation",
                "source_and_evidence_review",
                "domain_review",
                "independent_quality_review",
                "entity_and_identity_review",
            },
        ),
        (
            "update_epistemic_state",
            False,
            {"technical_validation", "source_and_evidence_review", "domain_review"},
        ),
    ],
)
def test_operation_sensitive_review_routing(
    operation: str,
    identity_relevant: bool,
    expected: set[str],
) -> None:
    candidate, evaluation = _route(
        operation=operation,
        identity_relevant=identity_relevant,
    )

    assert candidate.semantic_change_operation == operation
    assert evaluation.disposition == "routed"
    assert evaluation.requirement_set is not None
    assert {
        item.review_type for item in evaluation.requirement_set.requirements
    } == expected
    assert all(
        item.subject_version == candidate.lifecycle_candidate_revision_ref
        for item in evaluation.requirement_set.requirements
    )


def test_evidence_basis_only_uses_baseline_reviews() -> None:
    _, evaluation = _route(
        operation="update_evidence_basis",
        evidence_basis_only=True,
    )

    assert evaluation.requirement_set is not None
    assert {item.review_type for item in evaluation.requirement_set.requirements} == {
        "technical_validation",
        "source_and_evidence_review",
    }


def test_evidence_basis_semantic_change_adds_domain_review() -> None:
    _, evaluation = _route(
        operation="update_evidence_basis",
        evidence_basis_only=False,
    )

    assert evaluation.requirement_set is not None
    assert {item.review_type for item in evaluation.requirement_set.requirements} == {
        "technical_validation",
        "source_and_evidence_review",
        "domain_review",
    }


def test_privacy_security_review_is_triggered_only_by_explicit_risk_context() -> None:
    _, without = _route(operation="add")
    _, with_trigger = _route(operation="add", privacy_triggered=True)

    assert without.requirement_set is not None
    assert with_trigger.requirement_set is not None
    assert "privacy_and_security_review" not in {
        item.review_type for item in without.requirement_set.requirements
    }
    assert "privacy_and_security_review" in {
        item.review_type for item in with_trigger.requirement_set.requirements
    }


def test_candidate_review_router_never_emits_publication_review() -> None:
    _, evaluation = _route(operation="correct", identity_relevant=True)
    assert evaluation.requirement_set is not None

    assert "publication_review" not in {
        item.review_type for item in evaluation.requirement_set.requirements
    }
    assert evaluation.requirement_set.candidate_level_only is True


def test_review_requests_are_concrete_revision_bound_and_deterministic() -> None:
    _, evaluation = _route(operation="add")
    assert evaluation.requirement_set is not None

    first = _requests(evaluation.requirement_set)
    second = _requests(evaluation.requirement_set)

    assert first == second
    assert all(request.subject_version for request in first)
    assert all(request.evidence_and_context_refs for request in first)
    assert all(request.known_questions_gaps_conflicts for request in first)


def test_review_record_is_immutable_and_hash_validated() -> None:
    candidate, evaluation = _route(operation="add")
    assert evaluation.requirement_set is not None
    request = _requests(evaluation.requirement_set)[0]
    record = _record(request)
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "accepted"
    assert record.synthetic_test_fixture is True
    assert record.record_hash
    with pytest.raises(FrozenInstanceError):
        record.result = "failed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("ref", "operation", "missing_type", "reason_code"),
    [
        ("RV-N01", "add", "technical_validation", "required_review_missing"),
        (
            "RV-N02",
            "add",
            "source_and_evidence_review",
            "required_review_missing",
        ),
        (
            "RV-N03",
            "correct",
            "independent_quality_review",
            "required_review_missing",
        ),
        (
            "RV-N04",
            "extend_scope",
            "independent_quality_review",
            "required_review_missing",
        ),
        (
            "RV-N05",
            "register_conflict",
            "independent_quality_review",
            "required_review_missing",
        ),
    ],
)
def test_required_review_missing_is_not_candidate_review_ready(
    ref: str,
    operation: str,
    missing_type: str,
    reason_code: str,
) -> None:
    candidate, evaluation = _route(operation=operation)
    assert evaluation.requirement_set is not None
    records = tuple(
        record
        for record in _valid_records(candidate, evaluation.requirement_set)
        if record.review_type != missing_type
    )
    readiness = ReviewOrchestrator().evaluate_readiness(
        evaluation.requirement_set,
        records,
    )

    assert ref.startswith("RV-N")
    assert readiness.ready is False
    assert readiness.reason_code == reason_code
    assert missing_type in readiness.missing_review_types


def test_rv_n06_producer_cannot_self_issue_independent_quality_review() -> None:
    candidate = _registered(
        operation="correct",
        producer_provenance=("SYNTHETIC-PRODUCER",),
    )
    _, evaluation = _route(operation="correct", candidate=candidate)
    assert evaluation.requirement_set is not None
    request = next(
        item
        for item in _requests(evaluation.requirement_set)
        if item.review_type == "independent_quality_review"
    )
    record = _record(request, reviewer_ref="SYNTHETIC-PRODUCER")
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "blocked"
    assert validation.reason_code == "independent_self_review_forbidden"


def test_rv_n07_project_owner_producer_requires_other_human() -> None:
    candidate = _registered(
        operation="correct",
        producer_provenance=("PROJECT-OWNER",),
    )
    authorities = _authorities()
    authorities["independent_quality_review"] = "project_owner_default_human"
    _, evaluation = _route(
        operation="correct",
        candidate=candidate,
        authorities=authorities,
    )
    assert evaluation.requirement_set is not None
    request = next(
        item
        for item in _requests(evaluation.requirement_set)
        if item.review_type == "independent_quality_review"
    )
    record = _record(request, reviewer_ref="PROJECT-OWNER")
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "blocked"
    assert validation.reason_code == "block_other_human_required"


def test_rv_n08_material_revision_invalidates_prior_review() -> None:
    rev1, evaluation = _route(
        operation="add", candidate=_registered(revision_ref="CCR-REV-1")
    )
    assert evaluation.requirement_set is not None
    old_record = _valid_records(rev1, evaluation.requirement_set)[0]
    rev2, new_evaluation = _route(
        operation="add",
        candidate=_registered(revision_ref="CCR-REV-2"),
    )
    assert new_evaluation.requirement_set is not None
    readiness = ReviewOrchestrator().evaluate_readiness(
        new_evaluation.requirement_set,
        (old_record,),
        materially_changed_from_revision=rev1.lifecycle_candidate_revision_ref,
    )

    assert (
        rev2.lifecycle_candidate_revision_ref != rev1.lifecycle_candidate_revision_ref
    )
    assert readiness.ready is False
    assert readiness.reason_code == "review_record_invalidated"


@pytest.mark.parametrize(
    ("ref", "review_type", "effects", "reason_code"),
    [
        (
            "RV-N09",
            "domain_review",
            ("resolution_decision", "policy_permit", "publication"),
            "review_foreign_authority_effect_forbidden",
        ),
        (
            "RV-N10",
            "privacy_and_security_review",
            (),
            "reviewer_not_authorized",
        ),
    ],
)
def test_review_authority_boundaries(
    ref: str,
    review_type: str,
    effects: tuple[str, ...],
    reason_code: str,
) -> None:
    candidate, evaluation = _route(operation="add", privacy_triggered=True)
    assert evaluation.requirement_set is not None
    request = next(
        item
        for item in _requests(evaluation.requirement_set)
        if item.review_type == review_type
    )
    record = _record(
        request,
        reviewer_authority=(
            "project_owner_default_human"
            if review_type == "privacy_and_security_review"
            else None
        ),
        asserted_effects=effects,
    )
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert ref.startswith("RV-N")
    assert validation.disposition == "blocked"
    assert validation.reason_code == reason_code


def test_rv_n11_technical_conformance_is_not_independent_quality_review() -> None:
    candidate, evaluation = _route(operation="correct")
    assert evaluation.requirement_set is not None
    request = next(
        item
        for item in _requests(evaluation.requirement_set)
        if item.review_type == "independent_quality_review"
    )
    record = _record(
        request,
        reviewer_authority="technical_conformance_mechanism",
    )
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "blocked"
    assert validation.reason_code == "technical_conformance_not_independent_review"


def test_rv_n12_conflict_review_cannot_select_winner() -> None:
    candidate, evaluation = _route(operation="register_conflict")
    assert evaluation.requirement_set is not None
    request = next(
        item
        for item in _requests(evaluation.requirement_set)
        if item.review_type == "domain_review"
    )
    record = _record(request, selects_conflict_winner=True)
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "blocked"
    assert validation.reason_code == "conflict_review_cannot_select_winner"


def test_open_conditions_are_not_candidate_review_ready() -> None:
    candidate, evaluation = _route(operation="add")
    assert evaluation.requirement_set is not None
    requests = _requests(evaluation.requirement_set)
    records = []
    for request in requests:
        if request.review_type == "domain_review":
            records.append(
                _record(
                    request,
                    result="passed_with_conditions",
                    conditions=(
                        ReviewCondition(
                            condition_ref="COND-OPEN",
                            state="open",
                            evidence_refs=(),
                        ),
                    ),
                )
            )
        else:
            records.append(_record(request))
    readiness = ReviewOrchestrator().evaluate_readiness(
        evaluation.requirement_set,
        tuple(records),
    )

    assert readiness.ready is False
    assert readiness.reason_code == "review_conditions_unmet"
    assert "domain_review" in readiness.open_condition_review_types


def test_all_synthetic_records_can_prove_candidate_level_readiness_only() -> None:
    candidate, evaluation = _route(operation="correct", identity_relevant=True)
    assert evaluation.requirement_set is not None
    records = _valid_records(candidate, evaluation.requirement_set)
    readiness = ReviewOrchestrator().evaluate_readiness(
        evaluation.requirement_set,
        records,
    )

    assert readiness.ready is True
    assert readiness.reason_code == "candidate_review_requirements_satisfied"
    assert readiness.readiness_scope == "candidate_review_readiness"
    assert readiness.publication_package_review_readiness is False
    assert all(record.synthetic_test_fixture for record in records)


def test_explicit_carry_forward_requires_unchanged_scope_rule_basis_and_evidence() -> (
    None
):
    rev1, old_evaluation = _route(
        operation="add",
        candidate=_registered(revision_ref="CCR-REV-1"),
    )
    assert old_evaluation.requirement_set is not None
    old_request = _requests(old_evaluation.requirement_set)[0]
    old_record = _record(old_request)
    _, new_evaluation = _route(
        operation="add",
        candidate=_registered(revision_ref="CCR-REV-2"),
    )
    assert new_evaluation.requirement_set is not None
    target_requirement = next(
        item
        for item in new_evaluation.requirement_set.requirements
        if item.review_type == old_record.review_type
    )
    orchestrator = ReviewOrchestrator()
    accepted = orchestrator.evaluate_carry_forward(
        ReviewCarryForwardRequest(
            review_record=old_record,
            target_requirement=target_requirement,
            review_scope_unchanged=True,
            rule_basis_still_valid=True,
            evidence_refs=("CARRY-FORWARD-EVIDENCE",),
        )
    )
    no_evidence = orchestrator.evaluate_carry_forward(
        ReviewCarryForwardRequest(
            review_record=old_record,
            target_requirement=target_requirement,
            review_scope_unchanged=True,
            rule_basis_still_valid=True,
            evidence_refs=(),
        )
    )
    changed_scope = orchestrator.evaluate_carry_forward(
        ReviewCarryForwardRequest(
            review_record=old_record,
            target_requirement=target_requirement,
            review_scope_unchanged=False,
            rule_basis_still_valid=True,
            evidence_refs=("CARRY-FORWARD-EVIDENCE",),
        )
    )

    assert rev1.lifecycle_candidate_revision_ref != target_requirement.subject_version
    assert accepted.disposition == "accepted"
    assert accepted.record is not None
    assert accepted.record.creates_new_review_decision is False
    assert no_evidence.reason_code == "explicit_carry_forward_evidence_missing"
    assert changed_scope.reason_code == "review_scope_changed"


def test_waiver_requires_concrete_policy_authority() -> None:
    candidate, evaluation = _route(operation="add")
    assert evaluation.requirement_set is not None
    request = _requests(evaluation.requirement_set)[0]
    record = _record(request, result="waived_by_authorized_policy")
    validation = ReviewRecordValidator().validate(record, request, candidate)

    assert validation.disposition == "blocked"
    assert validation.reason_code == "authorized_policy_waiver_missing"


def test_review_outputs_contain_no_d6_objects_or_authority() -> None:
    candidate, evaluation = _route(operation="add")
    assert evaluation.requirement_set is not None
    records = _valid_records(candidate, evaluation.requirement_set)
    payload = (
        ReviewOrchestrator()
        .evaluate_readiness(
            evaluation.requirement_set,
            records,
        )
        .to_dict()
    )

    assert "publication_review" not in payload["review_states"]
    assert "policy_decision" not in payload
    assert "publication_change_set" not in payload
    assert "publication_unit" not in payload
    assert "g5" not in payload
    assert "g6" not in payload
