from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from cp_knowledge_tools.semantics import (
    ChangeCandidatePipeline,
    ChangeCandidateRequest,
    KnowledgeFinding,
    PriorKnowledgeState,
    SemanticChangeOperationPolicy,
    SemanticChangeProposal,
    SemanticTarget,
)

HR005_OPERATIONS = frozenset(
    {
        "add",
        "qualify",
        "temporal_progression",
        "constrain",
        "extend_scope",
        "register_conflict",
        "correct",
        "update_epistemic_state",
        "update_evidence_basis",
    }
)


def _pipeline(
    allowed: frozenset[str] = HR005_OPERATIONS,
) -> ChangeCandidatePipeline:
    return ChangeCandidatePipeline(
        SemanticChangeOperationPolicy.from_allowed(
            allowed,
            policy_ref="TEST-LOCAL-OPERATION-POLICY",
        )
    )


def _finding(
    *,
    ref: str = "FND-1",
    source_ref: str = "SOURCE-1",
    evidence_refs: tuple[str, ...] = ("EVIDENCE-1",),
    payload: dict[str, Any] | None = None,
    time_scope: tuple[str, ...] = (),
    epistemic_state: str | None = "observed",
    conflicts: tuple[str, ...] = (),
) -> KnowledgeFinding:
    return KnowledgeFinding(
        finding_ref=ref,
        finding_revision="0.1",
        task_ref="TEST-HR005-D4",
        source_continuation_result_ref="TEST-CONTINUATION-RESULT",
        source_ref=source_ref,
        subject_refs=("TEST-SUBJECT",),
        prior_state_ref="TEST-PRIOR",
        finding_type="conflict" if conflicts else "observation",
        description="synthetic material Finding",
        delta_class=("test",),
        semantic_observation=(
            payload
            if payload is not None
            else {"predicate": "pilot_status", "value": "actual"}
        ),
        evidence_refs=evidence_refs,
        time_scope=time_scope,
        epistemic_state=epistemic_state,
        uncertainty_or_conflict=conflicts,
        material_delta=True,
        material_delta_dimensions=("semantic",),
        non_canonical=True,
        event_time=None,
        producer_ref="TEST-PRODUCER",
        tool_or_model_ref="TEST-FINDING-EVALUATOR@0.1",
    )


def _proposal(
    *,
    operation: str = "add",
    effect: str = "add_pilot_status",
    payload: dict[str, Any] | None = None,
    **changes: Any,
) -> SemanticChangeProposal:
    return SemanticChangeProposal(
        semantic_change_operation=operation,
        proposed_semantic_effect=effect,
        proposed_semantic_payload=(
            payload
            if payload is not None
            else {"predicate": "pilot_status", "value": "actual"}
        ),
        **changes,
    )


def _request(
    *,
    findings: tuple[KnowledgeFinding, ...] | None = None,
    target: SemanticTarget | None = None,
    prior_state: PriorKnowledgeState | None = None,
    proposals: tuple[SemanticChangeProposal, ...] | None = None,
) -> ChangeCandidateRequest:
    return ChangeCandidateRequest(
        findings=findings if findings is not None else (_finding(),),
        semantic_target=(
            target if target is not None else SemanticTarget("claim", ("TEST-SUBJECT",))
        ),
        prior_state=(
            prior_state
            if prior_state is not None
            else PriorKnowledgeState(
                ("TEST-PRIOR",),
                "prior pilot status",
                {"predicate": "pilot_status", "value": "planned"},
            )
        ),
        proposals=proposals if proposals is not None else (_proposal(),),
    )


