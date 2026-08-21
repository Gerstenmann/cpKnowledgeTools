from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from cp_knowledge_tools.semantics.change_candidates import ChangeCandidateRevision

from ._common import (
    canonical_json,
    canonical_value,
    content_hash,
    local_ref,
    ordered_unique,
)

SameObjectResult = Literal[
    "same_identity",
    "new_identity_required",
    "no_material_new_version",
    "ambiguous_or_unresolved",
    "not_applicable",
]
ResolutionDisposition = Literal["resolved", "blocked", "unresolved"]

RESOLUTION_TYPES = frozenset(
    {
        "create_new_identity",
        "revise_existing_identity",
        "map_to_existing_without_new_version",
        "merge_into_existing",
        "merge_into_new_identity",
        "split_into_new_identities",
        "retract_existing_version",
        "close_without_canonicalization",
    }
)

_CLAIM_IDENTITY_DIMENSIONS = (
    "subject",
    "predicate",
    "object",
    "value",
    "modality",
    "applicability_scope",
    "normative_content",
)
_EVENT_IDENTITY_DIMENSIONS = ("occurrence_key", "occurrence_ref", "event_ref")
_KNOWLEDGE_OBJECT_IDENTITY_DIMENSIONS = (
    "knowledge_purpose",
    "identity_continuity",
    "primary_kind",
    "authority_boundary",
    "lifecycle_boundary",
)
_FOREIGN_AUTHORITY_ACTIONS = frozenset(
    {
        "permit_policy",
        "deny_policy",
        "publish",
        "publication_authority",
        "approve_review",
    }
)


@dataclass(frozen=True, slots=True)
class LifecycleCandidateRevision:
    """Minimal KPR registration projection over one immutable D4 revision."""

    lifecycle_candidate_ref: str
    lifecycle_candidate_revision_ref: str
    candidate_revision: str
    source_change_candidate_ref: str
    source_change_candidate_revision_ref: str
    semantic_unit_kind: str
    semantic_change_operation: str
    target_refs: tuple[str, ...]
    target_version_refs: tuple[str, ...]
    source_finding_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    producer_refs: tuple[str, ...]
    registered_by: str
    registered_at: str
    rule_basis_refs: tuple[str, ...]
    idempotency_key: str
    request_fingerprint: str
    revision_hash: str
    contract_version: str = "0.1"
    non_canonical: bool = True
    identity_scope: str = "implementation_local_non_canonical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Candidate Registration and Revision Contract",
            "contract_version": self.contract_version,
            "message_kind": "record",
            "candidate_ref": self.lifecycle_candidate_ref,
            "candidate_revision_ref": self.lifecycle_candidate_revision_ref,
            "candidate_revision": self.candidate_revision,
            "source_change_candidate_ref": self.source_change_candidate_ref,
            "source_change_candidate_revision_ref": (
                self.source_change_candidate_revision_ref
            ),
            "semantic_unit_kind": self.semantic_unit_kind,
            "semantic_change_operation": self.semantic_change_operation,
            "target_refs": list(self.target_refs),
            "target_version_refs": list(self.target_version_refs),
            "source_finding_refs": list(self.source_finding_refs),
            "source_refs": list(self.source_refs),
            "evidence_refs": list(self.evidence_refs),
            "producer_refs": list(self.producer_refs),
            "registered_by": self.registered_by,
            "registered_at": self.registered_at,
            "rule_basis_refs": list(self.rule_basis_refs),
            "idempotency_key": self.idempotency_key,
            "request_fingerprint": self.request_fingerprint,
            "revision_hash": self.revision_hash,
            "non_canonical": self.non_canonical,
            "identity_scope": self.identity_scope,
        }


