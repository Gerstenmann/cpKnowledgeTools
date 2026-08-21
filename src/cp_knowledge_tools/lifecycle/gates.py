from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cp_knowledge_tools.policy import (
    PolicyDecision,
    PolicyDecisionValidator,
    PolicyEvaluationInput,
)

from .publication import (
    ExpectedPriorState,
    PublicationPackage,
    PublicationReviewValidation,
)
from .resolution import LifecycleCandidateRevision, ResolutionDecision


@dataclass(frozen=True, slots=True)
class G5PolicyGateRequest:
    package: PublicationPackage
    policy_evaluation: PolicyEvaluationInput
    policy_decision: object | None
    publication_review: PublicationReviewValidation | None
    context_valid_at: str
    foreign_permit_basis: str | None = None


@dataclass(frozen=True, slots=True)
class G5PolicyGateResult:
    disposition: Literal["passed", "blocked"]
    reason_code: str
    binding_refs: tuple[str, ...] = ()
    policy_decision_ref: str | None = None
    condition_refs: tuple[str, ...] = ()
    execution_authorized: bool = False
    publication_performed: bool = False
    publication_record_created: bool = False
    gate: str = "G5"


class G5PolicyGate:
    """Consume, but never invent, a concrete publication Policy Decision."""

    _FOREIGN_BASIS_REASONS = {
        "policy_evaluation": "policy_evaluation_not_policy_decision",
        "quality_gate": "quality_gate_not_publication_permit",
        "candidate_review": "candidate_review_not_publication_permit",
        "publication_review": "publication_review_not_policy_permit",
    }

    def evaluate(self, request: G5PolicyGateRequest) -> G5PolicyGateResult:
        if request.foreign_permit_basis:
            return self._blocked(
                self._FOREIGN_BASIS_REASONS.get(
                    request.foreign_permit_basis,
                    "foreign_permit_basis_not_policy_decision",
                )
            )
        review = request.publication_review
        if review is None:
            return self._blocked("publication_review_missing")
        if review.disposition != "accepted":
            return self._blocked("publication_review_not_satisfied")
        package = request.package
        if (
            review.publication_package_ref != package.publication_package_ref
            or review.package_version_ref != package.package_version_ref
            or not review.review_record_ref
        ):
            return self._blocked("publication_review_package_binding_mismatch")

        evaluation = request.policy_evaluation
        if not self._evaluation_binds_package(evaluation, package, review):
            return self._blocked("policy_evaluation_package_binding_mismatch")
        decision = request.policy_decision
        if not isinstance(decision, PolicyDecision):
            return self._blocked("policy_decision_missing_or_invalid")
        binding = PolicyDecisionValidator().validate(decision, evaluation)
        if binding.disposition != "valid":
            return self._blocked(binding.reason_code)
        if decision.valid_from and request.context_valid_at < decision.valid_from:
            return self._blocked("policy_decision_not_yet_valid")
        if decision.valid_until and request.context_valid_at > decision.valid_until:
            return self._blocked("policy_decision_expired")

        if decision.result == "deny":
            if "policy_configuration_missing" in decision.decision_reasons:
                return self._blocked("applicable_knowledge_publication_policy_missing")
            return self._blocked("policy_denied")
        if decision.result == "review":
            return self._blocked("policy_additional_review_required")
        if decision.result == "escalate":
            return self._blocked("policy_escalation_required")
        if decision.result == "conditions":
            if not decision.conditions:
                return self._blocked("policy_conditions_missing")
            for condition in decision.conditions:
                contract_failure = condition.contract_failure()
                if contract_failure:
                    return self._blocked(contract_failure)
                if condition.valid_from > request.context_valid_at or (
                    condition.valid_until < request.context_valid_at
                ):
                    return self._blocked("policy_conditions_not_satisfied")
                if condition.state not in {
                    "satisfied",
                    "waived_by_authorized_override",
                }:
                    return self._blocked("policy_conditions_not_satisfied")
                if not set(condition.required_evidence_refs).issubset(
                    condition.fulfilment_evidence_refs
                ):
                    return self._blocked("policy_condition_fulfilment_evidence_missing")
                if not self._condition_subjects_match(condition.subject_refs, package):
                    return self._blocked("policy_condition_subject_mismatch")
        elif decision.result != "permit":
            return self._blocked("policy_result_not_gate_eligible")

        binding_refs = (
            package.package_version_ref,
            package.change_set.change_set_version_ref,
            package.publication_unit_binding.publication_unit_ref,
            package.publication_finalization_plan.publication_finalization_plan_ref,
            package.publication_unit_binding.content_hash.value,
            package.publication_unit_binding.prepublication_representation_hash.value,
            package.publication_finalization_plan.canonical_path,
            package.publication_finalization_plan.maintenance_context_ref,
            package.publication_finalization_plan.publication_authority_ref,
            review.review_record_ref,
            decision.policy_decision_ref,
        )
        return G5PolicyGateResult(
            disposition="passed",
            reason_code="policy_gate_passed",
            binding_refs=binding_refs,
            policy_decision_ref=decision.policy_decision_ref,
            condition_refs=tuple(
                condition.condition_ref for condition in decision.conditions
            ),
        )

    @staticmethod
    def _evaluation_binds_package(
        evaluation: PolicyEvaluationInput,
        package: PublicationPackage,
        review: PublicationReviewValidation,
    ) -> bool:
        unit = package.publication_unit_binding
        plan = package.publication_finalization_plan
        subjects_match = bool(evaluation.subject_refs) and all(
            subject.stable_id == unit.knowledge_object_id
            and subject.version == unit.knowledge_object_version
            for subject in evaluation.subject_refs
        )
        return bool(
            plan.integrity_ok()
            and evaluation.effective_requested_action == "publish"
            and evaluation.requested_operation == "publish"
            and evaluation.requested_data_operations == ("publish",)
            and evaluation.candidate_revision_ref == package.candidate_revision_ref
            and evaluation.resolution_decision_ref == package.resolution_decision_ref
            and evaluation.publication_change_set_ref
            == package.change_set.publication_change_set_ref
            and evaluation.publication_change_set_version_ref
            == package.change_set.change_set_version_ref
            and evaluation.publication_change_set_hash
            == package.change_set.change_set_hash.value
            and evaluation.publication_package_version_ref
            == package.package_version_ref
            and evaluation.publication_package_hash == package.package_hash.value
            and evaluation.publication_finalization_plan_ref
            == plan.publication_finalization_plan_ref
            and evaluation.publication_unit_refs == (unit.publication_unit_ref,)
            and evaluation.knowledge_content_hash_refs == (unit.content_hash.value,)
            and evaluation.prepublication_representation_hash_refs
            == (unit.prepublication_representation_hash.value,)
            and evaluation.target_refs
            == (plan.canonical_path, plan.maintenance_context_ref)
            and evaluation.publication_authority_ref
            == plan.publication_authority_ref
            and evaluation.actor_or_consumer_ref == plan.publisher_ref
            and evaluation.publication_review_record_ref == review.review_record_ref
            and evaluation.profile_refs == package.profile_refs
            and set(package.candidate_review_record_refs).issubset(
                evaluation.review_record_refs
            )
            and review.review_record_ref in evaluation.review_record_refs
            and set(package.conformance_report_refs).issubset(
                evaluation.conformance_report_refs
            )
            and set(package.policy_anchor_refs).issubset(evaluation.policy_anchor_ids)
            and subjects_match
        )

    @staticmethod
    def _condition_subjects_match(subjects: tuple, package: PublicationPackage) -> bool:
        unit = package.publication_unit_binding
        return bool(subjects) and all(
            subject.stable_id == unit.knowledge_object_id
            and subject.version == unit.knowledge_object_version
            for subject in subjects
        )

    @staticmethod
    def _blocked(reason_code: str) -> G5PolicyGateResult:
        return G5PolicyGateResult(disposition="blocked", reason_code=reason_code)


