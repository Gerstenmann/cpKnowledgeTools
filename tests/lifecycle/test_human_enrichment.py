from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from cp_knowledge_tools.lifecycle.enrichment import (
    HumanEnrichmentOpportunity,
    HumanEnrichmentQueue,
    LessonLearnedLifecycle,
)


def _opportunity(
    ref: str,
    *,
    priority: str = "P1",
    dedupe_key: str | None = None,
    evidence_sufficient: bool = False,
) -> HumanEnrichmentOpportunity:
    return HumanEnrichmentOpportunity(
        opportunity_ref=ref,
        trigger_ref=f"KF-{ref}",
        trigger_class="currentness_gap",
        purpose="currentness_assessment",
        why_owner="Synthetic owner may have unique knowledge.",
        expected_information_gain="Material currentness clarification.",
        expected_decision_or_reuse_value="Avoid a false current lead.",
        priority=priority,
        dedupe_key=dedupe_key or ref,
        frontier_lineage_refs=(f"KF-{ref}",),
        evidence_checked_refs=("EL-CHECKED",),
        candidate_ref="LLC-SYNTHETIC-01",
        candidate_revision_ref="LLC-SYNTHETIC-01@1",
        target_knowledge_refs=("KO-SYNTHETIC-01@1",),
        related_experience_refs=("EXP-SYNTHETIC-01",),
        knowledge_frontier_ref=f"KF-{ref}",
        remaining_gap="The current state remains unresolved.",
        created_at="2026-08-20T09:00:00+02:00",
        route_to="Knowledge Lifecycle and Curation",
        requested_owner_ref="HUMAN-SYNTHETIC-OWNER",
        proposed_owner_question="What is the current bounded state?",
        priority_rationale="Currentness materially affects reuse.",
        frontier_descriptor="Currentness remains unverified.",
        completion_criteria=("currentness_answer_recorded",),
        trigger_stage="post_r5_hardening",
        mode="regular",
        gain_justifies_human_cost=True,
        evidence_sufficient=evidence_sufficient,
    )


def test_heq_01_and_07_opportunity_is_not_request_and_kpr_checks_eligibility() -> None:
    queue = HumanEnrichmentQueue()

    sufficient = queue.persist_request(
        _opportunity("SUFFICIENT", evidence_sufficient=True)
    )
    eligible = queue.persist_request(_opportunity("ELIGIBLE"))

    assert sufficient is None
    assert eligible is not None
    assert eligible.human_enrichment_request_ref != eligible.opportunity_ref
    assert eligible.blocking is False


@pytest.mark.parametrize(
    "missing_field",
    [
        "why_owner",
        "expected_information_gain",
        "expected_decision_or_reuse_value",
        "evidence_checked_refs",
        "frontier_lineage_refs",
    ],
)
def test_neg14_incomplete_kpr_eligibility_cannot_persist(
    missing_field: str,
) -> None:
    payload = {
        "opportunity_ref": "HEO-INCOMPLETE",
        "trigger_ref": "KF-INCOMPLETE",
        "trigger_class": "currentness_gap",
        "purpose": "currentness_assessment",
        "why_owner": "The requested owner observed the current state.",
        "expected_information_gain": "Resolve a material currentness gap.",
        "expected_decision_or_reuse_value": "Prevent reuse of a stale lead.",
        "priority": "P1",
        "dedupe_key": "incomplete",
        "frontier_lineage_refs": ["KF-INCOMPLETE"],
        "evidence_checked_refs": ["EL-HISTORICAL"],
        "evidence_sufficient": False,
        "candidate_ref": "LLC-SYNTHETIC-01",
        "candidate_revision_ref": "LLC-SYNTHETIC-01@1",
        "target_knowledge_refs": ["KO-SYNTHETIC-01@1"],
        "related_experience_refs": ["EXP-SYNTHETIC-01"],
        "knowledge_frontier_ref": "KF-INCOMPLETE",
        "remaining_gap": "The current state remains unresolved.",
        "created_at": "2026-08-20T09:00:00+02:00",
        "route_to": "Knowledge Lifecycle and Curation",
        "requested_owner_ref": "HUMAN-SYNTHETIC-OWNER",
        "proposed_owner_question": "What is the current bounded state?",
        "priority_rationale": "Currentness materially affects reuse.",
        "frontier_descriptor": "Currentness remains unverified.",
        "completion_criteria": ["currentness_answer_recorded"],
        "trigger_stage": "post_r5_hardening",
        "mode": "regular",
        "gain_justifies_human_cost": True,
    }
    payload.pop(missing_field)

    with pytest.raises(ValueError, match="eligibility"):
        HumanEnrichmentOpportunity.from_mapping(payload)


def test_neg14_nonmaterial_gain_and_unjustified_cost_fail_closed() -> None:
    opportunity = _opportunity("MATERIAL")

    with pytest.raises(ValueError, match="material gain"):
        HumanEnrichmentOpportunity(
            **{
                **asdict(opportunity),
                "expected_information_gain": "No material gain.",
            }
        )
    with pytest.raises(ValueError, match="human cost"):
        HumanEnrichmentOpportunity(
            **{
                **asdict(opportunity),
                "gain_justifies_human_cost": False,
            }
        )