class LifecycleCandidateRegistrar:
    def register(
        self,
        source: ChangeCandidateRevision,
        *,
        registered_by: str,
        registered_at: str,
        rule_basis_refs: tuple[str, ...],
        idempotency_key: str,
    ) -> LifecycleCandidateRevision:
        if not source.non_canonical:
            raise ValueError("lifecycle_registration_requires_non_canonical_candidate")
        fingerprint_payload = {
            "contract_name": "Candidate Registration and Revision Contract",
            "contract_version": "0.1",
            "operation": "register_candidate_revision",
            "source_change_candidate": source.to_dict(),
            "registered_by": registered_by,
            "rule_basis_refs": list(ordered_unique(rule_basis_refs)),
        }
        request_fingerprint = content_hash(fingerprint_payload)
        candidate_ref = local_ref(
            "LCC",
            {
                "source_change_candidate_ref": source.change_candidate_ref,
                "authority_context": "Knowledge Lifecycle and Curation",
            },
        )
        revision_payload = {
            "candidate_ref": candidate_ref,
            "source_change_candidate_revision_ref": source.candidate_revision_ref,
            "request_fingerprint": request_fingerprint,
            "idempotency_key": idempotency_key,
        }
        revision_hash = content_hash(revision_payload)
        return LifecycleCandidateRevision(
            lifecycle_candidate_ref=candidate_ref,
            lifecycle_candidate_revision_ref=f"LCR-{revision_hash[:24]}",
            candidate_revision=f"local-{revision_hash[:12]}",
            source_change_candidate_ref=source.change_candidate_ref,
            source_change_candidate_revision_ref=source.candidate_revision_ref,
            semantic_unit_kind=source.semantic_unit_kind,
            semantic_change_operation=source.semantic_change_operation,
            target_refs=ordered_unique(source.target_refs),
            target_version_refs=ordered_unique(source.target_version_refs),
            source_finding_refs=ordered_unique(source.source_finding_refs),
            source_refs=ordered_unique(source.source_refs),
            evidence_refs=ordered_unique(source.evidence_refs),
            producer_refs=ordered_unique((*source.producer_provenance, registered_by)),
            registered_by=registered_by,
            registered_at=registered_at,
            rule_basis_refs=ordered_unique(rule_basis_refs),
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            revision_hash=revision_hash,
        )


@dataclass(frozen=True, slots=True)
class IdentitySnapshot:
    semantic_unit_kind: str
    identity_ref: str | None
    _dimensions_json: str
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_dimensions(
        cls,
        *,
        semantic_unit_kind: str,
        identity_ref: str | None,
        dimensions: dict[str, object],
        evidence_refs: tuple[str, ...] = (),
    ) -> IdentitySnapshot:
        return cls(
            semantic_unit_kind=semantic_unit_kind,
            identity_ref=identity_ref,
            _dimensions_json=canonical_json(dimensions),
            evidence_refs=ordered_unique(evidence_refs),
        )

    @property
    def dimensions(self) -> dict[str, Any]:
        return json.loads(self._dimensions_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_unit_kind": self.semantic_unit_kind,
            "identity_ref": self.identity_ref,
            "dimensions": self.dimensions,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SameObjectAssessmentRequest:
    candidate_revision: LifecycleCandidateRevision
    prior_snapshot: IdentitySnapshot | None
    proposed_snapshot: IdentitySnapshot | None
    existing_canonical_refs: tuple[str, ...]
    prior_identity_evidence_refs: tuple[str, ...]
    assessed_dimensions: tuple[str, ...]
    material_delta_dimensions: tuple[str, ...]
    rationale: str
    rule_basis_refs: tuple[str, ...]
    unresolved_identity_questions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SameObjectAssessment:
    same_object_assessment_ref: str
    candidate_ref: str
    candidate_revision_ref: str
    semantic_unit_kind: str
    existing_canonical_refs: tuple[str, ...]
    prior_identity_evidence_refs: tuple[str, ...]
    assessed_dimensions: tuple[str, ...]
    changed_identity_dimensions: tuple[str, ...]
    material_delta_dimensions: tuple[str, ...]
    result: SameObjectResult
    rationale: str
    rule_basis_refs: tuple[str, ...]
    unresolved_identity_questions: tuple[str, ...]
    disposition: str = "assessed"
    contract_version: str = "0.1"
    identity_scope: str = "implementation_local_non_canonical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Same-Object Assessment",
            "contract_version": self.contract_version,
            "same_object_assessment_ref": self.same_object_assessment_ref,
            "candidate_ref": self.candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "semantic_unit_kind": self.semantic_unit_kind,
            "existing_canonical_refs": list(self.existing_canonical_refs),
            "prior_identity_evidence_refs": list(self.prior_identity_evidence_refs),
            "assessed_dimensions": list(self.assessed_dimensions),
            "changed_identity_dimensions": list(self.changed_identity_dimensions),
            "material_delta_dimensions": list(self.material_delta_dimensions),
            "result": self.result,
            "rationale": self.rationale,
            "rule_basis_refs": list(self.rule_basis_refs),
            "unresolved_identity_questions": list(self.unresolved_identity_questions),
            "identity_scope": self.identity_scope,
        }