@dataclass(frozen=True, slots=True)
class PublicationAuthorityEvidence:
    authority_ref: str
    authority_kind: str
    authorized_action: str
    authorized_package_version_ref: str
    authorized_subject_refs: tuple[str, ...]
    authority_context_ref: str
    valid_at: str
    explicitly_granted: bool
    synthetic_test_fixture: bool = False


@dataclass(frozen=True, slots=True)
class G6PublicationReadinessRequest:
    package: PublicationPackage | None
    candidate_revision: LifecycleCandidateRevision
    resolution_decision: ResolutionDecision
    candidate_reviews_satisfied: bool
    publication_review: PublicationReviewValidation | None
    g5_result: G5PolicyGateResult | None
    publication_authority: PublicationAuthorityEvidence | None
    observed_prior_states: tuple[ExpectedPriorState, ...]
    recovery_consequences_determined: bool
    foreign_authority_basis: str | None = None
    claimed_publication_record_ref: str | None = None


@dataclass(frozen=True, slots=True)
class G6PublicationReadinessResult:
    disposition: Literal["ready", "blocked"]
    reason_code: str
    binding_refs: tuple[str, ...] = ()
    failed_requirements: tuple[str, ...] = ()
    synthetic_test_only: bool = False
    execution_performed: bool = False
    publication_performed: bool = False
    publication_record_created: bool = False
    canonical_write_performed: bool = False
    gate: str = "G6"


