from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from ._common import local_ref

Priority = Literal["P0", "P1", "P2", "P3"]
RequestState = Literal[
    "queued",
    "presented",
    "answered",
    "revision_required",
    "closed",
    "cancelled",
    "superseded",
]
FrontierOutcome = Literal[
    "resolved",
    "partially_resolved",
    "unchanged",
    "reframed",
    "spawned_subfrontier",
]
ReviewDisposition = Literal[
    "approve",
    "approve_with_scope",
    "reject",
    "defer",
    "revise",
]

_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_HUMAN_ENRICHMENT_ROUTE = "Knowledge Lifecycle and Curation"
_IMMATERIAL_TEXT = {
    "none",
    "no gain",
    "no material gain",
    "immaterial",
    "not material",
    "n/a",
    "unknown",
}


def _material_text(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and value.strip()
        and value.strip().lower().rstrip(".") not in _IMMATERIAL_TEXT
    )


@dataclass(frozen=True, slots=True)
class HumanEnrichmentOpportunity:
    opportunity_ref: str
    trigger_ref: str
    trigger_class: str
    purpose: str
    why_owner: str
    expected_information_gain: str
    expected_decision_or_reuse_value: str
    priority: Priority
    dedupe_key: str
    frontier_lineage_refs: tuple[str, ...]
    evidence_checked_refs: tuple[str, ...]
    candidate_ref: str | None
    candidate_revision_ref: str | None
    target_knowledge_refs: tuple[str, ...]
    related_experience_refs: tuple[str, ...]
    knowledge_frontier_ref: str
    remaining_gap: str
    created_at: str
    route_to: str
    requested_owner_ref: str
    proposed_owner_question: str
    priority_rationale: str
    frontier_descriptor: str
    completion_criteria: tuple[str, ...]
    trigger_stage: str
    mode: str
    gain_justifies_human_cost: bool
    maintenance_case_ref: str | None = None
    evidence_sufficient: bool = False
    blocking_criteria_satisfied: bool = False

    def __post_init__(self) -> None:
        required = (
            self.opportunity_ref,
            self.trigger_ref,
            self.trigger_class,
            self.purpose,
            self.why_owner,
            self.expected_information_gain,
            self.expected_decision_or_reuse_value,
            self.dedupe_key,
            self.knowledge_frontier_ref,
            self.remaining_gap,
            self.created_at,
            self.route_to,
            self.requested_owner_ref,
            self.proposed_owner_question,
            self.priority_rationale,
            self.frontier_descriptor,
            self.trigger_stage,
            self.mode,
        )
        if (
            not all(required)
            or not self.frontier_lineage_refs
            or not self.evidence_checked_refs
            or not self.completion_criteria
        ):
            raise ValueError("Human Enrichment Opportunity eligibility is incomplete")
        if self.route_to != _HUMAN_ENRICHMENT_ROUTE:
            raise ValueError(
                "Human Enrichment Opportunity eligibility requires the KPR route"
            )
        if not _material_text(self.expected_information_gain) or not _material_text(
            self.expected_decision_or_reuse_value
        ):
            raise ValueError(
                "Human Enrichment Opportunity eligibility requires material gain"
            )
        if not self.gain_justifies_human_cost:
            raise ValueError(
                "Human Enrichment Opportunity eligibility does not justify human cost"
            )
        if self.priority not in _PRIORITY_RANK:
            raise ValueError(
                f"unsupported Human Enrichment priority: {self.priority!r}"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> HumanEnrichmentOpportunity:
        required = {
            "opportunity_ref",
            "trigger_ref",
            "trigger_class",
            "purpose",
            "why_owner",
            "expected_information_gain",
            "expected_decision_or_reuse_value",
            "priority",
            "dedupe_key",
            "frontier_lineage_refs",
            "evidence_checked_refs",
            "knowledge_frontier_ref",
            "remaining_gap",
            "created_at",
            "route_to",
            "requested_owner_ref",
            "proposed_owner_question",
            "priority_rationale",
            "frontier_descriptor",
            "completion_criteria",
            "trigger_stage",
            "mode",
            "gain_justifies_human_cost",
        }
        missing = sorted(field for field in required if field not in value)
        if missing:
            raise ValueError(
                f"Human Enrichment Opportunity eligibility fields missing: {missing}"
            )
        return cls(
            opportunity_ref=value.get("opportunity_ref"),
            trigger_ref=value.get("trigger_ref"),
            trigger_class=value.get("trigger_class"),
            purpose=value.get("purpose"),
            why_owner=value.get("why_owner"),
            expected_information_gain=value.get("expected_information_gain"),
            expected_decision_or_reuse_value=value.get(
                "expected_decision_or_reuse_value"
            ),
            priority=value.get("priority"),
            dedupe_key=value.get("dedupe_key"),
            frontier_lineage_refs=tuple(value.get("frontier_lineage_refs", ())),
            evidence_checked_refs=tuple(value.get("evidence_checked_refs", ())),
            candidate_ref=value.get("candidate_ref"),
            candidate_revision_ref=value.get("candidate_revision_ref"),
            target_knowledge_refs=tuple(value.get("target_knowledge_refs", ())),
            related_experience_refs=tuple(value.get("related_experience_refs", ())),
            knowledge_frontier_ref=value.get("knowledge_frontier_ref"),
            remaining_gap=value.get("remaining_gap"),
            created_at=value.get("created_at"),
            route_to=value.get("route_to"),
            requested_owner_ref=value.get("requested_owner_ref"),
            proposed_owner_question=value.get("proposed_owner_question"),
            priority_rationale=value.get("priority_rationale"),
            frontier_descriptor=value.get("frontier_descriptor"),
            completion_criteria=tuple(value.get("completion_criteria", ())),
            trigger_stage=value.get("trigger_stage"),
            mode=value.get("mode"),
            gain_justifies_human_cost=(value.get("gain_justifies_human_cost") is True),
            maintenance_case_ref=value.get("maintenance_case_ref"),
            evidence_sufficient=value.get("evidence_sufficient") is True,
            blocking_criteria_satisfied=(
                value.get("blocking_criteria_satisfied") is True
            ),
        )

    @property
    def human_enrichment_opportunity_ref(self) -> str:
        return self.opportunity_ref

    @property
    def eligible_for_request(self) -> bool:
        return (
            not self.evidence_sufficient
            and bool(self.knowledge_frontier_ref)
            and bool(self.frontier_lineage_refs)
            and bool(self.purpose)
            and bool(self.why_owner)
            and _material_text(self.expected_information_gain)
            and _material_text(self.expected_decision_or_reuse_value)
            and bool(self.evidence_checked_refs)
            and bool(self.proposed_owner_question)
            and self.gain_justifies_human_cost
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["human_enrichment_opportunity_ref"] = payload.pop("opportunity_ref")
        for field in (
            "target_knowledge_refs",
            "related_experience_refs",
            "frontier_lineage_refs",
            "evidence_checked_refs",
            "completion_criteria",
        ):
            payload[field] = list(payload[field])
        return payload


@dataclass(frozen=True, slots=True)
class HumanEnrichmentRequest:
    human_enrichment_request_ref: str
    opportunity_ref: str
    state: RequestState
    priority: Priority
    blocking: bool
    trigger_ref: str
    trigger_stage: str
    trigger_class: str
    mode: str
    requested_owner_ref: str
    candidate_ref: str | None
    candidate_revision_ref: str | None
    target_canonical_refs: tuple[str, ...]
    related_experience_refs: tuple[str, ...]
    maintenance_case_ref: str | None
    knowledge_frontier_ref: str
    frontier_descriptor: str
    purpose: str
    owner_question: str
    why_owner: str
    expected_information_gain: str
    expected_decision_or_reuse_value: str
    priority_rationale: str
    frontier_lineage_refs: tuple[str, ...]
    source_and_evidence_refs: tuple[str, ...]
    created_at: str
    last_reassessed_at: str
    dedupe_key: str
    completion_criteria: tuple[str, ...]
    frontier_outcome: FrontierOutcome | None = None

    def __post_init__(self) -> None:
        required = (
            self.human_enrichment_request_ref,
            self.opportunity_ref,
            self.trigger_ref,
            self.trigger_stage,
            self.trigger_class,
            self.mode,
            self.requested_owner_ref,
            self.knowledge_frontier_ref,
            self.frontier_descriptor,
            self.purpose,
            self.owner_question,
            self.why_owner,
            self.expected_information_gain,
            self.expected_decision_or_reuse_value,
            self.priority_rationale,
            self.created_at,
            self.last_reassessed_at,
            self.dedupe_key,
        )
        if not all(required) or not self.frontier_lineage_refs:
            raise ValueError("Human Enrichment Request contract is incomplete")
        if not self.source_and_evidence_refs or not self.completion_criteria:
            raise ValueError("Human Enrichment Request eligibility evidence is missing")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for field in (
            "target_canonical_refs",
            "related_experience_refs",
            "frontier_lineage_refs",
            "source_and_evidence_refs",
            "completion_criteria",
        ):
            payload[field] = list(payload[field])
        return payload


class HumanEnrichmentQueue:
    """KPR boundary for eligibility, priority, dedupe, and completion."""

    def persist_request(
        self, opportunity: HumanEnrichmentOpportunity
    ) -> HumanEnrichmentRequest | None:
        if not opportunity.eligible_for_request:
            return None
        if opportunity.priority == "P0" and not (
            opportunity.blocking_criteria_satisfied
        ):
            return None
        payload = {
            "opportunity_ref": opportunity.opportunity_ref,
            "trigger_ref": opportunity.trigger_ref,
            "purpose": opportunity.purpose,
            "dedupe_key": opportunity.dedupe_key,
        }
        return HumanEnrichmentRequest(
            human_enrichment_request_ref=local_ref("HER", payload),
            opportunity_ref=opportunity.opportunity_ref,
            state="queued",
            priority=opportunity.priority,
            blocking=opportunity.priority == "P0",
            trigger_ref=opportunity.trigger_ref,
            trigger_stage=opportunity.trigger_stage,
            trigger_class=opportunity.trigger_class,
            mode=opportunity.mode,
            requested_owner_ref=opportunity.requested_owner_ref,
            candidate_ref=opportunity.candidate_ref,
            candidate_revision_ref=opportunity.candidate_revision_ref,
            target_canonical_refs=opportunity.target_knowledge_refs,
            related_experience_refs=opportunity.related_experience_refs,
            maintenance_case_ref=opportunity.maintenance_case_ref,
            knowledge_frontier_ref=opportunity.knowledge_frontier_ref,
            frontier_descriptor=opportunity.frontier_descriptor,
            purpose=opportunity.purpose,
            owner_question=opportunity.proposed_owner_question,
            why_owner=opportunity.why_owner,
            expected_information_gain=opportunity.expected_information_gain,
            expected_decision_or_reuse_value=(
                opportunity.expected_decision_or_reuse_value
            ),
            priority_rationale=opportunity.priority_rationale,
            frontier_lineage_refs=opportunity.frontier_lineage_refs,
            source_and_evidence_refs=opportunity.evidence_checked_refs,
            created_at=opportunity.created_at,
            last_reassessed_at=opportunity.created_at,
            dedupe_key=opportunity.dedupe_key,
            completion_criteria=opportunity.completion_criteria,
        )

    def regular_batch(
        self, requests: tuple[HumanEnrichmentRequest, ...]
    ) -> tuple[HumanEnrichmentRequest, ...]:
        eligible = sorted(
            (
                item
                for item in requests
                if not item.blocking
                and item.priority in {"P1", "P2"}
                and item.state not in {"closed", "cancelled", "superseded"}
            ),
            key=lambda item: (
                _PRIORITY_RANK[item.priority],
                item.dedupe_key,
                item.human_enrichment_request_ref,
            ),
        )
        deduplicated: dict[str, HumanEnrichmentRequest] = {}
        for item in eligible:
            deduplicated.setdefault(item.dedupe_key, item)
        return tuple(deduplicated.values())[:3]

    def close_with_owner_unknown(
        self, request: HumanEnrichmentRequest
    ) -> HumanEnrichmentRequest:
        return replace(request, state="closed", frontier_outcome="unchanged")


@dataclass(frozen=True, slots=True)
class LessonLearnedCandidateRevision:
    revision_ref: str
    revision: int
    predecessor_revision_ref: str | None
    semantic_payload_ref: str
    source_and_evidence_refs: tuple[str, ...]
    human_source_record_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LessonLearnedCandidate:
    candidate_ref: str
    experience_ref: str
    current_revision: LessonLearnedCandidateRevision
    accepted: bool = False
    published: bool = False


@dataclass(frozen=True, slots=True)
class CandidateBlockingScope:
    blocked_candidate_refs: tuple[str, ...]
    unblocked_candidate_refs: tuple[str, ...]
    global_pipeline_blocked: bool = False


@dataclass(frozen=True, slots=True)
class LessonLearnedReviewOutcome:
    candidate_ref: str
    candidate_revision_ref: str
    disposition: ReviewDisposition
    accepted: bool
    scope_conditions: tuple[str, ...] = ()
    reason: str | None = None
    revision_required: bool = False


class LessonLearnedLifecycle:
    def create_candidate(
        self,
        *,
        experience_ref: str,
        eligibility: str,
        semantic_payload_ref: str,
        source_and_evidence_refs: tuple[str, ...],
    ) -> LessonLearnedCandidate | None:
        if eligibility != "eligible":
            return None
        if not experience_ref or not semantic_payload_ref:
            raise ValueError(
                "eligible Lesson-Learned Candidate requires Experience and Payload"
            )
        if not source_and_evidence_refs:
            raise ValueError("eligible Lesson-Learned Candidate requires Evidence")
        candidate_ref = local_ref(
            "LLC",
            {"experience_ref": experience_ref, "kind": "lesson_learned"},
        )
        revision_ref = f"{candidate_ref}@1"
        revision = LessonLearnedCandidateRevision(
            revision_ref=revision_ref,
            revision=1,
            predecessor_revision_ref=None,
            semantic_payload_ref=semantic_payload_ref,
            source_and_evidence_refs=source_and_evidence_refs,
        )
        return LessonLearnedCandidate(
            candidate_ref=candidate_ref,
            experience_ref=experience_ref,
            current_revision=revision,
        )

    def revise_candidate(
        self,
        candidate: LessonLearnedCandidate,
        *,
        disposition: ReviewDisposition,
        human_interaction_source_record_ref: str,
        new_semantic_payload_ref: str,
    ) -> LessonLearnedCandidate:
        if disposition != "revise":
            raise ValueError("new Candidate Revision requires revise disposition")
        if not human_interaction_source_record_ref:
            raise ValueError("revise requires a Human Interaction Source Record")
        previous = candidate.current_revision
        if new_semantic_payload_ref == previous.semantic_payload_ref:
            raise ValueError("revise requires a material new semantic Payload")
        next_revision = previous.revision + 1
        revision = LessonLearnedCandidateRevision(
            revision_ref=f"{candidate.candidate_ref}@{next_revision}",
            revision=next_revision,
            predecessor_revision_ref=previous.revision_ref,
            semantic_payload_ref=new_semantic_payload_ref,
            source_and_evidence_refs=previous.source_and_evidence_refs,
            human_source_record_refs=(human_interaction_source_record_ref,),
        )
        return replace(
            candidate,
            current_revision=revision,
            accepted=False,
            published=False,
        )

    def review_candidate(
        self,
        candidate: LessonLearnedCandidate,
        *,
        disposition: ReviewDisposition,
        scope_conditions: tuple[str, ...] = (),
        reason: str | None = None,
    ) -> LessonLearnedReviewOutcome:
        if disposition == "approve_with_scope" and not scope_conditions:
            raise ValueError("approve_with_scope requires explicit Scope conditions")
        if disposition == "defer" and not reason:
            raise ValueError("defer requires a reason or revisit condition")
        accepted = disposition in {"approve", "approve_with_scope"}
        return LessonLearnedReviewOutcome(
            candidate_ref=candidate.candidate_ref,
            candidate_revision_ref=candidate.current_revision.revision_ref,
            disposition=disposition,
            accepted=accepted,
            scope_conditions=scope_conditions,
            reason=reason,
            revision_required=disposition == "revise",
        )

    def blocking_scope(
        self,
        open_review_candidate_refs: tuple[str, ...],
        other_candidate_refs: tuple[str, ...],
    ) -> CandidateBlockingScope:
        blocked = tuple(dict.fromkeys(open_review_candidate_refs))
        return CandidateBlockingScope(
            blocked_candidate_refs=blocked,
            unblocked_candidate_refs=tuple(
                item
                for item in dict.fromkeys(other_candidate_refs)
                if item not in blocked
            ),
        )