class SameObjectEvaluator:
    """Apply Core identity dimensions without using operation-to-resolution maps."""

    def evaluate(self, request: SameObjectAssessmentRequest) -> SameObjectAssessment:
        candidate = request.candidate_revision
        prior = request.prior_snapshot
        proposed = request.proposed_snapshot
        changed: tuple[str, ...] = ()

        if request.unresolved_identity_questions or proposed is None:
            result: SameObjectResult = "ambiguous_or_unresolved"
        elif proposed.semantic_unit_kind != candidate.semantic_unit_kind:
            result = "ambiguous_or_unresolved"
        elif prior is None or prior.identity_ref is None:
            result = "new_identity_required"
            changed = ordered_unique(
                dimension
                for dimension, value in proposed.dimensions.items()
                if value is not None
            )
        elif prior.semantic_unit_kind != proposed.semantic_unit_kind:
            result = "new_identity_required"
            changed = ("semantic_unit_kind",)
        else:
            identity_dimensions = self._identity_dimensions(
                candidate.semantic_unit_kind,
                prior.dimensions,
                proposed.dimensions,
            )
            changed = tuple(
                dimension
                for dimension in identity_dimensions
                if prior.dimensions.get(dimension) != proposed.dimensions.get(dimension)
            )
            if changed:
                result = "new_identity_required"
            elif not request.material_delta_dimensions:
                result = "no_material_new_version"
            elif identity_dimensions:
                result = "same_identity"
            else:
                result = "ambiguous_or_unresolved"

        payload = {
            "candidate_ref": candidate.lifecycle_candidate_ref,
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "semantic_unit_kind": candidate.semantic_unit_kind,
            "prior_snapshot": prior.to_dict() if prior else None,
            "proposed_snapshot": proposed.to_dict() if proposed else None,
            "existing_canonical_refs": list(
                ordered_unique(request.existing_canonical_refs)
            ),
            "prior_identity_evidence_refs": list(
                ordered_unique(request.prior_identity_evidence_refs)
            ),
            "assessed_dimensions": list(ordered_unique(request.assessed_dimensions)),
            "changed_identity_dimensions": list(changed),
            "material_delta_dimensions": list(
                ordered_unique(request.material_delta_dimensions)
            ),
            "result": result,
            "rationale": request.rationale,
            "rule_basis_refs": list(ordered_unique(request.rule_basis_refs)),
            "unresolved_identity_questions": list(
                ordered_unique(request.unresolved_identity_questions)
            ),
        }
        return SameObjectAssessment(
            same_object_assessment_ref=local_ref("SOA", payload),
            candidate_ref=candidate.lifecycle_candidate_ref,
            candidate_revision_ref=candidate.lifecycle_candidate_revision_ref,
            semantic_unit_kind=candidate.semantic_unit_kind,
            existing_canonical_refs=ordered_unique(request.existing_canonical_refs),
            prior_identity_evidence_refs=ordered_unique(
                request.prior_identity_evidence_refs
            ),
            assessed_dimensions=ordered_unique(request.assessed_dimensions),
            changed_identity_dimensions=ordered_unique(changed),
            material_delta_dimensions=ordered_unique(request.material_delta_dimensions),
            result=result,
            rationale=request.rationale,
            rule_basis_refs=ordered_unique(request.rule_basis_refs),
            unresolved_identity_questions=ordered_unique(
                request.unresolved_identity_questions
            ),
        )

    @staticmethod
    def _identity_dimensions(
        semantic_unit_kind: str,
        prior: dict[str, Any],
        proposed: dict[str, Any],
    ) -> tuple[str, ...]:
        if semantic_unit_kind == "claim":
            return tuple(
                key
                for key in _CLAIM_IDENTITY_DIMENSIONS
                if key in prior or key in proposed
            )
        if semantic_unit_kind == "event":
            return tuple(
                key
                for key in _EVENT_IDENTITY_DIMENSIONS
                if key in prior or key in proposed
            )
        if semantic_unit_kind == "knowledge_object":
            return tuple(
                key
                for key in _KNOWLEDGE_OBJECT_IDENTITY_DIMENSIONS
                if key in prior or key in proposed
            )
        return ()


