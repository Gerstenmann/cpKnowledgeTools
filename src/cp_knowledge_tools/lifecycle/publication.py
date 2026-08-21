from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from cp_knowledge_tools.publication.contracts import (
    publication_unit_template_is_compatible,
)

from ._common import (
    canonical_json,
    content_hash,
    local_ref,
    ordered_unique,
)
from .resolution import (
    KnowledgeVersionProjection,
    LifecycleCandidateRevision,
    ResolutionDecision,
)
from .reviews import (
    ReviewRecord,
    ReviewRecordValidator,
    ReviewRequest,
    ReviewRequestFactory,
    ReviewRequirement,
    ReviewRequirementSet,
)

PUBLICATION_OPERATION_TYPES = frozenset(
    {
        "create_identity",
        "publish_new_version",
        "supersede_version",
        "retract_version",
        "archive_version",
        "deprecate_identity",
        "retire_identity",
        "merge_identities",
        "split_identity",
        "update_primary_context",
    }
)


@dataclass(frozen=True, slots=True)
class HashRuleBinding:
    """Explicit hash-rule authority supplied by the caller.

    D6 intentionally has no implicit production default. Synthetic fixtures must
    identify themselves so their hashes cannot be mistaken for an active
    productive approval under CPKS-SPEC-ARCH-INT.
    """

    algorithm: str
    canonicalization_profile_ref: str
    approval_context_ref: str
    synthetic_test_fixture: bool = False

    def validation_reason(self) -> str | None:
        if self.algorithm != "sha256":
            return "hash_algorithm_not_supported"
        if not self.canonicalization_profile_ref:
            return "canonicalization_profile_binding_missing"
        if not self.approval_context_ref:
            return "hash_rule_approval_context_missing"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "canonicalization_profile_ref": self.canonicalization_profile_ref,
            "approval_context_ref": self.approval_context_ref,
            "synthetic_test_fixture": self.synthetic_test_fixture,
        }


@dataclass(frozen=True, slots=True)
class IntegrityHash:
    algorithm: str
    canonicalization_profile: str
    hash_scope: str
    value: str
    approval_context_ref: str
    synthetic_test_fixture: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "canonicalization_profile": self.canonicalization_profile,
            "hash_scope": self.hash_scope,
            "value": self.value,
            "approval_context_ref": self.approval_context_ref,
            "synthetic_test_fixture": self.synthetic_test_fixture,
        }


def _integrity_hash(
    value: Any,
    *,
    scope: str,
    binding: HashRuleBinding,
) -> IntegrityHash:
    reason = binding.validation_reason()
    if reason:
        raise ValueError(reason)
    return IntegrityHash(
        algorithm=binding.algorithm,
        canonicalization_profile=binding.canonicalization_profile_ref,
        hash_scope=scope,
        value=content_hash(value),
        approval_context_ref=binding.approval_context_ref,
        synthetic_test_fixture=binding.synthetic_test_fixture,
    )


KNOWLEDGE_CONTENT_MANIFEST_FIELDS = (
    "document_type",
    "schema_ref",
    "semantic_model_ref",
    "vocabulary_set_ref",
    "knowledge_object_id",
    "knowledge_object_version",
    "title",
    "language",
    "primary_kind",
    "knowledge_functions",
    "applicability",
    "profile_refs",
    "claims",
    "events",
    "event_participations",
    "evidence_links",
    "structural_relationships",
    "conflict_sets",
    "policy_anchors",
    "cross_view_mappings",
    "human_readable",
)
HARDENING_KNOWLEDGE_CONTENT_MANIFEST_FIELDS = (
    "evidence_assessments",
    "temporal_constraints",
)

INITIAL_PUBLICATION_FINALIZATION_FIELDS = (
    "canonical_path",
    "publication.publication_state",
    "publication.publication_record_ref",
    "publication.published_at",
    "publication.publisher_ref",
    "publication.predecessor_publication_ref",
)

PUBLICATION_FINALIZATION_POSTCONDITIONS = (
    "knowledge_content_hash_unchanged",
    "target_canonical_path_matches",
    "final_representation_hash_recorded",
    "publication_record_valid",
    "no_uncompensated_partial_visibility",
)


def _markdown_without_publication_section(
    markdown_body: str,
    publication_anchor: str,
) -> str:
    marker = f'<a id="{publication_anchor}"></a>'
    lines = markdown_body.splitlines(keepends=True)
    try:
        start = next(
            index for index, line in enumerate(lines) if line.rstrip("\r\n") == marker
        )
    except StopIteration as exc:
        raise ValueError("publication_anchor_section_missing") from exc

    end = len(lines)
    for index in range(start + 1, len(lines) - 1):
        if lines[index].startswith('<a id="') and lines[index + 1].startswith("## "):
            end = index
            break
    return "".join((*lines[:start], *lines[end:]))


def _knowledge_content_projection(
    manifest: dict[str, Any],
    markdown_body: str,
) -> dict[str, Any]:
    human_readable = manifest.get("human_readable")
    if not isinstance(human_readable, dict) or not human_readable.get(
        "publication_anchor"
    ):
        raise ValueError("publication_anchor_missing")

    projection = {
        field: deepcopy(manifest.get(field))
        for field in KNOWLEDGE_CONTENT_MANIFEST_FIELDS
    }
    if manifest.get("schema_ref") == "CPKS-SPEC-KM-PU@0.3":
        projection.update(
            {
                field: deepcopy(manifest.get(field))
                for field in HARDENING_KNOWLEDGE_CONTENT_MANIFEST_FIELDS
            }
        )
    policy_anchors = projection.get("policy_anchors")
    if isinstance(policy_anchors, list):
        for anchor in policy_anchors:
            if isinstance(anchor, dict):
                anchor.pop("policy_decision_refs", None)
    projection["markdown_body"] = _markdown_without_publication_section(
        markdown_body,
        str(human_readable["publication_anchor"]),
    )
    return projection


def publication_unit_knowledge_content_hash(
    manifest: dict[str, Any],
    markdown_body: str,
    hash_rule_binding: HashRuleBinding,
) -> IntegrityHash:
    return _integrity_hash(
        _knowledge_content_projection(manifest, markdown_body),
        scope="publication_unit_knowledge_content",
        binding=hash_rule_binding,
    )