def test_mem_opportunity_and_kpr_request_shapes_are_materialized() -> None:
    opportunity = _opportunity("SHAPE")
    request = HumanEnrichmentQueue().persist_request(opportunity)

    assert request is not None
    assert set(opportunity.to_dict()) >= {
        "human_enrichment_opportunity_ref",
        "trigger_ref",
        "trigger_class",
        "candidate_ref",
        "candidate_revision_ref",
        "target_knowledge_refs",
        "related_experience_refs",
        "knowledge_frontier_ref",
        "frontier_lineage_refs",
        "purpose",
        "why_owner",
        "evidence_checked_refs",
        "remaining_gap",
        "expected_information_gain",
        "expected_decision_or_reuse_value",
        "created_at",
        "route_to",
    }
    assert set(request.to_dict()) >= {
        "state",
        "priority",
        "trigger_stage",
        "trigger_class",
        "mode",
        "blocking",
        "requested_owner_ref",
        "candidate_ref",
        "candidate_revision_ref",
        "target_canonical_refs",
        "related_experience_refs",
        "maintenance_case_ref",
        "knowledge_frontier_ref",
        "frontier_descriptor",
        "frontier_lineage_refs",
        "purpose",
        "owner_question",
        "why_owner",
        "expected_information_gain",
        "expected_decision_or_reuse_value",
        "priority_rationale",
        "source_and_evidence_refs",
        "created_at",
        "last_reassessed_at",
        "dedupe_key",
        "completion_criteria",
    }


def test_heq_02_eligibility_creates_candidate_not_acceptance_or_publication() -> None:
    lifecycle = LessonLearnedLifecycle()
    candidate = lifecycle.create_candidate(
        experience_ref="EXP-SYNTHETIC-01",
        eligibility="eligible",
        semantic_payload_ref="PAYLOAD-LESSON-01",
        source_and_evidence_refs=("EL-EXPERIENCE-01",),
    )

    assert candidate is not None
    assert candidate.accepted is False
    assert candidate.published is False
    assert candidate.current_revision.revision == 1
    assert (
        lifecycle.create_candidate(
            experience_ref="EXP-SYNTHETIC-02",
            eligibility="insufficient_evidence",
            semantic_payload_ref="PAYLOAD-LESSON-02",
            source_and_evidence_refs=(),
        )
        is None
    )


def test_heq_03_revise_creates_new_immutable_candidate_revision() -> None:
    lifecycle = LessonLearnedLifecycle()
    candidate = lifecycle.create_candidate(
        experience_ref="EXP-SYNTHETIC-01",
        eligibility="eligible",
        semantic_payload_ref="PAYLOAD-LESSON-01",
        source_and_evidence_refs=("EL-EXPERIENCE-01",),
    )
    original = candidate.current_revision

    revised = lifecycle.revise_candidate(
        candidate,
        disposition="revise",
        human_interaction_source_record_ref="HISR-SYNTHETIC-01",
        new_semantic_payload_ref="PAYLOAD-LESSON-02",
    )

    assert revised.current_revision.revision == 2
    assert revised.current_revision.predecessor_revision_ref == original.revision_ref
    assert revised.current_revision.human_source_record_refs == ("HISR-SYNTHETIC-01",)
    assert original.semantic_payload_ref == "PAYLOAD-LESSON-01"
    with pytest.raises(FrozenInstanceError):
        original.semantic_payload_ref = "mutated"


@pytest.mark.parametrize(
    ("disposition", "accepted", "revision_required", "scope", "reason"),
    [
        ("approve", True, False, (), None),
        ("approve_with_scope", True, False, ("synthetic_scope",), None),
        ("reject", False, False, (), "not suitable"),
        ("defer", False, False, (), "revisit after synthetic follow-up"),
        ("revise", False, True, (), "add bounded context"),
    ],
)
def test_all_lesson_learned_review_dispositions_are_explicit(
    disposition: str,
    accepted: bool,
    revision_required: bool,
    scope: tuple[str, ...],
    reason: str | None,
) -> None:
    lifecycle = LessonLearnedLifecycle()
    candidate = lifecycle.create_candidate(
        experience_ref="EXP-SYNTHETIC-01",
        eligibility="eligible",
        semantic_payload_ref="PAYLOAD-LESSON-01",
        source_and_evidence_refs=("EL-EXPERIENCE-01",),
    )

    outcome = lifecycle.review_candidate(
        candidate,
        disposition=disposition,
        scope_conditions=scope,
        reason=reason,
    )

    assert outcome.disposition == disposition
    assert outcome.accepted is accepted
    assert outcome.revision_required is revision_required
    assert candidate.published is False


def test_heq_04_owner_unknown_closes_request_but_not_frontier() -> None:
    request = HumanEnrichmentQueue().persist_request(_opportunity("UNKNOWN"))
    completed = HumanEnrichmentQueue().close_with_owner_unknown(request)

    assert completed.state == "closed"
    assert completed.frontier_outcome == "unchanged"


def test_heq_05_open_review_blocks_only_affected_candidate() -> None:
    lifecycle = LessonLearnedLifecycle()

    blocking = lifecycle.blocking_scope(("LLC-OPEN",), ("LLC-OTHER",))

    assert blocking.blocked_candidate_refs == ("LLC-OPEN",)
    assert blocking.global_pipeline_blocked is False


def test_heq_06_regular_batch_dedupes_limits_and_prioritizes() -> None:
    queue = HumanEnrichmentQueue()
    opportunities = (
        _opportunity("P2-A", priority="P2", dedupe_key="a"),
        _opportunity("P1-A", priority="P1", dedupe_key="a"),
        _opportunity("P1-B", priority="P1", dedupe_key="b"),
        _opportunity("P2-C", priority="P2", dedupe_key="c"),
        _opportunity("P2-D", priority="P2", dedupe_key="d"),
        _opportunity("P3-E", priority="P3", dedupe_key="e"),
    )
    requests = tuple(
        request
        for item in opportunities
        if (request := queue.persist_request(item)) is not None
    )

    batch = queue.regular_batch(requests)

    assert len(batch) == 3
    assert [item.priority for item in batch] == ["P1", "P1", "P2"]
    assert len({item.dedupe_key for item in batch}) == 3
    assert all(item.priority != "P3" for item in batch)