@dataclass(frozen=True, slots=True)
class ResolutionAuthority:
    authority_ref: str
    authority_context: str
    authority_kind: str
    authorized_actions: tuple[str, ...]
    decision_basis_refs: tuple[str, ...]
    decided_at: str


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    resolution_type: str
    target_canonical_refs: tuple[str, ...]
    planned_target_versions: tuple[str, ...]
    identity_rationale: str
    merge_or_split_plan_ref: str | None = None
    review_record_refs: tuple[str, ...] = ()
    policy_context_refs: tuple[str, ...] = ()
    overwrites_existing_claim: bool = False
    attempts_in_place_knowledge_mutation: bool = False
    attempts_predecessor_supersession: bool = False
    predecessor_publication_state: str | None = None
    foreign_authority_effects: tuple[str, ...] = ()
    originated_from_review: bool = False


@dataclass(frozen=True, slots=True)
class ResolutionRequest:
    candidate_revision: LifecycleCandidateRevision
    same_object_assessment: SameObjectAssessment | None
    plan: ResolutionPlan
    authority: ResolutionAuthority
    active_resolution_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    resolution_decision_ref: str
    candidate_ref: str
    candidate_revision_ref: str
    resolution_type: str
    source_candidate_refs: tuple[str, ...]
    target_canonical_refs: tuple[str, ...]
    planned_target_versions: tuple[str, ...]
    identity_rationale: str
    same_object_assessment_ref: str
    merge_or_split_plan_ref: str | None
    review_record_refs: tuple[str, ...]
    policy_context_refs: tuple[str, ...]
    decided_by: str
    decision_authority_context: str
    decision_authority_kind: str
    decided_at: str
    rule_basis_refs: tuple[str, ...]
    decision_hash: str
    contract_version: str = "0.1"
    identity_scope: str = "implementation_local_non_canonical"
    publication_status: str = "not_performed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Resolution Decision Contract",
            "contract_version": self.contract_version,
            "message_kind": "decision",
            "resolution_decision_ref": self.resolution_decision_ref,
            "candidate_ref": self.candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "resolution_type": self.resolution_type,
            "source_candidate_refs": list(self.source_candidate_refs),
            "target_canonical_refs": list(self.target_canonical_refs),
            "planned_target_versions": list(self.planned_target_versions),
            "identity_rationale": self.identity_rationale,
            "same_object_assessment": self.same_object_assessment_ref,
            "merge_or_split_plan_ref": self.merge_or_split_plan_ref,
            "review_record_refs": list(self.review_record_refs),
            "policy_context_refs": list(self.policy_context_refs),
            "decided_by": self.decided_by,
            "decision_authority_context": self.decision_authority_context,
            "decision_authority_kind": self.decision_authority_kind,
            "decided_at": self.decided_at,
            "rule_basis_refs": list(self.rule_basis_refs),
            "decision_hash": self.decision_hash,
            "identity_scope": self.identity_scope,
            "publication_status": self.publication_status,
        }