def publication_unit_representation_hash(
    manifest: dict[str, Any],
    markdown_body: str,
    hash_rule_binding: HashRuleBinding,
    *,
    scope: Literal[
        "publication_unit_prepublication_representation",
        "publication_unit_final_representation",
    ],
) -> IntegrityHash:
    return _integrity_hash(
        {
            "manifest": json.loads(canonical_json(manifest)),
            "markdown_body": markdown_body,
        },
        scope=scope,
        binding=hash_rule_binding,
    )


@dataclass(frozen=True, slots=True)
class ExpectedPriorState:
    stable_knowledge_object_ref: str
    knowledge_object_version_ref: str
    publication_state: str
    stable_identity_state: str
    subject_state_refs: tuple[str, ...]
    expected_content_hashes: tuple[tuple[str, str], ...]
    candidate_revision_ref: str
    resolution_decision_ref: str
    required_candidate_review_refs: tuple[str, ...]
    profile_context_input_refs: tuple[str, ...]
    policy_context_input_refs: tuple[str, ...]
    no_competing_change_set: bool

    def validation_reason(self) -> str | None:
        required_strings = (
            self.stable_knowledge_object_ref,
            self.knowledge_object_version_ref,
            self.publication_state,
            self.stable_identity_state,
            self.candidate_revision_ref,
            self.resolution_decision_ref,
        )
        if not all(required_strings):
            return "expected_prior_state_incomplete"
        if not self.expected_content_hashes:
            return "expected_prior_content_hash_missing"
        if not self.required_candidate_review_refs:
            return "expected_prior_candidate_reviews_missing"
        if not self.profile_context_input_refs:
            return "expected_prior_profile_context_missing"
        if not self.policy_context_input_refs:
            return "expected_prior_policy_context_missing"
        if not self.no_competing_change_set:
            return "competing_change_set_precondition_failed"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_knowledge_object_ref": self.stable_knowledge_object_ref,
            "knowledge_object_version_ref": self.knowledge_object_version_ref,
            "publication_state": self.publication_state,
            "stable_identity_state": self.stable_identity_state,
            "subject_state_refs": list(self.subject_state_refs),
            "expected_content_hashes": [
                {"subject_ref": subject_ref, "value": value}
                for subject_ref, value in self.expected_content_hashes
            ],
            "candidate_revision_ref": self.candidate_revision_ref,
            "resolution_decision_ref": self.resolution_decision_ref,
            "required_candidate_review_refs": list(self.required_candidate_review_refs),
            "profile_context_input_refs": list(self.profile_context_input_refs),
            "policy_context_input_refs": list(self.policy_context_input_refs),
            "no_competing_change_set": self.no_competing_change_set,
        }


@dataclass(frozen=True, slots=True)
class PublicationOperation:
    operation_type: str
    subject_refs: tuple[str, ...]
    target_version_refs: tuple[str, ...]
    atomic_effect_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_type": self.operation_type,
            "subject_refs": list(self.subject_refs),
            "target_version_refs": list(self.target_version_refs),
            "atomic_effect_ref": self.atomic_effect_ref,
        }


@dataclass(frozen=True, slots=True)
class PublicationChangeSetBuildRequest:
    candidate_revision: LifecycleCandidateRevision | None
    resolution_decision: ResolutionDecision | None
    knowledge_version_projection: KnowledgeVersionProjection | None
    operations: tuple[PublicationOperation, ...]
    expected_prior_states: tuple[ExpectedPriorState, ...]
    candidate_review_record_refs: tuple[str, ...]
    conformance_report_refs: tuple[str, ...]
    idempotency_key: str
    rollback_or_compensation_plan_ref: str | None
    created_by: str
    created_at: str
    hash_rule_binding: HashRuleBinding
    additional_candidate_revision_refs: tuple[str, ...] = ()
    existing_idempotency_fingerprint: str | None = None
    publication_finalization_plan_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublicationChangeSet:
    publication_change_set_ref: str
    change_set_version: str
    candidate_ref: str
    candidate_revision_ref: str
    resolution_decision_ref: str
    operations: tuple[PublicationOperation, ...]
    affected_canonical_refs: tuple[str, ...]
    new_publication_unit_refs: tuple[str, ...]
    expected_prior_states: tuple[ExpectedPriorState, ...]
    review_record_refs: tuple[str, ...]
    policy_decision_ref: str | None
    conformance_report_refs: tuple[str, ...]
    publication_finalization_plan_refs: tuple[str, ...]
    publication_authority_ref: str | None
    idempotency_key: str
    rollback_or_compensation_plan_ref: str
    created_by: str
    created_at: str
    change_set_hash: IntegrityHash
    request_fingerprint: str
    atomic: bool = True
    state: str = "awaiting_reviews"
    contract_version: str = "0.1"
    execution_performed: bool = False
    publication_performed: bool = False

    @property
    def change_set_version_ref(self) -> str:
        return f"{self.publication_change_set_ref}@{self.change_set_version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Publication Change Set Contract",
            "contract_version": self.contract_version,
            "publication_change_set_ref": self.publication_change_set_ref,
            "change_set_version": self.change_set_version,
            "change_set_version_ref": self.change_set_version_ref,
            "candidate_ref": self.candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "resolution_decision_ref": self.resolution_decision_ref,
            "operations": [item.to_dict() for item in self.operations],
            "affected_canonical_refs": list(self.affected_canonical_refs),
            "new_publication_unit_refs": list(self.new_publication_unit_refs),
            "expected_prior_states": [
                item.to_dict() for item in self.expected_prior_states
            ],
            "review_record_refs": list(self.review_record_refs),
            "policy_decision_ref": self.policy_decision_ref,
            "conformance_report_refs": list(self.conformance_report_refs),
            "publication_finalization_plan_refs": list(
                self.publication_finalization_plan_refs
            ),
            "publication_authority_ref": self.publication_authority_ref,
            "idempotency_key": self.idempotency_key,
            "rollback_or_compensation_plan_ref": (
                self.rollback_or_compensation_plan_ref
            ),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "change_set_hash": self.change_set_hash.to_dict(),
            "request_fingerprint": self.request_fingerprint,
            "atomic": self.atomic,
            "state": self.state,
            "execution_performed": self.execution_performed,
            "publication_performed": self.publication_performed,
        }


