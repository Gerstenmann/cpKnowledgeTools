from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ._common import (
    canonical_json,
    content_hash,
    local_ref,
    ordered_unique,
)
from .resolution import LifecycleCandidateRevision

ReviewRoutingDisposition = Literal["routed", "blocked"]
ReviewValidationDisposition = Literal["accepted", "blocked"]

REVIEW_TYPES = frozenset(
    {
        "technical_validation",
        "source_and_evidence_review",
        "entity_and_identity_review",
        "domain_review",
        "privacy_and_security_review",
        "policy_review",
        "publication_review",
        "independent_quality_review",
    }
)
REVIEW_RESULTS = frozenset(
    {
        "passed",
        "passed_with_conditions",
        "changes_required",
        "failed",
        "not_applicable",
        "waived_by_authorized_policy",
    }
)
_FOREIGN_REVIEW_EFFECTS = frozenset(
    {
        "resolution_decision",
        "policy_permit",
        "policy_deny",
        "publication",
        "publication_authority",
        "publication_change_set",
    }
)


@dataclass(frozen=True, slots=True)
class ReviewRoutingPolicy:
    baseline_review_types: tuple[str, ...]
    _operation_requirements_json: str
    identity_sensitive_operations: frozenset[str]
    baseline_only_when_evidence_basis_unchanged: frozenset[str]
    policy_ref: str

    @classmethod
    def from_rules(
        cls,
        *,
        baseline_review_types: tuple[str, ...],
        operation_requirements: Mapping[str, tuple[str, ...]],
        identity_sensitive_operations: tuple[str, ...],
        baseline_only_when_evidence_basis_unchanged: tuple[str, ...],
        policy_ref: str,
    ) -> ReviewRoutingPolicy:
        values = {
            operation: list(ordered_unique(review_types))
            for operation, review_types in sorted(operation_requirements.items())
        }
        return cls(
            baseline_review_types=ordered_unique(baseline_review_types),
            _operation_requirements_json=canonical_json(values),
            identity_sensitive_operations=frozenset(identity_sensitive_operations),
            baseline_only_when_evidence_basis_unchanged=frozenset(
                baseline_only_when_evidence_basis_unchanged
            ),
            policy_ref=policy_ref,
        )

    @property
    def operation_requirements(self) -> dict[str, tuple[str, ...]]:
        values = json.loads(self._operation_requirements_json)
        return {key: tuple(items) for key, items in values.items()}


@dataclass(frozen=True, slots=True)
class ReviewRoutingContext:
    candidate_revision: LifecycleCandidateRevision
    semantic_change_operation: str
    same_object_relevant: bool
    identity_ambiguous: bool
    evidence_basis_only: bool
    privacy_or_security_triggered: bool
    evidence_and_context_refs: tuple[str, ...]
    known_questions_gaps_conflicts: tuple[str, ...]
    profile_refs: tuple[str, ...]
    rule_basis_refs: tuple[str, ...]
    authority_by_review_type: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ReviewRequirement:
    review_requirement_ref: str
    review_type: str
    subject_ref: str
    subject_version: str
    review_scope: str
    required_reviewer_authority: str
    rule_basis_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    trigger: str
    blocking: bool
    contract_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_requirement_ref": self.review_requirement_ref,
            "review_type": self.review_type,
            "subject_ref": self.subject_ref,
            "subject_version": self.subject_version,
            "review_scope": self.review_scope,
            "required_reviewer_authority": self.required_reviewer_authority,
            "rule_basis_refs": list(self.rule_basis_refs),
            "profile_refs": list(self.profile_refs),
            "trigger": self.trigger,
            "blocking": self.blocking,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class ReviewRequirementSet:
    review_requirement_set_ref: str
    candidate_ref: str
    candidate_revision_ref: str
    requirements: tuple[ReviewRequirement, ...]
    routing_policy_ref: str
    candidate_level_only: bool = True
    contract_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_requirement_set_ref": self.review_requirement_set_ref,
            "candidate_ref": self.candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "requirements": [item.to_dict() for item in self.requirements],
            "routing_policy_ref": self.routing_policy_ref,
            "candidate_level_only": self.candidate_level_only,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class ReviewRoutingEvaluation:
    disposition: ReviewRoutingDisposition
    reason_code: str
    requirement_set: ReviewRequirementSet | None = None