@pytest.mark.parametrize(
    ("ref", "operation", "effect", "payload"),
    [
        (
            "KF-D01",
            "temporal_progression",
            "planned_to_actual_same_event",
            {"event_ref": "EVT-INTERNAL-PILOT", "occurrence_state": "actual"},
        ),
        (
            "KF-D02",
            "add",
            "add_pilot_specific_engagement_teamwork_evaluation",
            {"predicate": "engagement_and_teamwork", "value": "strong"},
        ),
        (
            "KF-D03",
            "add",
            "add_mixed_coding_progression_evaluation",
            {"predicate": "coding_progression", "value": "mixed"},
        ),
        (
            "KF-D04",
            "add",
            "add_time_qualified_technical_operation_progression",
            {
                "predicate": "technical_operation",
                "value": "stable_after_first_session",
            },
        ),
        (
            "KF-D05",
            "add",
            "add_coupled_outcome_assessment",
            {
                "promising_after_school": True,
                "not_ready_for_classroom": True,
            },
        ),
        (
            "KF-D06",
            "temporal_progression",
            "add_follow_up_approval_state",
            {"predicate": "second_after_school_cycle", "value": "approved"},
        ),
        (
            "KF-D07",
            "temporal_progression",
            "add_time_bounded_classroom_follow_up_state",
            {
                "classroom_2024_25": "not_introduced",
                "classroom_long_term": "not_permanently_rejected",
            },
        ),
        (
            "KF-D08",
            "temporal_progression",
            "add_time_bounded_external_competition_follow_up_state",
            {
                "external_competition_2024_25": "not_planned",
                "external_competition_long_term": "not_permanently_excluded",
            },
        ),
        (
            "KF-D09",
            "add",
            "add_evaluation_occurrence_event",
            {
                "event_type": "pilot_evaluation",
                "occurrence": "completed_after_cycle",
            },
        ),
    ],
)
def test_nine_golden_findings_create_atomic_non_canonical_candidates(
    ref: str,
    operation: str,
    effect: str,
    payload: dict[str, Any],
) -> None:
    finding = _finding(ref=ref, payload=payload)
    request = _request(
        findings=(finding,),
        proposals=(_proposal(operation=operation, effect=effect, payload=payload),),
    )

    result = _pipeline().evaluate(request)

    assert result.disposition == "candidates"
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.non_canonical is True
    assert candidate.identity_scope == "implementation_local_non_canonical"
    assert candidate.semantic_change_operation == operation
    assert candidate.proposed_semantic_effect == effect
    assert candidate.source_finding_refs == (ref,)
    assert candidate.evidence_refs == ("EVIDENCE-1",)
    assert candidate.to_dict()["primary_operation_count"] == 1


def test_operation_vocabulary_is_caller_supplied_not_system_wide() -> None:
    proposal = _proposal(operation="context_specific_operation")
    accepted = _pipeline(frozenset({"context_specific_operation"})).evaluate(
        _request(proposals=(proposal,))
    )
    rejected = _pipeline(frozenset({"another_operation"})).evaluate(
        _request(proposals=(proposal,))
    )

    assert accepted.disposition == "candidates"
    assert rejected.disposition == "blocked"
    assert rejected.reason_code == "semantic_change_operation_not_allowed"


def test_cc_n01_ambiguous_target_retains_finding_without_candidate() -> None:
    result = _pipeline().evaluate(
        _request(target=SemanticTarget("claim", ("A", "B"), resolution="ambiguous"))
    )

    assert result.disposition == "no_change_candidate_yet"
    assert result.reason_code == "target_not_determinable"
    assert result.candidates == ()


def test_cc_n02_missing_prior_state_retains_finding_without_candidate() -> None:
    request = _request()
    request = ChangeCandidateRequest(
        findings=request.findings,
        semantic_target=request.semantic_target,
        prior_state=None,
        proposals=request.proposals,
    )

    result = _pipeline().evaluate(request)

    assert result.disposition == "no_change_candidate_yet"
    assert result.reason_code == "relevant_prior_state_not_determinable"