@dataclass(frozen=True, slots=True)
class PublicationChangeSetBuildEvaluation:
    disposition: Literal["built", "not_required", "blocked"]
    reason_code: str
    change_set: PublicationChangeSet | None = None


class PublicationChangeSetBuilder:
    def build(
        self,
        request: PublicationChangeSetBuildRequest,
    ) -> PublicationChangeSetBuildEvaluation:
        candidate = request.candidate_revision
        decision = request.resolution_decision
        if candidate is None:
            return self._blocked("candidate_revision_missing")
        if decision is None:
            return self._blocked("resolution_decision_missing")
        if decision.candidate_ref != candidate.lifecycle_candidate_ref or (
            decision.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
        ):
            return self._blocked("resolution_candidate_revision_mismatch")
        if decision.publication_status != "not_performed":
            return self._blocked("resolution_already_claims_publication")
        if decision.resolution_type in {
            "map_to_existing_without_new_version",
            "close_without_canonicalization",
        }:
            if request.knowledge_version_projection is None and not request.operations:
                return PublicationChangeSetBuildEvaluation(
                    disposition="not_required",
                    reason_code="resolution_has_no_material_publication",
                )
            return self._blocked("non_material_resolution_has_publication_effect")
        if request.additional_candidate_revision_refs:
            return self._blocked("independent_candidates_cannot_share_change_set")
        if not request.candidate_review_record_refs:
            return self._blocked("candidate_reviews_missing")
        if not request.conformance_report_refs:
            return self._blocked("conformance_reports_missing")
        if len(ordered_unique(request.publication_finalization_plan_refs)) != 1:
            return self._blocked("publication_finalization_plan_binding_invalid")
        if not request.rollback_or_compensation_plan_ref:
            return self._blocked("rollback_or_compensation_plan_missing")
        if not request.idempotency_key:
            return self._blocked("idempotency_key_missing")
        if not request.created_by or not request.created_at:
            return self._blocked("change_set_provenance_missing")
        hash_reason = request.hash_rule_binding.validation_reason()
        if hash_reason:
            return self._blocked(hash_reason)

        projection = request.knowledge_version_projection
        if projection is None:
            return self._blocked("knowledge_version_projection_missing")
        if (
            projection.resolution_decision_ref != decision.resolution_decision_ref
            or projection.publication_status != "not_performed"
            or not projection.immutable
        ):
            return self._blocked("knowledge_version_projection_mismatch")
        target_version = projection.planned_target_knowledge_object_version_ref
        if not projection.new_version_required or not target_version:
            return self._blocked("new_publication_unit_projection_missing")
        if not request.operations:
            return self._blocked("publication_operations_missing")
        if any(
            item.operation_type not in PUBLICATION_OPERATION_TYPES
            for item in request.operations
        ):
            return self._blocked("publication_operation_not_allowed")
        if any(
            item.atomic_effect_ref != candidate.lifecycle_candidate_revision_ref
            for item in request.operations
        ):
            return self._blocked("change_set_atomic_candidate_binding_mismatch")

        operation_types = {item.operation_type for item in request.operations}
        if "publish_new_version" not in operation_types:
            return self._blocked("publish_new_version_operation_missing")
        if decision.resolution_type == "create_new_identity" and (
            "create_identity" not in operation_types
        ):
            return self._blocked("create_identity_operation_missing")
        if decision.resolution_type == "revise_existing_identity" and (
            "create_identity" in operation_types
        ):
            return self._blocked("existing_identity_revision_cannot_create_identity")
        if "supersede_version" in operation_types and any(
            item.publication_state == "unpublished"
            for item in request.expected_prior_states
        ):
            return self._blocked("unpublished_predecessor_cannot_be_superseded")
        if not any(
            target_version in item.target_version_refs
            for item in request.operations
            if item.operation_type == "publish_new_version"
        ):
            return self._blocked("projected_publication_unit_operation_missing")
        if not request.expected_prior_states:
            return self._blocked("expected_prior_states_missing")
        for prior in request.expected_prior_states:
            reason = prior.validation_reason()
            if reason:
                return self._blocked(reason)
            if (
                prior.candidate_revision_ref
                != candidate.lifecycle_candidate_revision_ref
                or prior.resolution_decision_ref != decision.resolution_decision_ref
            ):
                return self._blocked("expected_prior_state_binding_mismatch")
            if not set(request.candidate_review_record_refs).issubset(
                prior.required_candidate_review_refs
            ):
                return self._blocked("expected_prior_candidate_review_mismatch")

        request_payload = {
            "candidate_ref": candidate.lifecycle_candidate_ref,
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "resolution_decision_ref": decision.resolution_decision_ref,
            "projection": projection.to_dict(),
            "operations": [item.to_dict() for item in request.operations],
            "expected_prior_states": [
                item.to_dict() for item in request.expected_prior_states
            ],
            "candidate_review_record_refs": list(
                ordered_unique(request.candidate_review_record_refs)
            ),
            "conformance_report_refs": list(
                ordered_unique(request.conformance_report_refs)
            ),
            "publication_finalization_plan_refs": list(
                ordered_unique(request.publication_finalization_plan_refs)
            ),
            "idempotency_key": request.idempotency_key,
            "rollback_or_compensation_plan_ref": (
                request.rollback_or_compensation_plan_ref
            ),
            "created_by": request.created_by,
            "created_at": request.created_at,
            "hash_rule_binding": request.hash_rule_binding.to_dict(),
        }
        fingerprint = content_hash(request_payload)
        if request.existing_idempotency_fingerprint and (
            request.existing_idempotency_fingerprint != fingerprint
        ):
            return self._blocked("idempotency_conflict")

        change_set_ref = local_ref(
            "PCS",
            {
                "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
                "resolution_decision_ref": decision.resolution_decision_ref,
                "idempotency_key": request.idempotency_key,
            },
        )
        hash_payload = {
            "publication_change_set_ref": change_set_ref,
            "change_set_version": "0.1",
            **request_payload,
            "affected_canonical_refs": list(
                ordered_unique(
                    (
                        *decision.target_canonical_refs,
                        projection.stable_knowledge_object_ref,
                    )
                )
            ),
            "new_publication_unit_refs": [target_version],
            "policy_decision_ref": None,
            "publication_authority_ref": None,
            "atomic": True,
            "state": "awaiting_reviews",
        }
        change_set = PublicationChangeSet(
            publication_change_set_ref=change_set_ref,
            change_set_version="0.1",
            candidate_ref=candidate.lifecycle_candidate_ref,
            candidate_revision_ref=candidate.lifecycle_candidate_revision_ref,
            resolution_decision_ref=decision.resolution_decision_ref,
            operations=tuple(request.operations),
            affected_canonical_refs=ordered_unique(
                (
                    *decision.target_canonical_refs,
                    projection.stable_knowledge_object_ref,
                )
            ),
            new_publication_unit_refs=(target_version,),
            expected_prior_states=tuple(request.expected_prior_states),
            review_record_refs=ordered_unique(request.candidate_review_record_refs),
            policy_decision_ref=None,
            conformance_report_refs=ordered_unique(request.conformance_report_refs),
            publication_finalization_plan_refs=ordered_unique(
                request.publication_finalization_plan_refs
            ),
            publication_authority_ref=None,
            idempotency_key=request.idempotency_key,
            rollback_or_compensation_plan_ref=(
                request.rollback_or_compensation_plan_ref
            ),
            created_by=request.created_by,
            created_at=request.created_at,
            change_set_hash=_integrity_hash(
                hash_payload,
                scope="publication_change_set_version",
                binding=request.hash_rule_binding,
            ),
            request_fingerprint=fingerprint,
        )
        return PublicationChangeSetBuildEvaluation(
            disposition="built",
            reason_code="publication_change_set_built",
            change_set=change_set,
        )

    @staticmethod
    def _blocked(reason_code: str) -> PublicationChangeSetBuildEvaluation:
        return PublicationChangeSetBuildEvaluation(
            disposition="blocked",
            reason_code=reason_code,
        )