class ReviewRequirementRouter:
    def __init__(self, policy: ReviewRoutingPolicy) -> None:
        self._policy = policy

    def route(self, context: ReviewRoutingContext) -> ReviewRoutingEvaluation:
        operation_rules = self._policy.operation_requirements
        if context.semantic_change_operation not in operation_rules:
            return ReviewRoutingEvaluation(
                disposition="blocked",
                reason_code="review_routing_operation_not_configured",
            )
        review_types = set(self._policy.baseline_review_types)
        review_types.update(operation_rules[context.semantic_change_operation])
        if (
            context.evidence_basis_only
            and context.semantic_change_operation
            in self._policy.baseline_only_when_evidence_basis_unchanged
        ):
            review_types.discard("domain_review")
        if (
            (context.same_object_relevant or context.identity_ambiguous)
            and context.semantic_change_operation
            in self._policy.identity_sensitive_operations
        ):
            review_types.add("entity_and_identity_review")
        if context.privacy_or_security_triggered:
            review_types.add("privacy_and_security_review")
        if "publication_review" in review_types:
            return ReviewRoutingEvaluation(
                disposition="blocked",
                reason_code="publication_review_not_candidate_level",
            )
        if not review_types.issubset(REVIEW_TYPES):
            return ReviewRoutingEvaluation(
                disposition="blocked",
                reason_code="review_type_not_allowed",
            )

        candidate = context.candidate_revision
        requirements: list[ReviewRequirement] = []
        for review_type in sorted(review_types):
            authority = context.authority_by_review_type.get(review_type)
            if not authority:
                return ReviewRoutingEvaluation(
                    disposition="blocked",
                    reason_code="review_authority_route_missing",
                )
            if review_type in self._policy.baseline_review_types:
                trigger = "candidate_revision_baseline"
            elif review_type == "entity_and_identity_review":
                trigger = "same_object_or_identity_relevance"
            elif review_type == "privacy_and_security_review":
                trigger = "privacy_or_security_risk"
            else:
                trigger = (
                    f"semantic_change_operation:{context.semantic_change_operation}"
                )
            review_scope = (
                f"candidate_revision:{context.semantic_change_operation}:{review_type}"
            )
            payload = {
                "review_type": review_type,
                "subject_ref": candidate.lifecycle_candidate_ref,
                "subject_version": candidate.lifecycle_candidate_revision_ref,
                "review_scope": review_scope,
                "required_reviewer_authority": authority,
                "rule_basis_refs": list(ordered_unique(context.rule_basis_refs)),
                "profile_refs": list(ordered_unique(context.profile_refs)),
                "trigger": trigger,
                "blocking": True,
            }
            requirements.append(
                ReviewRequirement(
                    review_requirement_ref=local_ref("RQR", payload),
                    review_type=review_type,
                    subject_ref=candidate.lifecycle_candidate_ref,
                    subject_version=candidate.lifecycle_candidate_revision_ref,
                    review_scope=review_scope,
                    required_reviewer_authority=authority,
                    rule_basis_refs=ordered_unique(context.rule_basis_refs),
                    profile_refs=ordered_unique(context.profile_refs),
                    trigger=trigger,
                    blocking=True,
                )
            )
        set_payload = {
            "candidate_ref": candidate.lifecycle_candidate_ref,
            "candidate_revision_ref": candidate.lifecycle_candidate_revision_ref,
            "requirement_refs": [item.review_requirement_ref for item in requirements],
            "routing_policy_ref": self._policy.policy_ref,
            "candidate_level_only": True,
        }
        requirement_set = ReviewRequirementSet(
            review_requirement_set_ref=local_ref("RQS", set_payload),
            candidate_ref=candidate.lifecycle_candidate_ref,
            candidate_revision_ref=candidate.lifecycle_candidate_revision_ref,
            requirements=tuple(requirements),
            routing_policy_ref=self._policy.policy_ref,
        )
        return ReviewRoutingEvaluation(
            disposition="routed",
            reason_code="candidate_review_requirements_routed",
            requirement_set=requirement_set,
        )


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    review_request_ref: str
    review_requirement_ref: str
    review_type: str
    subject_ref: str
    subject_version: str
    review_scope: str
    required_reviewer_authority: str
    evidence_and_context_refs: tuple[str, ...]
    known_questions_gaps_conflicts: tuple[str, ...]
    rule_basis_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    contract_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Review Request Contract",
            "contract_version": self.contract_version,
            "message_kind": "request",
            "review_request_ref": self.review_request_ref,
            "review_requirement_ref": self.review_requirement_ref,
            "review_type": self.review_type,
            "subject_ref": self.subject_ref,
            "subject_version": self.subject_version,
            "review_scope": self.review_scope,
            "required_reviewer_authority": self.required_reviewer_authority,
            "evidence_and_context_refs": list(self.evidence_and_context_refs),
            "known_questions_gaps_conflicts": list(self.known_questions_gaps_conflicts),
            "rule_basis_refs": list(self.rule_basis_refs),
            "profile_refs": list(self.profile_refs),
        }