def test_cc_n03_ungrounded_payload_is_blocked() -> None:
    result = _pipeline().evaluate(
        _request(
            proposals=(
                _proposal(payload={"predicate": "pilot_status", "value": "invented"}),
            )
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "proposed_change_exceeds_finding_or_evidence"


def test_cc_n04_approved_cannot_become_performed_or_repeated() -> None:
    payload = {"predicate": "second_after_school_cycle", "value": "approved"}
    result = _pipeline().evaluate(
        _request(
            findings=(_finding(payload=payload),),
            proposals=(
                _proposal(
                    operation="temporal_progression",
                    payload=payload,
                    prohibited_inferences=("performed", "repeated"),
                    attempted_inferences=("performed",),
                ),
            ),
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "approved_state_overreach"


@pytest.mark.parametrize("attempted", ["permanently_rejected", "permanently_excluded"])
def test_cc_n05_time_bounded_state_cannot_become_permanent(
    attempted: str,
) -> None:
    result = _pipeline().evaluate(
        _request(
            proposals=(
                _proposal(
                    prohibited_inferences=(attempted,),
                    attempted_inferences=(attempted,),
                ),
            )
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "time_bounded_state_overreach"


def test_cc_n06_conflict_cannot_overwrite_existing_assertion() -> None:
    result = _pipeline().evaluate(
        _request(
            proposals=(
                _proposal(
                    operation="register_conflict",
                    overwrites_existing_assertion=True,
                ),
            )
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "conflict_overwrite_requires_resolution"


def test_cc_n07_candidate_cannot_make_identity_decision() -> None:
    result = _pipeline().evaluate(
        _request(
            proposals=(_proposal(identity_decisions=("revise_existing_identity",)),)
        )
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "same_object_or_identity_resolution_preempted"


def test_cc_n08_candidate_cannot_emit_foreign_authority_output() -> None:
    result = _pipeline().evaluate(
        _request(proposals=(_proposal(foreign_authority_outputs=("policy_permit",)),))
    )

    assert result.disposition == "blocked"
    assert result.reason_code == "foreign_authority_output_preempted"


def test_cc_n09_unclear_effect_retains_finding_without_candidate() -> None:
    result = _pipeline().evaluate(
        _request(proposals=(_proposal(effect_is_bounded=False),))
    )

    assert result.disposition == "no_change_candidate_yet"
    assert result.reason_code == "semantic_effect_not_determinable"


@pytest.mark.parametrize(
    ("operation", "reason_code"),
    [
        ("supersede_version", "wrong_layer_publication_or_lifecycle_operation"),
        ("merge", "wrong_layer_resolution_operation"),
        ("split", "wrong_layer_resolution_operation"),
        ("publish_new_version", "wrong_layer_publication_change_set_operation"),
        ("approve", "foreign_review_or_policy_authority_operation"),
        ("reject", "foreign_review_or_policy_authority_operation"),
        ("permit", "foreign_review_or_policy_authority_operation"),
        ("deny", "foreign_review_or_policy_authority_operation"),
    ],
)
def test_cc_n10_through_n13_foreign_layer_operations_are_blocked(
    operation: str,
    reason_code: str,
) -> None:
    result = _pipeline(HR005_OPERATIONS | {operation}).evaluate(
        _request(proposals=(_proposal(operation=operation),))
    )

    assert result.disposition == "blocked"
    assert result.reason_code == reason_code


def test_cc_n14_independent_operations_split_into_atomic_candidates() -> None:
    payload = {"engagement": "strong", "coding": "mixed"}
    result = _pipeline().evaluate(
        _request(
            findings=(_finding(payload=payload),),
            proposals=(
                _proposal(
                    effect="add_engagement_evaluation",
                    payload={"engagement": "strong"},
                ),
                _proposal(
                    effect="add_coding_evaluation",
                    payload={"coding": "mixed"},
                ),
            ),
        )
    )

    assert result.disposition == "candidates"
    assert result.reason_code == "split_into_atomic_candidates"
    assert len(result.candidates) == 2
    assert all(
        candidate.to_dict()["primary_operation_count"] == 1
        for candidate in result.candidates
    )


def test_same_run_same_evidence_same_delta_is_deduplicated() -> None:
    request = _request()

    result = _pipeline().evaluate_many((request, request))

    assert result.disposition == "candidates"
    assert result.reason_code == "provenance_preserving_semantic_deduplication"
    assert len(result.candidates) == 1
    assert result.candidates[0].evidence_refs == ("EVIDENCE-1",)


def test_independent_evidence_preserved_on_shared_semantic_candidate() -> None:
    payload = {"predicate": "second_cycle", "value": "approved"}
    first = _request(
        findings=(
            _finding(
                ref="FND-A",
                source_ref="SOURCE-A",
                evidence_refs=("EVIDENCE-A",),
                payload=payload,
            ),
        ),
        proposals=(
            _proposal(
                operation="update_evidence_basis",
                effect="update_second_cycle_evidence_basis",
                payload=payload,
            ),
        ),
    )
    second = _request(
        findings=(
            _finding(
                ref="FND-B",
                source_ref="SOURCE-B",
                evidence_refs=("EVIDENCE-B",),
                payload=payload,
            ),
        ),
        proposals=first.proposals,
    )

    result = _pipeline().evaluate_many((first, second))

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.source_finding_refs == ("FND-A", "FND-B")
    assert candidate.source_refs == ("SOURCE-A", "SOURCE-B")
    assert candidate.evidence_refs == ("EVIDENCE-A", "EVIDENCE-B")


def test_conflict_candidate_preserves_prior_and_incoming_evidence() -> None:
    payload = {"predicate": "technical_operation", "value": "intermittent"}
    finding = _finding(
        ref="FND-CONFLICT",
        source_ref="SOURCE-NEW",
        evidence_refs=("EVIDENCE-NEW",),
        payload=payload,
        conflicts=("support_vs_conflict",),
    )
    request = _request(
        findings=(finding,),
        prior_state=PriorKnowledgeState(
            ("PRIOR-TECHNICAL-STABILITY",),
            "technical operation was stable",
            source_refs=("SOURCE-PRIOR",),
            evidence_refs=("EVIDENCE-PRIOR",),
        ),
        proposals=(
            _proposal(
                operation="register_conflict",
                effect="register_technical_operation_conflict",
                payload=payload,
                conflict_treatment=("support_vs_conflict",),
                preservation_constraints=(
                    "preserve_prior_assertion",
                    "preserve_conflicting_assertion",
                ),
            ),
        ),
    )

    candidate = _pipeline().evaluate(request).candidates[0]

    assert candidate.source_refs == ("SOURCE-NEW", "SOURCE-PRIOR")
    assert candidate.evidence_refs == ("EVIDENCE-NEW", "EVIDENCE-PRIOR")
    assert candidate.known_conflicts == ("support_vs_conflict",)


def test_unknown_event_time_is_preserved_in_candidate_revision() -> None:
    finding = _finding(payload={"event_type": "evaluation", "occurrence": "completed"})
    candidate = (
        _pipeline()
        .evaluate(
            _request(
                findings=(finding,),
                proposals=(
                    _proposal(
                        effect="add_evaluation_occurrence",
                        payload=finding.semantic_observation,
                        preservation_constraints=("preserve_unknown_exact_event_time",),
                    ),
                ),
            )
        )
        .candidates[0]
    )

    assert candidate.event_time_values == ()
    assert candidate.event_time_unknown is True
    assert candidate.to_dict()["time"] == {
        "event_time_values": [],
        "event_time_unknown": True,
    }


@pytest.mark.parametrize(
    "changed_proposal",
    [
        _proposal(time_scope=("later",)),
        _proposal(conflict_treatment=("conflict",)),
        _proposal(epistemic_context="reported"),
        _proposal(effect="different_effect"),
        _proposal(relevant_constraints=("different_constraint",)),
    ],
)
def test_candidates_are_not_deduplicated_across_material_boundaries(
    changed_proposal: SemanticChangeProposal,
) -> None:
    first = _request()
    second = _request(proposals=(changed_proposal,))

    result = _pipeline().evaluate_many((first, second))

    assert result.disposition == "candidates"
    assert len(result.candidates) == 2


def test_candidate_revision_is_deeply_immutable_and_ids_are_distinct() -> None:
    candidate = _pipeline().evaluate(_request()).candidates[0]

    with pytest.raises(FrozenInstanceError):
        candidate.semantic_change_operation = "qualify"  # type: ignore[misc]

    detached_payload = candidate.proposed_semantic_payload
    detached_payload["value"] = "mutated"

    assert candidate.proposed_semantic_payload["value"] == "actual"
    assert candidate.change_candidate_ref != candidate.candidate_revision_ref
    assert candidate.change_candidate_ref.startswith("CCL-")
    assert candidate.candidate_revision_ref.startswith("CCR-")


def test_identical_input_is_deterministic() -> None:
    request = _request()

    first = _pipeline().evaluate(request).candidates[0]
    second = _pipeline().evaluate(request).candidates[0]

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_new_independent_evidence_changes_revision_not_candidate_identity() -> None:
    payload = {"predicate": "pilot_status", "value": "actual"}
    first_request = _request(
        findings=(
            _finding(ref="FND-A", evidence_refs=("EVIDENCE-A",), payload=payload),
        ),
        proposals=(_proposal(payload=payload),),
    )
    second_request = _request(
        findings=(
            _finding(ref="FND-B", evidence_refs=("EVIDENCE-B",), payload=payload),
        ),
        proposals=first_request.proposals,
    )

    first = _pipeline().evaluate(first_request).candidates[0]
    combined = _pipeline().evaluate_many((first_request, second_request)).candidates[0]

    assert first.change_candidate_ref == combined.change_candidate_ref
    assert first.candidate_revision_ref != combined.candidate_revision_ref
    assert first.candidate_revision != combined.candidate_revision


def test_candidate_output_contains_no_d5_authority_or_records() -> None:
    payload = _pipeline().evaluate(_request()).candidates[0].to_dict()

    assert {
        "candidate_kind",
        "processing_state",
        "resolution_ref",
        "resolution_type",
        "resolution_decision",
        "review_requirement_set",
        "review_record",
        "policy_decision",
        "publication_request",
        "publication_change_set",
        "publication_record",
    }.isdisjoint(payload)
    assert payload["identity_context"] == {"unresolved_identity_questions": []}