@dataclass(frozen=True, slots=True)
class PublicationUnitBinding:
    publication_unit_ref: str
    knowledge_object_id: str
    knowledge_object_version: str
    publication_state: str
    profile_refs: tuple[str, ...]
    semantic_subject_refs: tuple[str, ...]
    evidence_link_refs: tuple[str, ...]
    conflict_set_refs: tuple[str, ...]
    cross_view_validation_status: str
    publication_finalization_plan_ref: str
    canonical_path: str | None
    _manifest_json: str
    markdown_body: str
    content_hash: IntegrityHash
    prepublication_representation_hash: IntegrityHash

    @classmethod
    def create(
        cls,
        *,
        manifest: dict[str, Any],
        markdown_body: str,
        hash_rule_binding: HashRuleBinding,
    ) -> PublicationUnitBinding:
        reason = hash_rule_binding.validation_reason()
        if reason:
            raise ValueError(reason)
        knowledge_object_id = str(manifest.get("knowledge_object_id", ""))
        knowledge_object_version = str(manifest.get("knowledge_object_version", ""))
        publication = manifest.get("publication", {})
        integrity = manifest.get("integrity", {})
        cross_view = (
            integrity.get("cross_view_validation", {})
            if isinstance(integrity, dict)
            else {}
        )
        publication_state = (
            str(publication.get("publication_state", ""))
            if isinstance(publication, dict)
            else ""
        )
        cross_view_status = (
            str(cross_view.get("status", "")) if isinstance(cross_view, dict) else ""
        )
        if not knowledge_object_id or not knowledge_object_version:
            raise ValueError("publication_unit_identity_missing")
        if not publication_unit_template_is_compatible(
            str(manifest.get("schema_ref", "")),
            str(manifest.get("template_ref", "")),
        ):
            raise ValueError("publication_unit_template_incompatible")
        if publication_state != "unpublished":
            raise ValueError("d6_publication_unit_must_be_unpublished")
        finalization_plan_ref = (
            str(publication.get("publication_finalization_plan_ref", ""))
            if isinstance(publication, dict)
            else ""
        )
        if not finalization_plan_ref:
            raise ValueError("publication_finalization_plan_ref_missing")
        if manifest.get("canonical_path") is not None:
            raise ValueError("unpublished_publication_unit_canonical_path_must_be_null")
        if cross_view_status != "pass":
            raise ValueError("publication_unit_cross_view_validation_not_passed")

        claims = manifest.get("claims", [])
        events = manifest.get("events", [])
        semantic_refs: list[str] = []
        for claim in claims if isinstance(claims, list) else []:
            if isinstance(claim, dict):
                ref = claim.get("claim_ref", {})
                if isinstance(ref, dict) and ref.get("stable_id"):
                    semantic_refs.append(str(ref["stable_id"]))
        for event in events if isinstance(events, list) else []:
            if isinstance(event, dict):
                ref = event.get("event_ref", {})
                if isinstance(ref, dict) and ref.get("stable_id"):
                    semantic_refs.append(str(ref["stable_id"]))
        if not semantic_refs:
            raise ValueError("publication_unit_semantic_subjects_missing")

        evidence_refs = tuple(
            str(item["evidence_link_id"])
            for item in manifest.get("evidence_links", [])
            if isinstance(item, dict) and item.get("evidence_link_id")
        )
        conflict_refs = tuple(
            str(item.get("conflict_set_id") or item.get("conflict_set_ref"))
            for item in manifest.get("conflict_sets", [])
            if isinstance(item, dict)
            and (item.get("conflict_set_id") or item.get("conflict_set_ref"))
        )
        bound_manifest = deepcopy(manifest)
        unit_hash = publication_unit_knowledge_content_hash(
            bound_manifest,
            markdown_body,
            hash_rule_binding,
        )
        integrity = bound_manifest.setdefault("integrity", {})
        if not isinstance(integrity, dict):
            raise ValueError("publication_unit_integrity_invalid")
        supplied_hash = integrity.get("content_hash")
        if supplied_hash not in (None, unit_hash.to_dict()):
            raise ValueError("publication_unit_knowledge_content_hash_mismatch")
        integrity["content_hash"] = unit_hash.to_dict()
        canonical_manifest = canonical_json(bound_manifest)
        prepublication_hash = publication_unit_representation_hash(
            bound_manifest,
            markdown_body,
            hash_rule_binding,
            scope="publication_unit_prepublication_representation",
        )
        return cls(
            publication_unit_ref=f"{knowledge_object_id}@{knowledge_object_version}",
            knowledge_object_id=knowledge_object_id,
            knowledge_object_version=knowledge_object_version,
            publication_state=publication_state,
            profile_refs=ordered_unique(
                str(item) for item in manifest.get("profile_refs", [])
            ),
            semantic_subject_refs=ordered_unique(semantic_refs),
            evidence_link_refs=ordered_unique(evidence_refs),
            conflict_set_refs=ordered_unique(conflict_refs),
            cross_view_validation_status=cross_view_status,
            publication_finalization_plan_ref=finalization_plan_ref,
            canonical_path=None,
            _manifest_json=canonical_manifest,
            markdown_body=markdown_body,
            content_hash=unit_hash,
            prepublication_representation_hash=prepublication_hash,
        )

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "publication_unit_ref": self.publication_unit_ref,
            "knowledge_object_id": self.knowledge_object_id,
            "knowledge_object_version": self.knowledge_object_version,
            "publication_state": self.publication_state,
            "profile_refs": list(self.profile_refs),
            "semantic_subject_refs": list(self.semantic_subject_refs),
            "evidence_link_refs": list(self.evidence_link_refs),
            "conflict_set_refs": list(self.conflict_set_refs),
            "cross_view_validation_status": self.cross_view_validation_status,
            "publication_finalization_plan_ref": (
                self.publication_finalization_plan_ref
            ),
            "canonical_path": self.canonical_path,
            "manifest": self.manifest,
            "markdown_body": self.markdown_body,
            "content_hash": self.content_hash.to_dict(),
            "prepublication_representation_hash": (
                self.prepublication_representation_hash.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class PublicationFinalizationPlan:
    publication_finalization_plan_ref: str
    publication_unit_ref: str
    knowledge_object_id: str
    knowledge_object_version: str
    knowledge_content_hash: IntegrityHash
    prepublication_representation_hash: IntegrityHash
    publication_change_set_ref: str
    publication_package_ref: str
    expected_source_publication_state: str
    expected_source_canonical_path: str | None
    canonical_path: str
    maintenance_context_ref: str
    target_publication_state: str
    publisher_ref: str
    executor_ref: str
    publication_authority_ref: str
    review_record_refs: tuple[str, ...]
    policy_decision_refs: tuple[str, ...]
    planned_publication_record_ref: str
    predecessor_publication_ref: str | None
    finalization_method_ref: str
    allowed_finalization_fields: tuple[str, ...]
    publication_anchor: str
    published_at_source: str
    final_representation_hash_scope: str
    required_postconditions: tuple[str, ...]
    created_by: str
    created_at: str
    plan_hash: IntegrityHash
    contract_version: str = "0.1"

    @classmethod
    def create(
        cls,
        *,
        publication_finalization_plan_ref: str,
        publication_unit: PublicationUnitBinding,
        publication_change_set_ref: str,
        publication_package_ref: str,
        canonical_path: str,
        maintenance_context_ref: str,
        publisher_ref: str,
        executor_ref: str,
        publication_authority_ref: str,
        review_record_refs: tuple[str, ...],
        policy_decision_refs: tuple[str, ...],
        planned_publication_record_ref: str,
        predecessor_publication_ref: str | None,
        finalization_method_ref: str,
        created_by: str,
        created_at: str,
        hash_rule_binding: HashRuleBinding,
    ) -> PublicationFinalizationPlan:
        required = (
            publication_finalization_plan_ref,
            publication_change_set_ref,
            publication_package_ref,
            canonical_path,
            maintenance_context_ref,
            publisher_ref,
            executor_ref,
            publication_authority_ref,
            planned_publication_record_ref,
            finalization_method_ref,
            created_by,
            created_at,
        )
        if not all(required):
            raise ValueError("publication_finalization_plan_incomplete")
        if (
            publication_unit.publication_finalization_plan_ref
            != publication_finalization_plan_ref
        ):
            raise ValueError("publication_finalization_plan_unit_binding_mismatch")
        if publication_unit.publication_state != "unpublished":
            raise ValueError("publication_finalization_source_state_invalid")
        if publication_unit.canonical_path is not None:
            raise ValueError("publication_finalization_source_path_invalid")
        if not review_record_refs:
            raise ValueError("publication_finalization_review_binding_missing")
        if not policy_decision_refs:
            raise ValueError("publication_finalization_policy_binding_missing")

        publication_anchor = str(
            publication_unit.manifest["human_readable"]["publication_anchor"]
        )
        allowed_fields = (
            *INITIAL_PUBLICATION_FINALIZATION_FIELDS,
            f"markdown_section:{publication_anchor}",
        )
        payload = {
            "contract_name": "Publication Finalization Plan",
            "contract_version": "0.1",
            "publication_finalization_plan_ref": (publication_finalization_plan_ref),
            "publication_unit_ref": publication_unit.publication_unit_ref,
            "knowledge_object_id": publication_unit.knowledge_object_id,
            "knowledge_object_version": publication_unit.knowledge_object_version,
            "knowledge_content_hash": publication_unit.content_hash.to_dict(),
            "prepublication_representation_hash": (
                publication_unit.prepublication_representation_hash.to_dict()
            ),
            "publication_change_set_ref": publication_change_set_ref,
            "publication_package_ref": publication_package_ref,
            "expected_source_state": {
                "publication_state": "unpublished",
                "canonical_path": None,
            },
            "target": {
                "canonical_path": canonical_path,
                "maintenance_context_ref": maintenance_context_ref,
            },
            "target_publication_state": "published",
            "publisher_ref": publisher_ref,
            "executor_ref": executor_ref,
            "publication_authority_ref": publication_authority_ref,
            "review_record_refs": list(ordered_unique(review_record_refs)),
            "policy_decision_refs": list(ordered_unique(policy_decision_refs)),
            "planned_publication_record_ref": planned_publication_record_ref,
            "predecessor_publication_ref": predecessor_publication_ref,
            "finalization_method_ref": finalization_method_ref,
            "allowed_finalization_fields": list(allowed_fields),
            "published_at_source": "transaction_commit_time",
            "final_representation_hash_contract": {
                "hash_scope": "publication_unit_final_representation",
                "record_location": "publication_record",
            },
            "required_postconditions": list(PUBLICATION_FINALIZATION_POSTCONDITIONS),
            "created_by": created_by,
            "created_at": created_at,
        }
        return cls(
            publication_finalization_plan_ref=publication_finalization_plan_ref,
            publication_unit_ref=publication_unit.publication_unit_ref,
            knowledge_object_id=publication_unit.knowledge_object_id,
            knowledge_object_version=publication_unit.knowledge_object_version,
            knowledge_content_hash=publication_unit.content_hash,
            prepublication_representation_hash=(
                publication_unit.prepublication_representation_hash
            ),
            publication_change_set_ref=publication_change_set_ref,
            publication_package_ref=publication_package_ref,
            expected_source_publication_state="unpublished",
            expected_source_canonical_path=None,
            canonical_path=canonical_path,
            maintenance_context_ref=maintenance_context_ref,
            target_publication_state="published",
            publisher_ref=publisher_ref,
            executor_ref=executor_ref,
            publication_authority_ref=publication_authority_ref,
            review_record_refs=ordered_unique(review_record_refs),
            policy_decision_refs=ordered_unique(policy_decision_refs),
            planned_publication_record_ref=planned_publication_record_ref,
            predecessor_publication_ref=predecessor_publication_ref,
            finalization_method_ref=finalization_method_ref,
            allowed_finalization_fields=allowed_fields,
            publication_anchor=publication_anchor,
            published_at_source="transaction_commit_time",
            final_representation_hash_scope=("publication_unit_final_representation"),
            required_postconditions=PUBLICATION_FINALIZATION_POSTCONDITIONS,
            created_by=created_by,
            created_at=created_at,
            plan_hash=_integrity_hash(
                payload,
                scope="publication_finalization_plan",
                binding=hash_rule_binding,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Publication Finalization Plan",
            "contract_version": self.contract_version,
            "publication_finalization_plan_ref": (
                self.publication_finalization_plan_ref
            ),
            "publication_unit_ref": self.publication_unit_ref,
            "knowledge_object_id": self.knowledge_object_id,
            "knowledge_object_version": self.knowledge_object_version,
            "knowledge_content_hash": self.knowledge_content_hash.to_dict(),
            "prepublication_representation_hash": (
                self.prepublication_representation_hash.to_dict()
            ),
            "publication_change_set_ref": self.publication_change_set_ref,
            "publication_package_ref": self.publication_package_ref,
            "expected_source_state": {
                "publication_state": self.expected_source_publication_state,
                "canonical_path": self.expected_source_canonical_path,
            },
            "target": {
                "canonical_path": self.canonical_path,
                "maintenance_context_ref": self.maintenance_context_ref,
            },
            "target_publication_state": self.target_publication_state,
            "publisher_ref": self.publisher_ref,
            "executor_ref": self.executor_ref,
            "publication_authority_ref": self.publication_authority_ref,
            "review_record_refs": list(self.review_record_refs),
            "policy_decision_refs": list(self.policy_decision_refs),
            "planned_publication_record_ref": (self.planned_publication_record_ref),
            "predecessor_publication_ref": self.predecessor_publication_ref,
            "finalization_method_ref": self.finalization_method_ref,
            "allowed_finalization_fields": list(self.allowed_finalization_fields),
            "published_at_source": self.published_at_source,
            "final_representation_hash_contract": {
                "hash_scope": self.final_representation_hash_scope,
                "record_location": "publication_record",
            },
            "required_postconditions": list(self.required_postconditions),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "plan_hash": self.plan_hash.to_dict(),
        }

    def integrity_ok(self) -> bool:
        try:
            payload = self.to_dict()
            payload.pop("plan_hash")
            return content_hash(payload) == self.plan_hash.value
        except AttributeError, KeyError, TypeError:
            return False


@dataclass(frozen=True, slots=True)
class PublicationPackageBuildRequest:
    candidate_revision: LifecycleCandidateRevision
    resolution_decision: ResolutionDecision
    change_set: PublicationChangeSet
    publication_unit_binding: PublicationUnitBinding
    candidate_review_record_refs: tuple[str, ...]
    conformance_report_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    policy_anchor_refs: tuple[str, ...]
    package_version: str
    created_by: str
    created_at: str
    hash_rule_binding: HashRuleBinding
    publication_finalization_plan: PublicationFinalizationPlan | None = None


@dataclass(frozen=True, slots=True)
class PublicationPackage:
    publication_package_ref: str
    package_version: str
    package_version_ref: str
    candidate_ref: str
    candidate_revision_ref: str
    resolution_decision_ref: str
    change_set: PublicationChangeSet
    publication_unit_binding: PublicationUnitBinding
    publication_finalization_plan: PublicationFinalizationPlan
    expected_prior_states: tuple[ExpectedPriorState, ...]
    candidate_review_record_refs: tuple[str, ...]
    conformance_report_refs: tuple[str, ...]
    recovery_plan_ref: str
    profile_refs: tuple[str, ...]
    policy_anchor_refs: tuple[str, ...]
    created_by: str
    created_at: str
    package_hash: IntegrityHash
    request_fingerprint: str
    state: str = "awaiting_publication_review"
    candidate_revision_immutable: bool = True
    execution_performed: bool = False
    publication_performed: bool = False
    contract_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Publication Package Contract",
            "contract_version": self.contract_version,
            "publication_package_ref": self.publication_package_ref,
            "package_version": self.package_version,
            "package_version_ref": self.package_version_ref,
            "candidate_ref": self.candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "resolution_decision_ref": self.resolution_decision_ref,
            "change_set": self.change_set.to_dict(),
            "publication_unit_binding": self.publication_unit_binding.to_dict(),
            "publication_finalization_plan": (
                self.publication_finalization_plan.to_dict()
            ),
            "expected_prior_states": [
                item.to_dict() for item in self.expected_prior_states
            ],
            "candidate_review_record_refs": list(self.candidate_review_record_refs),
            "conformance_report_refs": list(self.conformance_report_refs),
            "recovery_plan_ref": self.recovery_plan_ref,
            "profile_refs": list(self.profile_refs),
            "policy_anchor_refs": list(self.policy_anchor_refs),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "package_hash": self.package_hash.to_dict(),
            "request_fingerprint": self.request_fingerprint,
            "state": self.state,
            "candidate_revision_immutable": self.candidate_revision_immutable,
            "execution_performed": self.execution_performed,
            "publication_performed": self.publication_performed,
        }


@dataclass(frozen=True, slots=True)
class PublicationPackageBuildEvaluation:
    disposition: Literal["built", "blocked"]
    reason_code: str
    package: PublicationPackage | None = None


class PublicationPackageBuilder:
    def build(
        self,
        request: PublicationPackageBuildRequest,
    ) -> PublicationPackageBuildEvaluation:
        candidate = request.candidate_revision
        decision = request.resolution_decision
        change_set = request.change_set
        unit = request.publication_unit_binding
        plan = request.publication_finalization_plan
        if (
            change_set.candidate_ref != candidate.lifecycle_candidate_ref
            or change_set.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
            or decision.candidate_ref != candidate.lifecycle_candidate_ref
            or decision.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
            or change_set.resolution_decision_ref != decision.resolution_decision_ref
        ):
            return self._blocked("publication_package_candidate_binding_mismatch")
        if change_set.state != "awaiting_reviews" or (
            change_set.execution_performed or change_set.publication_performed
        ):
            return self._blocked("publication_change_set_state_not_packageable")
        if unit.publication_state != "unpublished":
            return self._blocked("d6_publication_unit_must_be_unpublished")
        expected_unit_ref = (
            f"{unit.knowledge_object_id}@{unit.knowledge_object_version}"
        )
        if (
            unit.publication_unit_ref != expected_unit_ref
            or unit.publication_unit_ref not in change_set.new_publication_unit_refs
        ):
            return self._blocked("publication_unit_version_resolution_mismatch")
        if unit.cross_view_validation_status != "pass":
            return self._blocked("publication_unit_cross_view_validation_not_passed")
        if unit.profile_refs != ordered_unique(request.profile_refs):
            return self._blocked("publication_unit_profile_binding_mismatch")
        if ordered_unique(request.candidate_review_record_refs) != (
            change_set.review_record_refs
        ):
            return self._blocked("candidate_review_binding_mismatch")
        if not request.conformance_report_refs:
            return self._blocked("conformance_reports_missing")
        if not set(change_set.conformance_report_refs).issubset(
            request.conformance_report_refs
        ):
            return self._blocked("conformance_report_binding_mismatch")
        if not request.policy_anchor_refs:
            return self._blocked("policy_anchor_refs_missing")
        if (
            not request.package_version
            or not request.created_by
            or not request.created_at
        ):
            return self._blocked("publication_package_provenance_missing")
        hash_reason = request.hash_rule_binding.validation_reason()
        if hash_reason:
            return self._blocked(hash_reason)

        package_ref = local_ref(
            "PPK",
            {
                "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
                "resolution_decision_ref": decision.resolution_decision_ref,
                "change_set_version_ref": change_set.change_set_version_ref,
            },
        )
        package_version_ref = f"{package_ref}@{request.package_version}"
        if plan is None:
            return self._blocked("publication_finalization_plan_missing")
        if not plan.integrity_ok():
            return self._blocked("publication_finalization_plan_integrity_invalid")
        if change_set.publication_finalization_plan_refs != (
            plan.publication_finalization_plan_ref,
        ):
            return self._blocked("publication_finalization_plan_change_set_mismatch")
        if unit.publication_finalization_plan_ref != (
            plan.publication_finalization_plan_ref
        ):
            return self._blocked("publication_finalization_plan_unit_mismatch")
        if (
            plan.publication_unit_ref != unit.publication_unit_ref
            or plan.knowledge_object_id != unit.knowledge_object_id
            or plan.knowledge_object_version != unit.knowledge_object_version
            or plan.knowledge_content_hash != unit.content_hash
            or plan.prepublication_representation_hash
            != unit.prepublication_representation_hash
        ):
            return self._blocked("publication_finalization_plan_hash_binding_mismatch")
        if (
            plan.publication_change_set_ref != change_set.publication_change_set_ref
            or plan.publication_package_ref != package_ref
        ):
            return self._blocked("publication_finalization_plan_package_mismatch")
        if plan.review_record_refs != ordered_unique(
            request.candidate_review_record_refs
        ):
            return self._blocked("publication_finalization_plan_review_mismatch")
        request_payload = {
            "publication_package_ref": package_ref,
            "package_version": request.package_version,
            "package_version_ref": package_version_ref,
            "candidate_ref": candidate.lifecycle_candidate_ref,
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "resolution_decision_ref": decision.resolution_decision_ref,
            "change_set": change_set.to_dict(),
            "publication_unit_binding": unit.to_dict(),
            "publication_finalization_plan": plan.to_dict(),
            "expected_prior_states": [
                item.to_dict() for item in change_set.expected_prior_states
            ],
            "candidate_review_record_refs": list(
                ordered_unique(request.candidate_review_record_refs)
            ),
            "conformance_report_refs": list(
                ordered_unique(request.conformance_report_refs)
            ),
            "recovery_plan_ref": change_set.rollback_or_compensation_plan_ref,
            "profile_refs": list(ordered_unique(request.profile_refs)),
            "policy_anchor_refs": list(ordered_unique(request.policy_anchor_refs)),
            "created_by": request.created_by,
            "created_at": request.created_at,
            "hash_rule_binding": request.hash_rule_binding.to_dict(),
            "state": "awaiting_publication_review",
            "candidate_revision_immutable": True,
        }
        fingerprint = content_hash(request_payload)
        package_hash = _integrity_hash(
            request_payload,
            scope="publication_package_version",
            binding=request.hash_rule_binding,
        )
        package = PublicationPackage(
            publication_package_ref=package_ref,
            package_version=request.package_version,
            package_version_ref=package_version_ref,
            candidate_ref=candidate.lifecycle_candidate_ref,
            candidate_revision_ref=candidate.lifecycle_candidate_revision_ref,
            resolution_decision_ref=decision.resolution_decision_ref,
            change_set=change_set,
            publication_unit_binding=unit,
            publication_finalization_plan=plan,
            expected_prior_states=change_set.expected_prior_states,
            candidate_review_record_refs=ordered_unique(
                request.candidate_review_record_refs
            ),
            conformance_report_refs=ordered_unique(request.conformance_report_refs),
            recovery_plan_ref=change_set.rollback_or_compensation_plan_ref,
            profile_refs=ordered_unique(request.profile_refs),
            policy_anchor_refs=ordered_unique(request.policy_anchor_refs),
            created_by=request.created_by,
            created_at=request.created_at,
            package_hash=package_hash,
            request_fingerprint=fingerprint,
        )
        return PublicationPackageBuildEvaluation(
            disposition="built",
            reason_code="publication_package_built",
            package=package,
        )

    @staticmethod
    def _blocked(reason_code: str) -> PublicationPackageBuildEvaluation:
        return PublicationPackageBuildEvaluation(
            disposition="blocked",
            reason_code=reason_code,
        )


class PublicationReviewFactory:
    def create(
        self,
        package: PublicationPackage,
        *,
        required_reviewer_authority: str,
        rule_basis_refs: tuple[str, ...],
        profile_refs: tuple[str, ...],
    ) -> tuple[ReviewRequirement, ReviewRequest]:
        review_scope = f"publication_package:{package.package_hash.value}"
        requirement_payload = {
            "review_type": "publication_review",
            "subject_ref": package.publication_package_ref,
            "subject_version": package.package_version_ref,
            "review_scope": review_scope,
            "required_reviewer_authority": required_reviewer_authority,
            "rule_basis_refs": list(ordered_unique(rule_basis_refs)),
            "profile_refs": list(ordered_unique(profile_refs)),
            "trigger": "publication_package_materialized",
            "blocking": True,
        }
        requirement = ReviewRequirement(
            review_requirement_ref=local_ref("RQR", requirement_payload),
            review_type="publication_review",
            subject_ref=package.publication_package_ref,
            subject_version=package.package_version_ref,
            review_scope=review_scope,
            required_reviewer_authority=required_reviewer_authority,
            rule_basis_refs=ordered_unique(rule_basis_refs),
            profile_refs=ordered_unique(profile_refs),
            trigger="publication_package_materialized",
            blocking=True,
        )
        requirement_set = ReviewRequirementSet(
            review_requirement_set_ref=local_ref(
                "RQS", {"requirement_ref": requirement.review_requirement_ref}
            ),
            candidate_ref=package.publication_package_ref,
            candidate_revision_ref=package.package_version_ref,
            requirements=(requirement,),
            routing_policy_ref="publication_package_review",
            candidate_level_only=False,
        )
        context_refs = ordered_unique(
            (
                package.candidate_revision_ref,
                package.resolution_decision_ref,
                package.change_set.change_set_version_ref,
                f"change_set_hash:{package.change_set.change_set_hash.value}",
                package.publication_unit_binding.publication_unit_ref,
                package.publication_finalization_plan.publication_finalization_plan_ref,
                (
                    "publication_finalization_plan_hash:"
                    f"{package.publication_finalization_plan.plan_hash.value}"
                ),
                (
                    "publication_unit_knowledge_content_hash:"
                    f"{package.publication_unit_binding.content_hash.value}"
                ),
                (
                    "publication_unit_prepublication_representation_hash:"
                    f"{package.publication_unit_binding.prepublication_representation_hash.value}"
                ),
                f"publication_target:{package.publication_finalization_plan.canonical_path}",
                f"maintenance_context:{package.publication_finalization_plan.maintenance_context_ref}",
                f"publication_authority:{package.publication_finalization_plan.publication_authority_ref}",
                f"publication_package_hash:{package.package_hash.value}",
            )
        )
        request = ReviewRequestFactory().create_requests(
            requirement_set,
            evidence_and_context_refs=context_refs,
            known_questions_gaps_conflicts=(),
        )[0]
        return requirement, request


@dataclass(frozen=True, slots=True)
class PublicationReviewValidation:
    disposition: Literal["accepted", "blocked"]
    reason_code: str
    review_record_ref: str | None = None
    publication_package_ref: str | None = None
    package_version_ref: str | None = None
    synthetic_test_publication_review_fixture: bool = False
    policy_permit_claimed: bool = False
    publication_authority_claimed: bool = False


class PublicationReviewValidator:
    def validate(
        self,
        record: ReviewRecord,
        request: ReviewRequest,
        requirement: ReviewRequirement,
        package: PublicationPackage,
        candidate: LifecycleCandidateRevision,
    ) -> PublicationReviewValidation:
        if not package.publication_finalization_plan.integrity_ok():
            return self._blocked("publication_review_stale")
        expected_requirement, expected_request = PublicationReviewFactory().create(
            package,
            required_reviewer_authority=requirement.required_reviewer_authority,
            rule_basis_refs=requirement.rule_basis_refs,
            profile_refs=requirement.profile_refs,
        )
        if requirement != expected_requirement or request != expected_request:
            return self._blocked("publication_review_stale")
        if requirement.review_type != "publication_review":
            return self._blocked("publication_review_type_required")
        validation = ReviewRecordValidator().validate(record, request, candidate)
        if validation.disposition != "accepted":
            return self._blocked(validation.reason_code)
        if record.result not in {"passed", "passed_with_conditions"}:
            return self._blocked("publication_review_not_passed")
        if record.result == "passed_with_conditions" and any(
            condition.state != "satisfied" for condition in record.conditions
        ):
            return self._blocked("publication_review_conditions_open")
        return PublicationReviewValidation(
            disposition="accepted",
            reason_code="publication_review_valid",
            review_record_ref=record.review_record_ref,
            publication_package_ref=package.publication_package_ref,
            package_version_ref=package.package_version_ref,
            synthetic_test_publication_review_fixture=record.synthetic_test_fixture,
        )

    @staticmethod
    def _blocked(reason_code: str) -> PublicationReviewValidation:
        return PublicationReviewValidation(
            disposition="blocked",
            reason_code=reason_code,
        )
