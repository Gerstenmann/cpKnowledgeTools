from __future__ import annotations

import pytest

from cp_knowledge_tools.delivery.hardening import (
    CurrentnessContext,
    DeliveryClaimProjector,
    HumanEnrichmentOpportunityRouter,
)


def test_sf04_historical_openness_is_not_a_current_opportunity() -> None:
    projector = DeliveryClaimProjector()

    result = projector.project_current_opportunity(
        historical_claim_ref="CLM-HISTORICAL-OPENNESS",
        purpose="current_opportunity_assessment",
        currentness=CurrentnessContext(status="historical_only"),
        policy_profile_conformant=True,
    )

    assert result is None
    with pytest.raises(ValueError, match="current Evidence"):
        CurrentnessContext(status="verified_current")


def test_verified_current_opportunity_retains_historical_and_current_evidence() -> None:
    result = DeliveryClaimProjector().project_current_opportunity(
        historical_claim_ref="CLM-HISTORICAL-OPENNESS",
        purpose="current_opportunity_assessment",
        currentness=CurrentnessContext(
            status="verified_current",
            evidence_refs=("EL-CURRENT-01",),
        ),
        policy_profile_conformant=True,
    )

    assert result is not None
    assert result.historical_claim_ref == "CLM-HISTORICAL-OPENNESS"
    assert result.current_evidence_refs == ("EL-CURRENT-01",)


def test_sf08_correction_history_is_asymmetric_and_drill_down_capable() -> None:
    view = DeliveryClaimProjector().claim_view(
        primary_claim_ref="CLM-CAPACITY-14",
        linked_claim_refs=("CLM-CAPACITY-QUALIFICATION",),
        correction_history_refs=("CLM-CAPACITY-16",),
        perspective_refs=("PERSPECTIVE-COORDINATOR",),
        qualification_refs=("CLM-CAPACITY-QUALIFICATION",),
        evidence_assessment_refs=("EVA-CAPACITY",),
    )

    assert view.primary_claim_ref == "CLM-CAPACITY-14"
    assert view.correction_history_refs == ("CLM-CAPACITY-16",)
    assert view.equivalent_unresolved_alternative_refs == ()
    assert view.atomic_claim_drill_down_refs == (
        "CLM-CAPACITY-14",
        "CLM-CAPACITY-QUALIFICATION",
        "CLM-CAPACITY-16",
    )


def test_heq_07_agent_interaction_routes_opportunity_but_not_request() -> None:
    router = HumanEnrichmentOpportunityRouter()

    opportunity = router.route(
        opportunity_ref="HEO-CURRENTNESS-01",
        trigger_ref="KF-CURRENTNESS-01",
        trigger_class="currentness_gap",
        purpose="current_opportunity_assessment",
        why_owner="Only the synthetic owner may know the current state.",
        expected_information_gain="Determine currentness.",
        expected_decision_or_reuse_value="Avoid a false lead.",
        priority="P1",
        dedupe_key="currentness-01",
        frontier_lineage_refs=("KF-CURRENTNESS-01",),
        evidence_checked_refs=("EL-HISTORICAL",),
        candidate_ref=None,
        candidate_revision_ref=None,
        target_knowledge_refs=("KO-SYNTHETIC-01@1",),
        related_experience_refs=(),
        knowledge_frontier_ref="KF-CURRENTNESS-01",
        remaining_gap="The current state remains unresolved.",
        created_at="2026-08-20T09:00:00+02:00",
        requested_owner_ref="HUMAN-SYNTHETIC-OWNER",
        proposed_owner_question="Is the opportunity currently available?",
        priority_rationale="Currentness materially affects delivery.",
        frontier_descriptor="Currentness remains unverified.",
        completion_criteria=("currentness_answer_recorded",),
        trigger_stage="post_r5_hardening",
        mode="regular",
        gain_justifies_human_cost=True,
        evidence_sufficient=False,
    )

    assert opportunity is not None
    assert opportunity.opportunity_ref == "HEO-CURRENTNESS-01"
    assert not hasattr(opportunity, "human_enrichment_request_ref")
    assert (
        router.route(
            opportunity_ref="HEO-ANSWERED",
            trigger_ref="KF-ANSWERED",
            trigger_class="currentness_gap",
            purpose="current_opportunity_assessment",
            why_owner="No longer needed.",
            expected_information_gain="None.",
            expected_decision_or_reuse_value="None.",
            priority="P2",
            dedupe_key="answered",
            frontier_lineage_refs=("KF-ANSWERED",),
            evidence_checked_refs=("EL-CURRENT",),
            candidate_ref=None,
            candidate_revision_ref=None,
            target_knowledge_refs=("KO-SYNTHETIC-01@1",),
            related_experience_refs=(),
            knowledge_frontier_ref="KF-ANSWERED",
            remaining_gap="No remaining material gap.",
            created_at="2026-08-20T09:00:00+02:00",
            requested_owner_ref="HUMAN-SYNTHETIC-OWNER",
            proposed_owner_question="Is the opportunity currently available?",
            priority_rationale="Current evidence already answers the question.",
            frontier_descriptor="Currentness is already verified.",
            completion_criteria=("currentness_answer_recorded",),
            trigger_stage="post_r5_hardening",
            mode="regular",
            gain_justifies_human_cost=True,
            evidence_sufficient=True,
        )
        is None
    )
