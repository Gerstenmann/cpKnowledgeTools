from __future__ import annotations

from copy import deepcopy
from typing import Any

from cp_knowledge_tools.derived import (
    ExperienceContinuationPlan,
    ExperienceGapPlan,
    ExperiencePhasePlan,
    ExperienceProjectionBuilder,
    ExperienceProjectionPlan,
    ExperienceReuseContext,
    ExperienceSemanticSelector,
    ExperienceThreadPlan,
)


def _ref(subject_type: str, stable_id: str) -> dict[str, str]:
    return {
        "subject_type": subject_type,
        "stable_id": stable_id,
        "version": "0.1",
        "authority_context": "Semantic Core",
    }


def _claim(stable_id: str, predicate: str, value: str) -> dict[str, Any]:
    return {
        "claim_ref": _ref("claim", stable_id),
        "statement": {
            "subject_ref": _ref("entity", "ENT-FOCUS"),
            "predicate_ref": predicate,
            "object": {
                "kind": "literal",
                "reference": None,
                "value": value,
                "datatype": "str",
                "language": "en",
            },
        },
        "epistemic_status": "confirmed",
        "time": [],
        "evidence_link_ids": [f"EL-{stable_id}"],
    }


def _event(stable_id: str, event_type: str, modality: str) -> dict[str, Any]:
    return {
        "event_ref": _ref("event", stable_id),
        "event_type_ref": event_type,
        "label": stable_id,
        "time": [{"modality": modality, "start": None}],
        "evidence_link_ids": [f"EL-{stable_id}"],
    }


def _manifest() -> dict[str, Any]:
    claims = [
        _claim("CLM-CONTEXT", "test.context", "known"),
        _claim("CLM-SCOPE-OPEN", "test.scope_state", "open"),
        _claim("CLM-SCOPE", "test.scope", "limited"),
        _claim("CLM-DEFERRED", "test.followup_state", "deferred"),
        _claim("CLM-DEPENDENCY", "test.dependency", "requires_evaluation"),
        _claim("CLM-COMP-FUTURE", "test.competition_future", "possible"),
        _claim("CLM-COMP-NO", "test.competition_approval", "not_approved"),
        _claim("CLM-COMP-DEP", "test.competition_dependency", "evaluation"),
    ]
    events = [
        _event("EVT-PROPOSAL", "test.event.proposal", "actual"),
        _event("EVT-DECISION", "test.event.decision", "actual"),
        _event("EVT-EXECUTION", "test.event.execution", "planned"),
    ]
    participations = [
        {
            "participation_ref": _ref("event_participation", "PART-INITIATOR"),
            "event_ref": _ref("event", "EVT-PROPOSAL"),
            "entity_ref": _ref("entity", "ENT-ACTOR"),
            "role": "test.role.initiator",
            "time": [],
            "evidence_link_ids": ["EL-PART-INITIATOR"],
        }
    ]
    evidence_links = [
        {
            "evidence_link_id": f"EL-{stable_id}",
            "subject_ref": _ref(subject_type, stable_id),
            "evidence_address_ref": _ref(
                "evidence_address", f"EA-{stable_id}"
            ),
            "role": "supports",
        }
        for subject_type, stable_id in [
            *(('claim', item["claim_ref"]["stable_id"]) for item in claims),
            *(('event', item["event_ref"]["stable_id"]) for item in events),
            ("event_participation", "PART-INITIATOR"),
        ]
    ]
    return {
        "knowledge_object_id": "KO-TEST",
        "knowledge_object_version": "0.1",
        "claims": claims,
        "events": events,
        "event_participations": participations,
        "evidence_links": evidence_links,
    }