class ReviewRequestFactory:
    def create_requests(
        self,
        requirement_set: ReviewRequirementSet,
        *,
        evidence_and_context_refs: tuple[str, ...],
        known_questions_gaps_conflicts: tuple[str, ...],
    ) -> tuple[ReviewRequest, ...]:
        requests: list[ReviewRequest] = []
        for requirement in requirement_set.requirements:
            payload = {
                "review_requirement_ref": requirement.review_requirement_ref,
                "review_type": requirement.review_type,
                "subject_ref": requirement.subject_ref,
                "subject_version": requirement.subject_version,
                "review_scope": requirement.review_scope,
                "required_reviewer_authority": (
                    requirement.required_reviewer_authority
                ),
                "evidence_and_context_refs": list(
                    ordered_unique(evidence_and_context_refs)
                ),
                "known_questions_gaps_conflicts": list(
                    ordered_unique(known_questions_gaps_conflicts)
                ),
                "rule_basis_refs": list(requirement.rule_basis_refs),
                "profile_refs": list(requirement.profile_refs),
            }
            requests.append(
                ReviewRequest(
                    review_request_ref=local_ref("RVQ", payload),
                    review_requirement_ref=requirement.review_requirement_ref,
                    review_type=requirement.review_type,
                    subject_ref=requirement.subject_ref,
                    subject_version=requirement.subject_version,
                    review_scope=requirement.review_scope,
                    required_reviewer_authority=(
                        requirement.required_reviewer_authority
                    ),
                    evidence_and_context_refs=ordered_unique(evidence_and_context_refs),
                    known_questions_gaps_conflicts=ordered_unique(
                        known_questions_gaps_conflicts
                    ),
                    rule_basis_refs=requirement.rule_basis_refs,
                    profile_refs=requirement.profile_refs,
                )
            )
        return tuple(requests)


