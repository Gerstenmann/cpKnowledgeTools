"""Source-neutral composition entry point for Post-R5 hardening capabilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from cp_knowledge_tools.delivery.hardening import (
    CurrentnessContext,
    DeliveryClaimProjector,
)
from cp_knowledge_tools.lifecycle.enrichment import (
    HumanEnrichmentOpportunity,
    HumanEnrichmentQueue,
    LessonLearnedLifecycle,
)
from cp_knowledge_tools.platform.hashing import stable_token
from cp_knowledge_tools.semantics.hardening import (
    ConflictCompatibilityAssessment,
    EvidenceAssessment,
    TemporalConstraint,
)
from cp_knowledge_tools.semantics.source_backed import (
    SourceBackedSemanticInterpreter,
    source_accounting,
)
from cp_knowledge_tools.sources.human_interaction import (
    HumanSourceContext,
    capture_human_interaction_source,
)
from cp_knowledge_tools.sources.models import EvidenceAddress, SourceRecord


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Post-R5 input {field!r} must be an object")
    return value


def run_post_r5_hardening(
    *,
    semantic_state: Mapping[str, Any],
    human_enrichment_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize the bounded Post-R5 state through production domain services."""

    perspective = _mapping(
        semantic_state.get("perspective_qualification"),
        "perspective_qualification",
    )
    claim_a = _mapping(perspective.get("claim_a"), "claim_a")
    claim_b = _mapping(perspective.get("claim_b"), "claim_b")
    conflict = ConflictCompatibilityAssessment.from_mapping(
        {
            "assessment_ref": perspective.get("conflict_set_ref"),
            "claim_refs": [claim_a.get("claim_ref"), claim_b.get("claim_ref")],
            "checks": perspective.get("compatibility_checks"),
            "remaining_material_incompatibility": (
                perspective.get("conflict_classification") == "hard_conflict"
            ),
            "outcome": perspective.get("conflict_classification"),
        }
    )
    conflict_set = {
        "conflict_set_id": perspective.get("conflict_set_ref"),
        "claim_refs": list(conflict.claim_refs),
        **conflict.to_canonical_conflict_fields(),
    }

    temporal = TemporalConstraint.from_mapping(
        _mapping(semantic_state.get("temporal_constraint"), "temporal_constraint")
    )
    evidence_assessment = EvidenceAssessment.from_mapping(
        _mapping(semantic_state.get("evidence_assessment"), "evidence_assessment")
    )

    currentness = _mapping(semantic_state.get("currentness"), "currentness")
    current = DeliveryClaimProjector().project_current_opportunity(
        historical_claim_ref=currentness.get("historical_claim_ref"),
        purpose=currentness.get("purpose"),
        currentness=CurrentnessContext(
            status=currentness.get("currentness"),
            evidence_refs=tuple(currentness.get("current_evidence_refs", ())),
        ),
        policy_profile_conformant=True,
    )
    correction = _mapping(
        semantic_state.get("correction_history"), "correction_history"
    )
    delivery = DeliveryClaimProjector().claim_view(
        primary_claim_ref=correction.get("primary_claim_ref"),
        correction_history_refs=(correction.get("historical_claim_ref"),),
    )

    queue = HumanEnrichmentQueue()
    opportunities = tuple(
        HumanEnrichmentOpportunity.from_mapping(item)
        for item in human_enrichment_state.get("opportunities", ())
    )
    requests = tuple(
        request
        for opportunity in opportunities
        if (request := queue.persist_request(opportunity)) is not None
    )

    interaction = deepcopy(
        dict(_mapping(human_enrichment_state.get("interaction"), "interaction"))
    )
    source_context = HumanSourceContext.from_mapping(
        _mapping(interaction.pop("source_context", None), "source_context")
    )
    source_record = capture_human_interaction_source(
        **interaction,
        source_context=source_context,
    )

    lesson = _mapping(
        human_enrichment_state.get("lesson_learned_candidate"),
        "lesson_learned_candidate",
    )
    lifecycle = LessonLearnedLifecycle()
    candidate = lifecycle.create_candidate(
        experience_ref=lesson.get("experience_ref"),
        eligibility=lesson.get("eligibility"),
        semantic_payload_ref=lesson.get("semantic_payload_ref"),
        source_and_evidence_refs=tuple(lesson.get("source_and_evidence_refs", ())),
    )
    if candidate is None:
        raise ValueError("Post-R5 Lesson-Learned Candidate is not eligible")
    revised = lifecycle.revise_candidate(
        candidate,
        disposition=lesson.get("review_disposition"),
        human_interaction_source_record_ref=(
            source_record.human_interaction_source_record_ref
        ),
        new_semantic_payload_ref=lesson.get("revised_semantic_payload_ref"),
    )

    return {
        "source_neutral_entry_point": (
            "cp_knowledge_tools.post_r5.run_post_r5_hardening"
        ),
        "conflict_sets": [conflict_set],
        "temporal_constraints": [temporal.to_dict()],
        "evidence_assessments": [evidence_assessment.to_dict()],
        "delivery": {
            "current_opportunity": asdict(current) if current is not None else None,
            "primary_claim_ref": delivery.primary_claim_ref,
            "correction_history_refs": list(delivery.correction_history_refs),
        },
        "human_enrichment": {
            "opportunities": [item.to_dict() for item in opportunities],
            "requests": [item.to_dict() for item in requests],
            "persisted_request_refs": [
                item.human_enrichment_request_ref for item in requests
            ],
        },
        "human_source_record": source_record.to_dict(),
        "lesson_learned_candidate": {
            "candidate_ref": revised.candidate_ref,
            "experience_ref": revised.experience_ref,
            "accepted": revised.accepted,
            "published": revised.published,
            "current_revision": {
                "revision_ref": revised.current_revision.revision_ref,
                "revision": revised.current_revision.revision,
                "predecessor_revision_ref": (
                    revised.current_revision.predecessor_revision_ref
                ),
                "semantic_payload_ref": revised.current_revision.semantic_payload_ref,
                "source_and_evidence_refs": list(
                    revised.current_revision.source_and_evidence_refs
                ),
                "human_source_record_refs": list(
                    revised.current_revision.human_source_record_refs
                ),
            },
        },
    }


