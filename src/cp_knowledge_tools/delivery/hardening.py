from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cp_knowledge_tools.lifecycle.enrichment import HumanEnrichmentOpportunity

CurrentnessStatus = Literal[
    "verified_current",
    "historical_only",
    "unknown",
    "not_applicable",
]

_CURRENTNESS_VALUES = {
    "verified_current",
    "historical_only",
    "unknown",
    "not_applicable",
}


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in values if item))


@dataclass(frozen=True, slots=True)
class CurrentnessContext:
    status: CurrentnessStatus
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _CURRENTNESS_VALUES:
            raise ValueError(f"unsupported currentness status: {self.status!r}")
        if self.status == "verified_current" and not self.evidence_refs:
            raise ValueError("verified_current requires current Evidence")


@dataclass(frozen=True, slots=True)
class CurrentOpportunityProjection:
    historical_claim_ref: str
    purpose: str
    currentness: Literal["verified_current"]
    current_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimDeliveryView:
    primary_claim_ref: str
    linked_claim_refs: tuple[str, ...]
    correction_history_refs: tuple[str, ...]
    perspective_refs: tuple[str, ...]
    qualification_refs: tuple[str, ...]
    evidence_assessment_refs: tuple[str, ...]
    equivalent_unresolved_alternative_refs: tuple[str, ...]
    atomic_claim_drill_down_refs: tuple[str, ...]


class DeliveryClaimProjector:
    """Build source-neutral currentness and correction-aware Delivery views."""

    def project_current_opportunity(
        self,
        *,
        historical_claim_ref: str,
        purpose: str,
        currentness: CurrentnessContext,
        policy_profile_conformant: bool,
    ) -> CurrentOpportunityProjection | None:
        if not historical_claim_ref or not purpose:
            raise ValueError("historical Claim and current Purpose are required")
        if currentness.status != "verified_current" or not policy_profile_conformant:
            return None
        return CurrentOpportunityProjection(
            historical_claim_ref=historical_claim_ref,
            purpose=purpose,
            currentness="verified_current",
            current_evidence_refs=currentness.evidence_refs,
        )

    def claim_view(
        self,
        *,
        primary_claim_ref: str,
        linked_claim_refs: tuple[str, ...] = (),
        correction_history_refs: tuple[str, ...] = (),
        perspective_refs: tuple[str, ...] = (),
        qualification_refs: tuple[str, ...] = (),
        evidence_assessment_refs: tuple[str, ...] = (),
    ) -> ClaimDeliveryView:
        if not primary_claim_ref:
            raise ValueError("primary Claim reference is required")
        if primary_claim_ref in correction_history_refs:
            raise ValueError("primary Claim cannot also be Correction History")
        linked = _ordered_unique(linked_claim_refs)
        history = _ordered_unique(correction_history_refs)
        drill_down = _ordered_unique((primary_claim_ref, *linked, *history))
        return ClaimDeliveryView(
            primary_claim_ref=primary_claim_ref,
            linked_claim_refs=linked,
            correction_history_refs=history,
            perspective_refs=_ordered_unique(perspective_refs),
            qualification_refs=_ordered_unique(qualification_refs),
            evidence_assessment_refs=_ordered_unique(evidence_assessment_refs),
            equivalent_unresolved_alternative_refs=(),
            atomic_claim_drill_down_refs=drill_down,
        )


class HumanEnrichmentOpportunityRouter:
    """Agent-Interaction boundary that routes Derived opportunities to KPR."""

    def route(
        self,
        *,
        opportunity_ref: str,
        trigger_ref: str,
        trigger_class: str,
        purpose: str,
        why_owner: str,
        expected_information_gain: str,
        expected_decision_or_reuse_value: str,
        priority: Literal["P0", "P1", "P2", "P3"],
        dedupe_key: str,
        frontier_lineage_refs: tuple[str, ...],
        evidence_checked_refs: tuple[str, ...],
        candidate_ref: str | None,
        candidate_revision_ref: str | None,
        target_knowledge_refs: tuple[str, ...],
        related_experience_refs: tuple[str, ...],
        knowledge_frontier_ref: str,
        remaining_gap: str,
        created_at: str,
        requested_owner_ref: str,
        proposed_owner_question: str,
        priority_rationale: str,
        frontier_descriptor: str,
        completion_criteria: tuple[str, ...],
        trigger_stage: str,
        mode: str,
        gain_justifies_human_cost: bool,
        evidence_sufficient: bool,
        maintenance_case_ref: str | None = None,
        blocking_criteria_satisfied: bool = False,
    ) -> HumanEnrichmentOpportunity | None:
        if evidence_sufficient:
            return None
        return HumanEnrichmentOpportunity(
            opportunity_ref=opportunity_ref,
            trigger_ref=trigger_ref,
            trigger_class=trigger_class,
            purpose=purpose,
            why_owner=why_owner,
            expected_information_gain=expected_information_gain,
            expected_decision_or_reuse_value=expected_decision_or_reuse_value,
            priority=priority,
            dedupe_key=dedupe_key,
            frontier_lineage_refs=frontier_lineage_refs,
            evidence_checked_refs=evidence_checked_refs,
            candidate_ref=candidate_ref,
            candidate_revision_ref=candidate_revision_ref,
            target_knowledge_refs=target_knowledge_refs,
            related_experience_refs=related_experience_refs,
            knowledge_frontier_ref=knowledge_frontier_ref,
            remaining_gap=remaining_gap,
            created_at=created_at,
            route_to="Knowledge Lifecycle and Curation",
            requested_owner_ref=requested_owner_ref,
            proposed_owner_question=proposed_owner_question,
            priority_rationale=priority_rationale,
            frontier_descriptor=frontier_descriptor,
            completion_criteria=completion_criteria,
            trigger_stage=trigger_stage,
            mode=mode,
            gain_justifies_human_cost=gain_justifies_human_cost,
            maintenance_case_ref=maintenance_case_ref,
            evidence_sufficient=False,
            blocking_criteria_satisfied=blocking_criteria_satisfied,
        )