@dataclass(frozen=True, slots=True)
class ReviewCondition:
    condition_ref: str
    state: str
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_ref": self.condition_ref,
            "state": self.state,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    review_record_ref: str
    review_request_ref: str
    review_type: str
    subject_ref: str
    subject_version: str
    review_scope: str
    reviewer_ref: str
    reviewer_authority: str
    result: str
    findings: tuple[str, ...]
    conditions: tuple[ReviewCondition, ...]
    evidence_reviewed_refs: tuple[str, ...]
    rule_basis_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    reviewed_at: str
    record_hash: str
    synthetic_test_fixture: bool
    asserted_effects: tuple[str, ...]
    selects_conflict_winner: bool
    policy_decision_ref: str | None = None
    contract_version: str = "0.1"

    @classmethod
    def create(
        cls,
        *,
        review_request_ref: str,
        review_type: str,
        subject_ref: str,
        subject_version: str,
        review_scope: str,
        reviewer_ref: str,
        reviewer_authority: str,
        result: str,
        findings: tuple[str, ...],
        conditions: tuple[ReviewCondition, ...],
        evidence_reviewed_refs: tuple[str, ...],
        rule_basis_refs: tuple[str, ...],
        profile_refs: tuple[str, ...],
        reviewed_at: str,
        synthetic_test_fixture: bool,
        asserted_effects: tuple[str, ...] = (),
        selects_conflict_winner: bool = False,
        policy_decision_ref: str | None = None,
    ) -> ReviewRecord:
        payload = {
            "review_request_ref": review_request_ref,
            "review_type": review_type,
            "subject_ref": subject_ref,
            "subject_version": subject_version,
            "review_scope": review_scope,
            "reviewer_ref": reviewer_ref,
            "reviewer_authority": reviewer_authority,
            "result": result,
            "findings": list(findings),
            "conditions": [item.to_dict() for item in conditions],
            "evidence_reviewed_refs": list(ordered_unique(evidence_reviewed_refs)),
            "rule_basis_refs": list(ordered_unique(rule_basis_refs)),
            "profile_refs": list(ordered_unique(profile_refs)),
            "reviewed_at": reviewed_at,
            "synthetic_test_fixture": synthetic_test_fixture,
            "asserted_effects": list(ordered_unique(asserted_effects)),
            "selects_conflict_winner": selects_conflict_winner,
            "policy_decision_ref": policy_decision_ref,
        }
        hash_value = content_hash(payload)
        return cls(
            review_record_ref=f"RVR-{hash_value[:24]}",
            review_request_ref=review_request_ref,
            review_type=review_type,
            subject_ref=subject_ref,
            subject_version=subject_version,
            review_scope=review_scope,
            reviewer_ref=reviewer_ref,
            reviewer_authority=reviewer_authority,
            result=result,
            findings=tuple(findings),
            conditions=tuple(conditions),
            evidence_reviewed_refs=ordered_unique(evidence_reviewed_refs),
            rule_basis_refs=ordered_unique(rule_basis_refs),
            profile_refs=ordered_unique(profile_refs),
            reviewed_at=reviewed_at,
            record_hash=hash_value,
            synthetic_test_fixture=synthetic_test_fixture,
            asserted_effects=ordered_unique(asserted_effects),
            selects_conflict_winner=selects_conflict_winner,
            policy_decision_ref=policy_decision_ref,
        )

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "review_request_ref": self.review_request_ref,
            "review_type": self.review_type,
            "subject_ref": self.subject_ref,
            "subject_version": self.subject_version,
            "review_scope": self.review_scope,
            "reviewer_ref": self.reviewer_ref,
            "reviewer_authority": self.reviewer_authority,
            "result": self.result,
            "findings": list(self.findings),
            "conditions": [item.to_dict() for item in self.conditions],
            "evidence_reviewed_refs": list(self.evidence_reviewed_refs),
            "rule_basis_refs": list(self.rule_basis_refs),
            "profile_refs": list(self.profile_refs),
            "reviewed_at": self.reviewed_at,
            "synthetic_test_fixture": self.synthetic_test_fixture,
            "asserted_effects": list(self.asserted_effects),
            "selects_conflict_winner": self.selects_conflict_winner,
            "policy_decision_ref": self.policy_decision_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": "Review Record Contract",
            "contract_version": self.contract_version,
            "message_kind": "record",
            "review_record_ref": self.review_record_ref,
            **self._hash_payload(),
            "record_hash": self.record_hash,
        }


@dataclass(frozen=True, slots=True)
class ReviewRecordValidation:
    disposition: ReviewValidationDisposition
    reason_code: str