@dataclass(frozen=True, slots=True)
class ResolutionEvaluation:
    disposition: ResolutionDisposition
    reason_code: str
    decision: ResolutionDecision | None = None


class ResolutionEngine:
    """Validate an explicit Core assessment and caller-supplied resolution plan."""

    def evaluate(self, request: ResolutionRequest) -> ResolutionEvaluation:
        candidate = request.candidate_revision
        assessment = request.same_object_assessment
        plan = request.plan
        authority = request.authority

        if assessment is None:
            return self._blocked("block_same_object_assessment_required")
        if assessment.candidate_ref != candidate.lifecycle_candidate_ref or (
            assessment.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
        ):
            return self._blocked("same_object_assessment_revision_mismatch")
        if assessment.result == "ambiguous_or_unresolved":
            return ResolutionEvaluation(
                disposition="unresolved",
                reason_code="same_object_assessment_unresolved",
            )
        if (
            not authority.authority_ref
            or authority.authority_kind == "development_agent"
            or "resolve_candidate_identity" not in authority.authorized_actions
        ):
            return self._blocked("resolution_authority_missing")
        if _FOREIGN_AUTHORITY_ACTIONS.intersection(authority.authorized_actions):
            return self._blocked("resolution_authority_scope_escalation_forbidden")
        if request.active_resolution_refs:
            return self._blocked("competing_active_resolution_decision")
        if plan.resolution_type not in RESOLUTION_TYPES:
            return self._blocked("resolution_type_not_allowed")
        if plan.originated_from_review:
            return self._blocked("review_cannot_create_resolution_decision")
        if plan.foreign_authority_effects:
            return self._blocked("resolution_foreign_authority_effect_forbidden")
        if plan.overwrites_existing_claim:
            return self._blocked("conflict_overwrite_forbidden")
        if plan.attempts_in_place_knowledge_mutation:
            return self._blocked("material_knowledge_object_state_in_place_forbidden")
        if (
            plan.attempts_predecessor_supersession
            and plan.predecessor_publication_state == "unpublished"
        ):
            return self._blocked("unpublished_predecessor_cannot_be_superseded")
        if (
            plan.resolution_type == "map_to_existing_without_new_version"
            and assessment.material_delta_dimensions
        ):
            return self._blocked("material_delta_requires_new_version")
        if not self._resolution_matches_assessment(
            plan.resolution_type,
            assessment.result,
        ):
            return self._blocked(
                "resolution_type_conflicts_with_same_object_assessment"
            )
        if any(
            ref
            in {
                candidate.lifecycle_candidate_ref,
                candidate.source_change_candidate_ref,
            }
            for ref in plan.target_canonical_refs
        ):
            return self._blocked("candidate_id_cannot_be_canonical_id")
        if (
            plan.resolution_type
            in {
                "merge_into_existing",
                "merge_into_new_identity",
                "split_into_new_identities",
            }
            and not plan.merge_or_split_plan_ref
        ):
            return self._blocked("merge_or_split_plan_missing")

        rule_basis_refs = ordered_unique(
            (*assessment.rule_basis_refs, *authority.decision_basis_refs)
        )
        decision_payload = {
            "candidate_ref": candidate.lifecycle_candidate_ref,
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "resolution_type": plan.resolution_type,
            "source_candidate_refs": [
                candidate.source_change_candidate_ref,
                candidate.lifecycle_candidate_ref,
            ],
            "target_canonical_refs": list(ordered_unique(plan.target_canonical_refs)),
            "planned_target_versions": list(
                ordered_unique(plan.planned_target_versions)
            ),
            "identity_rationale": plan.identity_rationale,
            "same_object_assessment_ref": assessment.same_object_assessment_ref,
            "merge_or_split_plan_ref": plan.merge_or_split_plan_ref,
            "review_record_refs": list(ordered_unique(plan.review_record_refs)),
            "policy_context_refs": list(ordered_unique(plan.policy_context_refs)),
            "decided_by": authority.authority_ref,
            "decision_authority_context": authority.authority_context,
            "decision_authority_kind": authority.authority_kind,
            "decided_at": authority.decided_at,
            "rule_basis_refs": list(rule_basis_refs),
        }
        decision_hash = content_hash(decision_payload)
        decision = ResolutionDecision(
            resolution_decision_ref=f"RDL-{decision_hash[:24]}",
            candidate_ref=candidate.lifecycle_candidate_ref,
            candidate_revision_ref=candidate.lifecycle_candidate_revision_ref,
            resolution_type=plan.resolution_type,
            source_candidate_refs=ordered_unique(
                (
                    candidate.source_change_candidate_ref,
                    candidate.lifecycle_candidate_ref,
                )
            ),
            target_canonical_refs=ordered_unique(plan.target_canonical_refs),
            planned_target_versions=ordered_unique(plan.planned_target_versions),
            identity_rationale=plan.identity_rationale,
            same_object_assessment_ref=assessment.same_object_assessment_ref,
            merge_or_split_plan_ref=plan.merge_or_split_plan_ref,
            review_record_refs=ordered_unique(plan.review_record_refs),
            policy_context_refs=ordered_unique(plan.policy_context_refs),
            decided_by=authority.authority_ref,
            decision_authority_context=authority.authority_context,
            decision_authority_kind=authority.authority_kind,
            decided_at=authority.decided_at,
            rule_basis_refs=rule_basis_refs,
            decision_hash=decision_hash,
        )
        return ResolutionEvaluation(
            disposition="resolved",
            reason_code="resolution_decision_created",
            decision=decision,
        )

    @staticmethod
    def _resolution_matches_assessment(
        resolution_type: str,
        result: SameObjectResult,
    ) -> bool:
        if resolution_type == "create_new_identity":
            return result == "new_identity_required"
        if resolution_type == "revise_existing_identity":
            return result == "same_identity"
        if resolution_type == "map_to_existing_without_new_version":
            return result == "no_material_new_version"
        if resolution_type in {
            "merge_into_existing",
            "merge_into_new_identity",
            "split_into_new_identities",
            "retract_existing_version",
            "close_without_canonicalization",
        }:
            return result in {
                "same_identity",
                "new_identity_required",
                "not_applicable",
            }
        return False

    @staticmethod
    def _blocked(reason_code: str) -> ResolutionEvaluation:
        return ResolutionEvaluation(disposition="blocked", reason_code=reason_code)