def run_source_backed_post_r5(
    *,
    source_records: Iterable[SourceRecord],
    evidence_addresses: Iterable[EvidenceAddress],
    as_of: str,
    requested_owner_ref: str,
    requested_owner_label: str,
) -> dict[str, Any]:
    """Compose a Post-R5 Frontier and KPR decision from documentary Sources."""

    records = tuple(source_records)
    addresses = tuple(evidence_addresses)
    interpretation = SourceBackedSemanticInterpreter().interpret(
        records,
        addresses,
        as_of=as_of,
    )
    knowledge = interpretation["knowledge"]
    frontier = interpretation["knowledge_frontier"]
    owner_appears_in_dossier = any(
        requested_owner_label.casefold() in record.normalized_text.casefold()
        for record in records
    )
    if not owner_appears_in_dossier:
        raise ValueError(
            "Human Enrichment Opportunity lacks source-backed owner relevance"
        )

    program = knowledge["program_context"]
    frontier_ref = frontier["knowledge_frontier_ref"]
    purpose = "noncontinuation_reason_assessment"
    opportunity = HumanEnrichmentOpportunity(
        opportunity_ref=stable_token("HEO", frontier_ref, purpose),
        trigger_ref=frontier_ref,
        trigger_class="knowledge_frontier_with_likely_owner_knowledge",
        purpose=purpose,
        why_owner=(
            "The requested owner appears in the bounded source correspondence and "
            "may remember a later decision that the documentary dossier does not "
            "contain."
        ),
        expected_information_gain=(
            "Establish whether a specific later decision or blocker explains the "
            "unresolved non-continuation Frontier."
        ),
        expected_decision_or_reuse_value=(
            "Prevent technical, ownership, interest, or staffing factors from being "
            "reused as an unsupported causal explanation."
        ),
        priority="P1",
        dedupe_key=stable_token("DEDUP", frontier_ref, purpose),
        frontier_lineage_refs=(frontier_ref,),
        evidence_checked_refs=tuple(frontier["evidence_checked_refs"]),
        candidate_ref=None,
        candidate_revision_ref=None,
        target_knowledge_refs=(
            program["program_ref"],
            program["pilot_cycle_ref"],
        ),
        related_experience_refs=(
            stable_token("EXP", program["pilot_cycle_ref"], "programme_frontier"),
        ),
        knowledge_frontier_ref=frontier_ref,
        remaining_gap=frontier["remaining_gap"],
        created_at=as_of,
        route_to="Knowledge Lifecycle and Curation",
        requested_owner_ref=requested_owner_ref,
        proposed_owner_question=(
            "Do you remember whether there was a specific decision or blocker "
            f"after the {program['pilot_cycle_label']} that explains why the "
            f"{program['program_label']} was not continued?"
        ),
        priority_rationale=(
            "The unresolved causal gap materially affects faithful future reuse of "
            "the programme history."
        ),
        frontier_descriptor=frontier["remaining_gap"],
        completion_criteria=(
            "bounded_answer_recorded_as_new_human_interaction_source",
        ),
        trigger_stage="post_r5_source_backed_interpretation",
        mode="regular",
        gain_justifies_human_cost=True,
        evidence_sufficient=False,
    )
    request = HumanEnrichmentQueue().persist_request(opportunity)
    if request is None:
        raise ValueError("KPR did not persist the eligible source-backed Opportunity")
    opportunity_payload = opportunity.to_dict()
    opportunity_payload["derived_from_frontier"] = True
    return {
        "source_neutral_entry_point": (
            "cp_knowledge_tools.post_r5.run_source_backed_post_r5"
        ),
        "source_processing_path": [
            "local_html_adapter",
            "immutable_source_record",
            "passage_evidence_addressing",
            "source_backed_semantic_interpretation",
            "knowledge_frontier_derivation",
            "agent_interaction_opportunity",
            "kpr_eligibility",
        ],
        "source_accounting": source_accounting(records, addresses),
        "knowledge": knowledge,
        "knowledge_frontier": frontier,
        "human_enrichment": {
            "opportunity": opportunity_payload,
            "opportunity_is_request": False,
            "kpr_eligibility": {
                "eligible": opportunity.eligible_for_request,
                "frontier_concrete": bool(frontier_ref),
                "evidence_checked": bool(frontier["evidence_checked_refs"]),
                "question_not_answerable_from_sources": True,
                "owner_relevance_source_backed": owner_appears_in_dossier,
                "information_gain_material": True,
                "decision_or_reuse_value_material": True,
                "question_narrow": True,
                "human_cost_justified": opportunity.gain_justifies_human_cost,
            },
            "kpr_disposition": "request_queued",
            "request": request.to_dict(),
            "human_response_present": False,
        },
    }