class ReviewRecordValidator:
    def validate(
        self,
        record: ReviewRecord,
        request: ReviewRequest,
        candidate: LifecycleCandidateRevision,
    ) -> ReviewRecordValidation:
        if record.record_hash != content_hash(record._hash_payload()):
            return self._blocked("review_record_hash_mismatch")
        if (
            record.review_type not in REVIEW_TYPES
            or record.result not in REVIEW_RESULTS
        ):
            return self._blocked("review_record_contract_value_not_allowed")
        if (
            record.review_request_ref != request.review_request_ref
            or record.review_type != request.review_type
            or record.subject_ref != request.subject_ref
            or record.subject_version != request.subject_version
            or record.review_scope != request.review_scope
        ):
            return self._blocked("review_record_request_or_revision_mismatch")
        if _FOREIGN_REVIEW_EFFECTS.intersection(record.asserted_effects):
            return self._blocked("review_foreign_authority_effect_forbidden")
        if record.selects_conflict_winner:
            return self._blocked("conflict_review_cannot_select_winner")
        if (
            record.review_type == "independent_quality_review"
            and record.reviewer_authority == "technical_conformance_mechanism"
        ):
            return self._blocked("technical_conformance_not_independent_review")
        if record.reviewer_authority != request.required_reviewer_authority:
            return self._blocked("reviewer_not_authorized")
        if (
            record.review_type == "independent_quality_review"
            and record.reviewer_ref in candidate.producer_refs
        ):
            if record.reviewer_ref == "PROJECT-OWNER":
                return self._blocked("block_other_human_required")
            return self._blocked("independent_self_review_forbidden")
        if (
            record.result == "waived_by_authorized_policy"
            and not record.policy_decision_ref
        ):
            return self._blocked("authorized_policy_waiver_missing")
        return ReviewRecordValidation(
            disposition="accepted",
            reason_code="review_record_valid",
        )

    @staticmethod
    def _blocked(reason_code: str) -> ReviewRecordValidation:
        return ReviewRecordValidation(disposition="blocked", reason_code=reason_code)


@dataclass(frozen=True, slots=True)
class ReviewCarryForwardRequest:
    review_record: ReviewRecord
    target_requirement: ReviewRequirement
    review_scope_unchanged: bool
    rule_basis_still_valid: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewCarryForwardRecord:
    carry_forward_ref: str
    review_record_ref: str
    from_subject_version: str
    to_subject_version: str
    review_type: str
    review_scope: str
    evidence_refs: tuple[str, ...]
    rule_basis_refs: tuple[str, ...]
    creates_new_review_decision: bool = False


@dataclass(frozen=True, slots=True)
class ReviewCarryForwardEvaluation:
    disposition: Literal["accepted", "blocked"]
    reason_code: str
    record: ReviewCarryForwardRecord | None = None


@dataclass(frozen=True, slots=True)
class CandidateReviewReadiness:
    ready: bool
    reason_code: str
    review_states: tuple[tuple[str, str], ...]
    missing_review_types: tuple[str, ...] = ()
    open_condition_review_types: tuple[str, ...] = ()
    readiness_scope: str = "candidate_review_readiness"
    publication_package_review_readiness: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "reason_code": self.reason_code,
            "review_states": dict(self.review_states),
            "missing_review_types": list(self.missing_review_types),
            "open_condition_review_types": list(self.open_condition_review_types),
            "readiness_scope": self.readiness_scope,
            "publication_package_review_readiness": (
                self.publication_package_review_readiness
            ),
        }