@dataclass(frozen=True, slots=True)
class KnowledgeVersionProjectionRequest:
    resolution_decision: ResolutionDecision
    stable_knowledge_object_ref: str
    prior_knowledge_object_version_ref: str
    prior_publication_state: str
    planned_target_knowledge_object_version_ref: str | None
    material_change: bool
    same_knowledge_object_identity: bool
    attempts_predecessor_supersession: bool = False
    attempts_in_place_mutation: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeVersionProjection:
    projection_ref: str
    resolution_decision_ref: str
    stable_knowledge_object_ref: str
    prior_knowledge_object_version_ref: str
    prior_publication_state: str
    planned_target_knowledge_object_version_ref: str | None
    same_knowledge_object_identity: bool
    new_version_required: bool
    prior_version_effect: str = "unchanged"
    publication_status: str = "not_performed"
    immutable: bool = True
    identity_scope: str = "implementation_local_non_canonical"

    def to_dict(self) -> dict[str, Any]:
        return canonical_value(
            {
                "projection_ref": self.projection_ref,
                "resolution_decision_ref": self.resolution_decision_ref,
                "stable_knowledge_object_ref": self.stable_knowledge_object_ref,
                "prior_knowledge_object_version_ref": (
                    self.prior_knowledge_object_version_ref
                ),
                "prior_publication_state": self.prior_publication_state,
                "planned_target_knowledge_object_version_ref": (
                    self.planned_target_knowledge_object_version_ref
                ),
                "same_knowledge_object_identity": self.same_knowledge_object_identity,
                "new_version_required": self.new_version_required,
                "prior_version_effect": self.prior_version_effect,
                "publication_status": self.publication_status,
                "immutable": self.immutable,
                "identity_scope": self.identity_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class KnowledgeVersionProjectionEvaluation:
    disposition: Literal["projected", "blocked"]
    reason_code: str
    projection: KnowledgeVersionProjection | None = None


class KnowledgeVersionProjector:
    def evaluate(
        self,
        request: KnowledgeVersionProjectionRequest,
    ) -> KnowledgeVersionProjectionEvaluation:
        decision = request.resolution_decision
        if request.attempts_in_place_mutation:
            return self._blocked("material_knowledge_object_state_in_place_forbidden")
        if (
            request.attempts_predecessor_supersession
            and request.prior_publication_state == "unpublished"
        ):
            return self._blocked("unpublished_predecessor_cannot_be_superseded")
        no_version_resolution = decision.resolution_type in {
            "map_to_existing_without_new_version",
            "close_without_canonicalization",
        }
        if request.material_change and no_version_resolution:
            return self._blocked("material_delta_requires_new_version")
        if (
            request.material_change
            and not request.planned_target_knowledge_object_version_ref
        ):
            return self._blocked("planned_target_knowledge_version_missing")
        if (
            not request.material_change
            and request.planned_target_knowledge_object_version_ref
        ):
            return self._blocked("no_material_delta_cannot_plan_new_version")
        if request.material_change and not request.same_knowledge_object_identity:
            return self._blocked("knowledge_object_same_object_assessment_required")

        payload = {
            "resolution_decision_ref": decision.resolution_decision_ref,
            "stable_knowledge_object_ref": request.stable_knowledge_object_ref,
            "prior_knowledge_object_version_ref": (
                request.prior_knowledge_object_version_ref
            ),
            "prior_publication_state": request.prior_publication_state,
            "planned_target_knowledge_object_version_ref": (
                request.planned_target_knowledge_object_version_ref
            ),
            "same_knowledge_object_identity": request.same_knowledge_object_identity,
            "new_version_required": request.material_change,
            "prior_version_effect": "unchanged",
            "publication_status": "not_performed",
        }
        projection = KnowledgeVersionProjection(
            projection_ref=local_ref("KVP", payload),
            resolution_decision_ref=decision.resolution_decision_ref,
            stable_knowledge_object_ref=request.stable_knowledge_object_ref,
            prior_knowledge_object_version_ref=(
                request.prior_knowledge_object_version_ref
            ),
            prior_publication_state=request.prior_publication_state,
            planned_target_knowledge_object_version_ref=(
                request.planned_target_knowledge_object_version_ref
            ),
            same_knowledge_object_identity=request.same_knowledge_object_identity,
            new_version_required=request.material_change,
        )
        return KnowledgeVersionProjectionEvaluation(
            disposition="projected",
            reason_code="planned_knowledge_version_projected",
            projection=projection,
        )

    @staticmethod
    def _blocked(reason_code: str) -> KnowledgeVersionProjectionEvaluation:
        return KnowledgeVersionProjectionEvaluation(
            disposition="blocked",
            reason_code=reason_code,
        )