class G6PublicationReadinessGate:
    """Prove readiness while leaving D7 execution entirely unimplemented."""

    _FOREIGN_AUTHORITY_REASONS = {
        "technical_write_capability": (
            "technical_write_capability_not_publication_authority"
        ),
        "project_owner": "project_ownership_not_publication_authority",
        "resolution_authority": "resolution_authority_not_publication_authority",
        "policy_permit": "policy_permit_not_publication_authority",
        "work_package": "work_package_not_publication_authority",
    }

    def evaluate(
        self,
        request: G6PublicationReadinessRequest,
    ) -> G6PublicationReadinessResult:
        if request.foreign_authority_basis:
            return self._blocked(
                self._FOREIGN_AUTHORITY_REASONS.get(
                    request.foreign_authority_basis,
                    "foreign_basis_not_publication_authority",
                )
            )
        if request.claimed_publication_record_ref:
            return self._blocked("policy_permit_not_publication_record")
        package = request.package
        if package is None:
            return self._blocked("publication_package_missing")
        if not request.candidate_reviews_satisfied:
            return self._blocked("candidate_reviews_not_satisfied")
        review = request.publication_review
        if review is None:
            return self._blocked("publication_review_missing")
        if (
            review.disposition != "accepted"
            or review.publication_package_ref != package.publication_package_ref
            or review.package_version_ref != package.package_version_ref
        ):
            return self._blocked("publication_review_not_satisfied")
        authority = request.publication_authority
        if authority is None:
            return self._blocked("publication_authority_missing")
        if request.g5_result is None or request.g5_result.disposition != "passed":
            return self._blocked("g5_policy_gate_not_passed")
        if not package.candidate_revision_immutable:
            return self._blocked("candidate_revision_not_immutable")
        candidate = request.candidate_revision
        resolution = request.resolution_decision
        if (
            package.candidate_ref != candidate.lifecycle_candidate_ref
            or package.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
            or package.resolution_decision_ref != resolution.resolution_decision_ref
            or resolution.candidate_revision_ref
            != candidate.lifecycle_candidate_revision_ref
        ):
            return self._blocked("candidate_resolution_package_binding_mismatch")

        change_set = package.change_set
        if not change_set.atomic:
            return self._blocked("publication_change_set_not_atomic")
        if not change_set.change_set_hash.value:
            return self._blocked("publication_change_set_hash_missing")
        if not change_set.expected_prior_states:
            return self._blocked("expected_prior_states_missing")
        for prior in change_set.expected_prior_states:
            failure = prior.validation_reason()
            if failure:
                return self._blocked(failure)
        if request.observed_prior_states != change_set.expected_prior_states:
            return self._blocked("expected_prior_state_mismatch")
        if not change_set.rollback_or_compensation_plan_ref or (
            not request.recovery_consequences_determined
        ):
            return self._blocked("recovery_plan_incomplete")
        if not change_set.review_record_refs:
            return self._blocked("candidate_review_refs_missing")
        if not change_set.conformance_report_refs:
            return self._blocked("conformance_reports_missing")

        unit = package.publication_unit_binding
        if unit is None:
            return self._blocked("publication_unit_missing")
        if not unit.publication_unit_ref or not unit.knowledge_object_version:
            return self._blocked("publication_unit_version_missing")
        if unit.publication_state != "unpublished":
            return self._blocked("d6_publication_unit_must_be_unpublished")
        if not unit.content_hash.value:
            return self._blocked("publication_unit_hash_missing")
        if not unit.prepublication_representation_hash.value:
            return self._blocked("publication_unit_prepublication_hash_missing")
        if unit.cross_view_validation_status != "pass":
            return self._blocked("publication_unit_cross_view_validation_not_passed")
        if not package.package_hash.value:
            return self._blocked("publication_package_hash_missing")

        plan = package.publication_finalization_plan
        if plan is None:
            return self._blocked("publication_finalization_plan_missing")
        if not plan.integrity_ok():
            return self._blocked("publication_finalization_plan_integrity_invalid")
        if (
            plan.publication_unit_ref != unit.publication_unit_ref
            or plan.knowledge_object_id != unit.knowledge_object_id
            or plan.knowledge_object_version != unit.knowledge_object_version
            or plan.knowledge_content_hash != unit.content_hash
            or plan.prepublication_representation_hash
            != unit.prepublication_representation_hash
        ):
            return self._blocked("finalization_plan_hash_binding_mismatch")
        if (
            plan.expected_source_publication_state != "unpublished"
            or plan.expected_source_canonical_path is not None
            or plan.target_publication_state != "published"
            or not plan.canonical_path
            or not plan.maintenance_context_ref
            or plan.canonical_path not in request.g5_result.binding_refs
            or plan.maintenance_context_ref not in request.g5_result.binding_refs
        ):
            return self._blocked("finalization_plan_target_mismatch")
        if (
            plan.publication_authority_ref != authority.authority_ref
            or plan.publication_authority_ref not in request.g5_result.binding_refs
        ):
            return self._blocked("finalization_plan_authority_mismatch")
        if (
            plan.publication_change_set_ref
            != change_set.publication_change_set_ref
            or plan.publication_package_ref != package.publication_package_ref
            or change_set.publication_finalization_plan_refs
            != (plan.publication_finalization_plan_ref,)
            or unit.publication_finalization_plan_ref
            != plan.publication_finalization_plan_ref
        ):
            return self._blocked("finalization_plan_package_binding_mismatch")
        if (
            plan.review_record_refs != package.candidate_review_record_refs
            or not plan.policy_decision_refs
            or not plan.publisher_ref
            or not plan.executor_ref
            or not plan.planned_publication_record_ref
            or not plan.finalization_method_ref
        ):
            return self._blocked("finalization_plan_context_incomplete")
        if (
            plan.publication_finalization_plan_ref
            not in request.g5_result.binding_refs
            or unit.content_hash.value not in request.g5_result.binding_refs
            or unit.prepublication_representation_hash.value
            not in request.g5_result.binding_refs
        ):
            return self._blocked("g5_finalization_binding_mismatch")

        if (
            not authority.explicitly_granted
            or authority.authority_kind != "publication_authority"
            or authority.authorized_action != "publish"
            or authority.authorized_package_version_ref != package.package_version_ref
            or unit.publication_unit_ref not in authority.authorized_subject_refs
            or not authority.authority_ref
            or not authority.authority_context_ref
            or not authority.valid_at
        ):
            return self._blocked("publication_authority_invalid_or_not_applicable")

        reason_code = (
            "finalization_ready_for_test_isolated_execution"
            if authority.synthetic_test_fixture
            else "publication_finalization_readiness_confirmed"
        )
        return G6PublicationReadinessResult(
            disposition="ready",
            reason_code=reason_code,
            binding_refs=(
                package.package_version_ref,
                change_set.change_set_version_ref,
                unit.publication_unit_ref,
                plan.publication_finalization_plan_ref,
                plan.plan_hash.value,
                unit.content_hash.value,
                unit.prepublication_representation_hash.value,
                plan.canonical_path,
                plan.maintenance_context_ref,
                review.review_record_ref or "",
                request.g5_result.policy_decision_ref or "",
                authority.authority_ref,
            ),
            synthetic_test_only=authority.synthetic_test_fixture,
        )

    @staticmethod
    def _blocked(reason_code: str) -> G6PublicationReadinessResult:
        return G6PublicationReadinessResult(
            disposition="blocked",
            reason_code=reason_code,
            failed_requirements=(reason_code,),
        )