class ReviewOrchestrator:
    def evaluate_carry_forward(
        self,
        request: ReviewCarryForwardRequest,
    ) -> ReviewCarryForwardEvaluation:
        record = request.review_record
        requirement = request.target_requirement
        if record.review_type != requirement.review_type:
            return self._carry_blocked("review_type_changed")
        if (
            not request.review_scope_unchanged
            or record.review_scope != requirement.review_scope
        ):
            return self._carry_blocked("review_scope_changed")
        if not request.rule_basis_still_valid or (
            record.rule_basis_refs != requirement.rule_basis_refs
        ):
            return self._carry_blocked("review_rule_basis_changed")
        if not request.evidence_refs:
            return self._carry_blocked("explicit_carry_forward_evidence_missing")
        if record.result not in {"passed", "not_applicable"}:
            return self._carry_blocked("review_result_not_carry_forward_eligible")
        payload = {
            "review_record_ref": record.review_record_ref,
            "from_subject_version": record.subject_version,
            "to_subject_version": requirement.subject_version,
            "review_type": record.review_type,
            "review_scope": record.review_scope,
            "evidence_refs": list(ordered_unique(request.evidence_refs)),
            "rule_basis_refs": list(record.rule_basis_refs),
        }
        carry_record = ReviewCarryForwardRecord(
            carry_forward_ref=local_ref("RCF", payload),
            review_record_ref=record.review_record_ref,
            from_subject_version=record.subject_version,
            to_subject_version=requirement.subject_version,
            review_type=record.review_type,
            review_scope=record.review_scope,
            evidence_refs=ordered_unique(request.evidence_refs),
            rule_basis_refs=record.rule_basis_refs,
        )
        return ReviewCarryForwardEvaluation(
            disposition="accepted",
            reason_code="review_carry_forward_documented",
            record=carry_record,
        )

    def evaluate_readiness(
        self,
        requirement_set: ReviewRequirementSet,
        records: tuple[ReviewRecord, ...],
        *,
        invalidated_review_record_refs: tuple[str, ...] = (),
        materially_changed_from_revision: str | None = None,
        carry_forward_records: tuple[ReviewCarryForwardRecord, ...] = (),
    ) -> CandidateReviewReadiness:
        states: dict[str, str] = {}
        missing: list[str] = []
        open_conditions: list[str] = []
        invalidated = set(invalidated_review_record_refs)
        carry_by_type = {
            item.review_type: item
            for item in carry_forward_records
            if item.to_subject_version == requirement_set.candidate_revision_ref
        }

        for requirement in requirement_set.requirements:
            matching = [
                record
                for record in records
                if record.review_type == requirement.review_type
                and record.subject_ref == requirement.subject_ref
                and record.subject_version == requirement.subject_version
            ]
            if not matching and requirement.review_type in carry_by_type:
                states[requirement.review_type] = "passed"
                continue
            if not matching:
                old_matching = [
                    record
                    for record in records
                    if record.review_type == requirement.review_type
                ]
                if old_matching and materially_changed_from_revision:
                    states[requirement.review_type] = "invalidated"
                    return self._not_ready(
                        "review_record_invalidated",
                        states,
                    )
                missing.append(requirement.review_type)
                states[requirement.review_type] = "not_requested"
                continue
            record = matching[0]
            if record.review_record_ref in invalidated:
                states[requirement.review_type] = "invalidated"
                return self._not_ready("review_record_invalidated", states)
            if record.result == "changes_required":
                states[requirement.review_type] = "changes_required"
                return self._not_ready("review_changes_required", states)
            if record.result == "failed":
                states[requirement.review_type] = "failed"
                return self._not_ready("review_failed", states)
            if record.result == "passed_with_conditions":
                if not record.conditions or any(
                    condition.state != "satisfied" or not condition.evidence_refs
                    for condition in record.conditions
                ):
                    states[requirement.review_type] = "passed_with_open_conditions"
                    open_conditions.append(requirement.review_type)
                    continue
                states[requirement.review_type] = "passed"
            elif record.result == "waived_by_authorized_policy":
                states[requirement.review_type] = "waived"
            else:
                states[requirement.review_type] = record.result

        if missing:
            return CandidateReviewReadiness(
                ready=False,
                reason_code="required_review_missing",
                review_states=tuple(sorted(states.items())),
                missing_review_types=ordered_unique(missing),
            )
        if open_conditions:
            return CandidateReviewReadiness(
                ready=False,
                reason_code="review_conditions_unmet",
                review_states=tuple(sorted(states.items())),
                open_condition_review_types=ordered_unique(open_conditions),
            )
        return CandidateReviewReadiness(
            ready=True,
            reason_code="candidate_review_requirements_satisfied",
            review_states=tuple(sorted(states.items())),
        )

    @staticmethod
    def _not_ready(
        reason_code: str,
        states: dict[str, str],
    ) -> CandidateReviewReadiness:
        return CandidateReviewReadiness(
            ready=False,
            reason_code=reason_code,
            review_states=tuple(sorted(states.items())),
        )

    @staticmethod
    def _carry_blocked(reason_code: str) -> ReviewCarryForwardEvaluation:
        return ReviewCarryForwardEvaluation(
            disposition="blocked",
            reason_code=reason_code,
        )