def _plan() -> ExperienceProjectionPlan:
    selector = ExperienceSemanticSelector
    return ExperienceProjectionPlan(
        experience_ref="EXP-TEST",
        focus_knowledge_object_ref="KO-TEST@0.1",
        as_of="2024-09-06T15:30:00+02:00",
        phases=(
            ExperiencePhasePlan("context", (selector("claim", "CLM-CONTEXT"),)),
            ExperiencePhasePlan(
                "intent",
                (selector("event", event_type_ref="test.event.proposal"),),
            ),
            ExperiencePhasePlan(
                "proposal",
                (
                    selector(
                        "event_participation",
                        participation_role="test.role.initiator",
                        event_type_ref="test.event.proposal",
                        time_modality="actual",
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "decision",
                (
                    selector(
                        "event",
                        event_type_ref="test.event.decision",
                        time_modality="actual",
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "scope",
                (
                    selector("claim", "CLM-SCOPE-OPEN"),
                    selector("claim", "CLM-SCOPE"),
                    selector("claim", "CLM-DEFERRED"),
                    selector("claim", "CLM-DEPENDENCY"),
                ),
            ),
            ExperiencePhasePlan(
                "execution",
                (
                    selector(
                        "event",
                        event_type_ref="test.event.execution",
                        time_modality="actual",
                    ),
                ),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "evaluation",
                (selector("event", event_type_ref="test.event.evaluation"),),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "outcome",
                (selector("claim", claim_predicate_ref="test.outcome"),),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "follow_up",
                (selector("claim", claim_predicate_ref="test.follow_up"),),
            ),
        ),
        threads=(
            ExperienceThreadPlan(
                "scope",
                (
                    "CLM-SCOPE-OPEN",
                    "CLM-SCOPE",
                    "CLM-DEFERRED",
                    "CLM-DEPENDENCY",
                ),
            ),
            ExperienceThreadPlan(
                "competition",
                ("CLM-COMP-FUTURE", "CLM-COMP-NO", "CLM-COMP-DEP"),
            ),
        ),
        gaps=(
            ExperienceGapPlan(
                "GAP-EXECUTION",
                "Did it occur?",
                "execution",
                ("EVT-EXECUTION",),
            ),
            ExperienceGapPlan(
                "GAP-EVALUATION-OCCURRENCE",
                "Was it evaluated?",
                "evaluation",
                ("CLM-DEPENDENCY",),
            ),
            ExperienceGapPlan(
                "GAP-EVALUATION-RESULT",
                "What was the result?",
                "evaluation",
                ("CLM-DEPENDENCY",),
            ),
            ExperienceGapPlan(
                "GAP-OUTCOME",
                "What was the outcome?",
                "outcome",
                ("CLM-DEPENDENCY",),
            ),
            ExperienceGapPlan(
                "GAP-FOLLOWUP-A",
                "What followed?",
                "follow_up",
                ("CLM-DEFERRED", "CLM-DEPENDENCY"),
            ),
            ExperienceGapPlan(
                "GAP-FOLLOWUP-B",
                "What followed?",
                "follow_up",
                ("CLM-COMP-DEP",),
            ),
            ExperienceGapPlan(
                "GAP-REPETITION",
                "Was it repeated?",
                "follow_up",
                ("EVT-EXECUTION",),
            ),
        ),
        reuse_context=ExperienceReuseContext(
            domain_terms=("education", "school", "school"),
            topic_terms=("pilot", "topic"),
            purpose_terms=("reuse",),
        ),
        continuation=ExperienceContinuationPlan(
            continuation_ref="CONT-01",
            critical_gap_refs=(
                "GAP-EXECUTION",
                "GAP-EVALUATION-OCCURRENCE",
                "GAP-EVALUATION-RESULT",
                "GAP-OUTCOME",
                "GAP-FOLLOWUP-A",
            ),
            search_after="2024-09-06T15:30:00+02:00",
            trigger_purposes=("reuse", "lesson", "reuse"),
        ),
    )


def test_phases_gaps_threads_and_lesson_gate_follow_semantic_support() -> None:
    projection = ExperienceProjectionBuilder().build(_manifest(), _plan())
    phase_states = {item.phase_ref: item.status for item in projection.phases}

    assert phase_states == {
        "context": "supported",
        "intent": "supported",
        "proposal": "supported",
        "decision": "supported",
        "scope": "supported",
        "execution": "unresolved",
        "evaluation": "unresolved",
        "outcome": "unresolved",
        "follow_up": "unresolved",
    }
    assert projection.experience_completeness == "partial"
    assert projection.lesson_learned_eligibility == "insufficient_evidence"
    assert projection.lesson_learned_candidates == ()
    assert len(projection.gaps) == 7
    assert {item.status for item in projection.gaps} == {"unresolved"}
    assert all(item.phase_ref for item in projection.gaps)
    assert projection.threads[0].semantic_refs == (
        "CLM-SCOPE-OPEN",
        "CLM-SCOPE",
        "CLM-DEFERRED",
        "CLM-DEPENDENCY",
    )
    assert projection.continuation_requirements[0].status == (
        "required_for_reusable_experience"
    )


def test_planned_event_does_not_support_actual_execution_or_imply_outcome() -> None:
    projection = ExperienceProjectionBuilder().build(_manifest(), _plan())
    phases = {item.phase_ref: item for item in projection.phases}

    assert phases["execution"].status == "unresolved"
    assert phases["evaluation"].status == "unresolved"
    assert phases["outcome"].status == "unresolved"
    assert all("failed" not in item.question.lower() for item in projection.gaps)


def test_builder_is_deterministic_order_independent_and_does_not_mutate_input() -> None:
    manifest_a = _manifest()
    manifest_before = deepcopy(manifest_a)
    manifest_b = deepcopy(manifest_a)
    for key in ("claims", "events", "event_participations", "evidence_links"):
        manifest_b[key].reverse()

    projection_a = ExperienceProjectionBuilder().build(manifest_a, _plan())
    projection_b = ExperienceProjectionBuilder().build(manifest_b, _plan())

    assert manifest_a == manifest_before
    assert projection_a.semantic_hash == projection_b.semantic_hash
    assert projection_a.experience_projection_ref == (
        projection_b.experience_projection_ref
    )
    assert projection_a.reuse_context.domain_terms == ("education", "school")
    assert projection_a.reuse_context.topic_terms == ("pilot", "topic")
