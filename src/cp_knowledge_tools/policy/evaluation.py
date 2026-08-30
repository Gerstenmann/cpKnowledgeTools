from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, get_args

from cp_knowledge_tools.platform.hashing import canonical_json_hash

PolicyEffect = Literal["permit", "conditions", "review", "escalate", "deny"]
PolicyOperation = Literal["claim_read", "evidence_resolution", "publish"]
PolicyAction = Literal[
    "register",
    "capture",
    "process",
    "resolve_evidence",
    "retrieve",
    "store_in_memory",
    "export",
    "publish",
    "communicate_external",
    "write_back",
    "delete",
    "archive",
    "override",
]
PolicyDataOperation = Literal[
    "discover",
    "read_metadata",
    "read_content",
    "resolve_evidence",
    "create",
    "update",
    "transform",
    "classify",
    "derive",
    "index",
    "retrieve",
    "include_in_context_package",
    "store_in_memory",
    "export",
    "redact",
    "delete",
    "archive",
]
ProfileResolutionStatus = Literal["resolved", "unresolved"]

# CPKS-SPEC-SEC-VOC@0.1 is the sole semantic rule home for these closed sets.
POLICY_ACTIONS_VOCABULARY_REF = "CPKS-SPEC-SEC-VOC@0.1#cpks.vocab.policy.action"
POLICY_DATA_OPERATIONS_VOCABULARY_REF = (
    "CPKS-SPEC-SEC-VOC@0.1#cpks.vocab.policy.data_operation"
)
SUPPORTED_ACTIONS = frozenset(get_args(PolicyAction))
SUPPORTED_DATA_OPERATIONS = frozenset(get_args(PolicyDataOperation))
PUBLICATION_DATA_OPERATIONS: tuple[PolicyDataOperation, ...] = (
    "read_content",
    "transform",
    "create",
)
LEGACY_SUPPORTED_OPERATIONS = frozenset({"claim_read", "evidence_resolution"})
CONTRACT_OPERATION_CODES = frozenset(
    {"capture_snapshot", "revise_registration", "detect_source_drift"}
)
PROFILE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


@dataclass(frozen=True, slots=True)
class PolicySubject:
    subject_type: str
    stable_id: str
    version: str
    authority_context: str


@dataclass(frozen=True, slots=True)
class ProfileReferenceResolution:
    """A caller-supplied result of concrete Profile Manifest checks."""

    concrete_ref: str
    artifact_type: str
    lifecycle_status: str
    applicable: bool
    compatible: bool


@dataclass(frozen=True, slots=True)
class ProfileApplicability:
    """Resolved applicable Profile set; this context grants no authority."""

    resolution_status: ProfileResolutionStatus
    reference_resolutions: tuple[ProfileReferenceResolution, ...] = ()
    required_profile_refs: tuple[str, ...] = ()
    conflicting_profile_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyEvaluationInput:
    policy_evaluation_ref: str
    actor_or_consumer_ref: str
    purpose: str
    requested_operation: str | None
    subject_refs: tuple[PolicySubject, ...]
    policy_config_ref: str
    processing_zone: str
    profile_refs: tuple[str, ...]
    profile_applicability: ProfileApplicability
    policy_anchor_ids: tuple[str, ...]
    requested_at: str
    context_valid_at: str
    requested_action: str | None = None
    actor_roles: tuple[str, ...] = ()
    requested_data_operations: tuple[str, ...] = ()
    requested_effect_scope: str | None = None
    candidate_revision_ref: str | None = None
    resolution_decision_ref: str | None = None
    publication_change_set_ref: str | None = None
    publication_change_set_version_ref: str | None = None
    publication_change_set_hash: str | None = None
    publication_package_version_ref: str | None = None
    publication_package_hash: str | None = None
    publication_finalization_plan_ref: str | None = None
    publication_unit_refs: tuple[str, ...] = ()
    knowledge_content_hash_refs: tuple[str, ...] = ()
    prepublication_representation_hash_refs: tuple[str, ...] = ()
    target_refs: tuple[str, ...] = ()
    publication_authority_ref: str | None = None
    publication_review_record_ref: str | None = None
    review_record_refs: tuple[str, ...] = ()
    conformance_report_refs: tuple[str, ...] = ()
    risk_input_refs: tuple[str, ...] = ()
    quality_input_refs: tuple[str, ...] = ()
    agent_authority_context: str | None = None

    @property
    def effective_requested_action(self) -> str | None:
        """Return only the canonical action; legacy operations never become one."""

        return self.requested_action

    def context_payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def context_fingerprint(self) -> str:
        return canonical_json_hash(self.context_payload())


@dataclass(frozen=True, slots=True)
class PolicyCondition:
    condition_ref: str
    condition_type: str
    subject_refs: tuple[PolicySubject, ...]
    responsible_context: str
    required_evidence_refs: tuple[str, ...]
    fulfilment_evidence_refs: tuple[str, ...]
    enforcement_point: str
    valid_from: str
    valid_until: str
    failure_action: str
    state: str

    def contract_failure(self) -> str | None:
        if not self.condition_ref or not self.condition_type:
            return "policy_condition_type_missing"
        if not self.subject_refs:
            return "policy_condition_subject_missing"
        if not self.responsible_context:
            return "policy_condition_responsible_context_missing"
        if not self.required_evidence_refs:
            return "policy_condition_required_evidence_missing"
        if not self.enforcement_point:
            return "policy_condition_enforcement_point_missing"
        if not self.valid_from or not self.valid_until:
            return "policy_condition_validity_missing"
        if not self.failure_action:
            return "policy_condition_failure_action_missing"
        if self.state not in {
            "open",
            "satisfied",
            "failed",
            "waived_by_authorized_override",
            "expired",
            "not_applicable",
        }:
            return "policy_condition_state_invalid"
        return None


@dataclass(frozen=True, slots=True)
class PolicyRule:
    policy_rule_ref: str
    actor_or_consumer_ref: str
    purpose: str
    requested_operation: PolicyOperation | None
    subject_ref: PolicySubject
    required_policy_anchor_ids: tuple[str, ...]
    effect: PolicyEffect
    reason: str
    requested_action: PolicyAction | None = None
    requested_data_operations: tuple[PolicyDataOperation, ...] = ()
    conditions: tuple[PolicyCondition, ...] = ()
    authorized_scope: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyConfiguration:
    policy_ref: str
    version: str
    status: str
    rules: tuple[PolicyRule, ...]
    decision_authority_ref: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    synthetic_test_fixture: bool = False

    @property
    def concrete_ref(self) -> str:
        return f"{self.policy_ref}@{self.version}"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    policy_decision_ref: str
    policy_evaluation_ref: str
    result: PolicyEffect
    authorized_actions: tuple[str, ...]
    authorized_subject_refs: tuple[PolicySubject, ...]
    authorized_scope: str | None
    actor_or_consumer_ref: str
    purpose: str
    processing_zone: str
    policy_rule_refs: tuple[str, ...]
    decision_reasons: tuple[str, ...]
    decision_authority_ref: str
    policy_configuration_ref: str | None = None
    requested_action: str | None = None
    requested_data_operations: tuple[str, ...] = ()
    conditions: tuple[PolicyCondition, ...] = ()
    review_record_refs: tuple[str, ...] = ()
    risk_input_refs: tuple[str, ...] = ()
    quality_input_refs: tuple[str, ...] = ()
    agent_authority_context: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    context_fingerprint: str = ""
    synthetic_test_fixture: bool = False
    publication_record_created: bool = False
    requested_operation: str | None = None
    authorized_legacy_operations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def authorizes_legacy_operation(self, operation: str) -> bool:
        """Compatibility check that cannot grant a canonical global action."""

        return operation in self.authorized_legacy_operations or (
            self.requested_action is None and operation in self.authorized_actions
        )


@dataclass(frozen=True, slots=True)
class PolicyDecisionBindingEvaluation:
    disposition: Literal["valid", "stale"]
    reason_code: str


class PolicyDecisionValidator:
    """Require exact, immutable reuse of the evaluated policy context."""

    def validate(
        self,
        decision: PolicyDecision,
        evaluation: PolicyEvaluationInput,
    ) -> PolicyDecisionBindingEvaluation:
        if (
            decision.policy_evaluation_ref != evaluation.policy_evaluation_ref
            or decision.context_fingerprint != evaluation.context_fingerprint
            or (decision.policy_configuration_ref or "") != evaluation.policy_config_ref
            or decision.actor_or_consumer_ref != evaluation.actor_or_consumer_ref
            or decision.purpose != evaluation.purpose
            or decision.processing_zone != evaluation.processing_zone
            or decision.requested_action != evaluation.requested_action
            or decision.requested_operation != evaluation.requested_operation
            or decision.requested_data_operations
            != evaluation.requested_data_operations
            or decision.review_record_refs != evaluation.review_record_refs
            or decision.risk_input_refs != evaluation.risk_input_refs
            or decision.quality_input_refs != evaluation.quality_input_refs
            or decision.agent_authority_context != evaluation.agent_authority_context
        ):
            return self._stale()
        if decision.valid_from and evaluation.context_valid_at < decision.valid_from:
            return self._stale()
        if decision.valid_until and evaluation.context_valid_at > decision.valid_until:
            return self._stale()
        if decision.result in {"permit", "conditions"}:
            if (
                decision.authorized_actions
                != (
                    (evaluation.requested_action,)
                    if evaluation.requested_action
                    else ()
                )
                or decision.authorized_legacy_operations
                != (
                    ()
                    if evaluation.requested_action
                    else (evaluation.requested_operation,)
                )
                or decision.authorized_subject_refs != evaluation.subject_refs
                or decision.authorized_scope != evaluation.requested_effect_scope
            ):
                return self._stale()
        return PolicyDecisionBindingEvaluation(
            disposition="valid",
            reason_code="policy_decision_context_current",
        )

    @staticmethod
    def _stale() -> PolicyDecisionBindingEvaluation:
        return PolicyDecisionBindingEvaluation(
            disposition="stale",
            reason_code="policy_decision_context_stale",
        )


class PolicyEvaluator:
    """Exact-match, deny-by-default evaluation for delivery and publication.

    Publication support generalizes the existing contracts; it does not infer
    policy, Profile applicability, review status, or publication authority.
    """

    def evaluate(
        self,
        evaluation: PolicyEvaluationInput,
        configuration: PolicyConfiguration | None,
    ) -> PolicyDecision:
        failure = self._input_failure(evaluation, configuration)
        if failure is not None:
            return self._decision(evaluation, None, "deny", (), (failure,))

        assert configuration is not None
        applicable = tuple(
            rule for rule in configuration.rules if self._applies(rule, evaluation)
        )
        if not applicable:
            return self._decision(
                evaluation,
                configuration,
                "deny",
                (),
                ("no_applicable_policy_rule",),
            )
        covered_subjects = {rule.subject_ref for rule in applicable}
        if any(subject not in covered_subjects for subject in evaluation.subject_refs):
            return self._decision(
                evaluation,
                configuration,
                "deny",
                applicable,
                ("policy_subject_scope_incomplete",),
            )

        effects = {rule.effect for rule in applicable}
        if len(effects) != 1:
            return self._decision(
                evaluation,
                configuration,
                "deny",
                applicable,
                ("unresolved_policy_rule_conflict",),
            )
        scopes = {rule.authorized_scope for rule in applicable}
        if len(scopes) > 1:
            return self._decision(
                evaluation,
                configuration,
                "deny",
                applicable,
                ("unresolved_policy_scope_conflict",),
            )

        effect = effects.pop()
        reasons = tuple(rule.reason for rule in applicable)
        return self._decision(evaluation, configuration, effect, applicable, reasons)

    def _input_failure(
        self,
        evaluation: PolicyEvaluationInput,
        configuration: PolicyConfiguration | None,
    ) -> str | None:
        if not evaluation.actor_or_consumer_ref:
            return "policy_actor_or_consumer_missing"
        if not evaluation.purpose:
            return "policy_purpose_missing"
        if evaluation.requested_action is None:
            if evaluation.requested_operation not in LEGACY_SUPPORTED_OPERATIONS:
                return "requested_operation_unsupported"
            if evaluation.requested_data_operations:
                return "legacy_operation_data_operation_context_invalid"
        else:
            if evaluation.requested_action not in SUPPORTED_ACTIONS:
                if evaluation.requested_action in CONTRACT_OPERATION_CODES:
                    return "contract_operation_used_as_policy_action"
                return "policy_action_unknown"
            if (
                evaluation.requested_operation is not None
                and evaluation.requested_operation != evaluation.requested_action
            ):
                return "legacy_operation_action_context_ambiguous"
            if not evaluation.requested_data_operations:
                return "policy_data_operations_missing"
            if any(
                operation not in SUPPORTED_DATA_OPERATIONS
                for operation in evaluation.requested_data_operations
            ):
                return "policy_data_operation_unknown"
        if not evaluation.subject_refs:
            return "policy_subject_missing"
        if not evaluation.processing_zone:
            return "processing_zone_unknown"
        if evaluation.requested_action == "publish":
            publish_failure = self._publication_input_failure(evaluation)
            if publish_failure:
                return publish_failure
        profile_failure = self._profile_failure(evaluation)
        if profile_failure is not None:
            return profile_failure
        if configuration is None:
            return "policy_configuration_missing"
        if configuration.status != "active":
            return "policy_configuration_not_active"
        if not configuration.policy_ref or not configuration.version:
            return "policy_configuration_unresolved"
        if evaluation.policy_config_ref != configuration.concrete_ref:
            return "policy_configuration_not_applicable"
        if configuration.valid_from and (
            evaluation.context_valid_at < configuration.valid_from
        ):
            return "policy_configuration_not_yet_valid"
        if configuration.valid_until and (
            evaluation.context_valid_at > configuration.valid_until
        ):
            return "policy_configuration_expired"
        configuration_failure = self._configuration_failure(configuration)
        if configuration_failure is not None:
            return configuration_failure
        return None

    @staticmethod
    def _configuration_failure(configuration: PolicyConfiguration) -> str | None:
        for rule in configuration.rules:
            if rule.requested_action is None:
                if rule.requested_operation not in LEGACY_SUPPORTED_OPERATIONS:
                    return "policy_configuration_operation_unsupported"
                if rule.requested_data_operations:
                    return "policy_configuration_legacy_data_operations_invalid"
                continue
            if rule.requested_action not in SUPPORTED_ACTIONS:
                return "policy_configuration_action_unknown"
            if (
                rule.requested_operation is not None
                and rule.requested_operation != rule.requested_action
            ):
                return "policy_configuration_legacy_action_context_ambiguous"
            if not rule.requested_data_operations:
                return "policy_configuration_data_operations_missing"
            if any(
                operation not in SUPPORTED_DATA_OPERATIONS
                for operation in rule.requested_data_operations
            ):
                return "policy_configuration_data_operation_unknown"
        return None

    @staticmethod
    def _publication_input_failure(
        evaluation: PolicyEvaluationInput,
    ) -> str | None:
        if evaluation.requested_data_operations != PUBLICATION_DATA_OPERATIONS:
            return "publish_data_operation_context_invalid"
        required_scalars = (
            ("requested_effect_scope_missing", evaluation.requested_effect_scope),
            ("candidate_revision_ref_missing", evaluation.candidate_revision_ref),
            ("resolution_decision_ref_missing", evaluation.resolution_decision_ref),
            (
                "publication_change_set_ref_missing",
                evaluation.publication_change_set_ref,
            ),
            (
                "publication_change_set_version_ref_missing",
                evaluation.publication_change_set_version_ref,
            ),
            (
                "publication_change_set_hash_missing",
                evaluation.publication_change_set_hash,
            ),
            (
                "publication_package_version_ref_missing",
                evaluation.publication_package_version_ref,
            ),
            (
                "publication_package_hash_missing",
                evaluation.publication_package_hash,
            ),
            (
                "publication_review_record_ref_missing",
                evaluation.publication_review_record_ref,
            ),
            (
                "publication_finalization_plan_ref_missing",
                evaluation.publication_finalization_plan_ref,
            ),
            (
                "publication_authority_ref_missing",
                evaluation.publication_authority_ref,
            ),
            ("agent_authority_context_missing", evaluation.agent_authority_context),
        )
        for reason, value in required_scalars:
            if not value:
                return reason
        if not evaluation.actor_roles:
            return "policy_actor_roles_missing"
        if not evaluation.publication_unit_refs:
            return "publication_unit_refs_missing"
        if not evaluation.knowledge_content_hash_refs:
            return "knowledge_content_hash_refs_missing"
        if not evaluation.prepublication_representation_hash_refs:
            return "prepublication_representation_hash_refs_missing"
        if not evaluation.target_refs:
            return "publication_target_refs_missing"
        if not evaluation.review_record_refs:
            return "review_inputs_missing"
        if (
            evaluation.publication_review_record_ref
            not in evaluation.review_record_refs
        ):
            return "publication_review_input_mismatch"
        if not evaluation.conformance_report_refs:
            return "conformance_inputs_missing"
        if not evaluation.risk_input_refs:
            return "risk_inputs_missing"
        if not evaluation.quality_input_refs:
            return "quality_inputs_missing"
        return None

    def _profile_failure(self, evaluation: PolicyEvaluationInput) -> str | None:
        context = evaluation.profile_applicability
        if context.resolution_status != "resolved":
            return "policy_profile_reference_unresolved"

        resolutions: dict[str, ProfileReferenceResolution] = {}
        for resolution in context.reference_resolutions:
            if resolution.concrete_ref in resolutions:
                return "policy_profile_conflict"
            resolutions[resolution.concrete_ref] = resolution

        supplied_refs = set(evaluation.profile_refs)
        if len(supplied_refs) != len(evaluation.profile_refs):
            return "policy_profile_conflict"

        required_refs = set(context.required_profile_refs)
        expected_refs = required_refs | {
            resolution.concrete_ref
            for resolution in context.reference_resolutions
            if resolution.applicable and resolution.artifact_type == "profile_manifest"
        }

        for concrete_ref in supplied_refs | expected_refs:
            resolution = resolutions.get(concrete_ref)
            if resolution is None or not self._is_concrete_profile_ref(concrete_ref):
                return "policy_profile_reference_unresolved"
            if resolution.artifact_type != "profile_manifest":
                return "policy_profile_reference_type_invalid"
            if (
                resolution.lifecycle_status != "active"
                or not resolution.applicable
                or not resolution.compatible
            ):
                return "policy_profile_not_applicable"

        if context.conflicting_profile_refs:
            return "policy_profile_conflict"
        if expected_refs - supplied_refs:
            return "policy_applicable_profile_missing"
        if supplied_refs - expected_refs:
            return "policy_profile_not_applicable"
        return None

    @staticmethod
    def _is_concrete_profile_ref(value: str) -> bool:
        profile_ref, separator, profile_version = value.rpartition("@")
        return bool(
            profile_ref
            and separator
            and PROFILE_VERSION_PATTERN.fullmatch(profile_version)
        )

    @staticmethod
    def _applies(rule: PolicyRule, evaluation: PolicyEvaluationInput) -> bool:
        shared_context_matches = (
            rule.actor_or_consumer_ref == evaluation.actor_or_consumer_ref
            and rule.purpose == evaluation.purpose
            and rule.subject_ref in evaluation.subject_refs
            and set(rule.required_policy_anchor_ids).issubset(
                evaluation.policy_anchor_ids
            )
        )
        if not shared_context_matches:
            return False
        if evaluation.requested_action is not None:
            return (
                rule.requested_action == evaluation.requested_action
                and rule.requested_data_operations
                == evaluation.requested_data_operations
            )
        return (
            rule.requested_action is None
            and rule.requested_operation == evaluation.requested_operation
        )

    def _decision(
        self,
        evaluation: PolicyEvaluationInput,
        configuration: PolicyConfiguration | None,
        result: PolicyEffect,
        rules: tuple[PolicyRule, ...],
        reasons: tuple[str, ...],
    ) -> PolicyDecision:
        conditionally_authorized = result in {"permit", "conditions"}
        scopes = {rule.authorized_scope for rule in rules}
        if conditionally_authorized and scopes == {None}:
            authorized_scope = (
                evaluation.requested_effect_scope
                if evaluation.requested_action == "publish"
                else configuration.concrete_ref
                if configuration is not None
                else None
            )
        elif conditionally_authorized and len(scopes) == 1:
            authorized_scope = scopes.pop()
        else:
            authorized_scope = None
        conditions = tuple(condition for rule in rules for condition in rule.conditions)
        payload = {
            "evaluation": evaluation.context_payload(),
            "configuration_ref": (
                configuration.concrete_ref if configuration else None
            ),
            "result": result,
            "rule_refs": [rule.policy_rule_ref for rule in rules],
            "conditions": [asdict(item) for item in conditions],
            "reasons": list(reasons),
        }
        return PolicyDecision(
            policy_decision_ref=f"PDEC-{canonical_json_hash(payload)[:24].upper()}",
            policy_evaluation_ref=evaluation.policy_evaluation_ref,
            result=result,
            authorized_actions=(
                (evaluation.requested_action,)
                if conditionally_authorized and evaluation.requested_action
                else ()
            ),
            authorized_subject_refs=(
                evaluation.subject_refs if conditionally_authorized else ()
            ),
            authorized_scope=authorized_scope,
            actor_or_consumer_ref=evaluation.actor_or_consumer_ref,
            purpose=evaluation.purpose,
            processing_zone=evaluation.processing_zone,
            policy_rule_refs=tuple(rule.policy_rule_ref for rule in rules),
            decision_reasons=reasons,
            decision_authority_ref=(
                configuration.decision_authority_ref or configuration.concrete_ref
                if configuration is not None
                else "fail-closed-policy-boundary"
            ),
            policy_configuration_ref=(
                configuration.concrete_ref if configuration is not None else None
            ),
            requested_action=evaluation.requested_action,
            requested_data_operations=evaluation.requested_data_operations,
            conditions=conditions,
            review_record_refs=evaluation.review_record_refs,
            risk_input_refs=evaluation.risk_input_refs,
            quality_input_refs=evaluation.quality_input_refs,
            agent_authority_context=evaluation.agent_authority_context,
            valid_from=configuration.valid_from if configuration else None,
            valid_until=configuration.valid_until if configuration else None,
            context_fingerprint=evaluation.context_fingerprint,
            synthetic_test_fixture=(
                configuration.synthetic_test_fixture if configuration else False
            ),
            requested_operation=evaluation.requested_operation,
            authorized_legacy_operations=(
                (evaluation.requested_operation,)
                if conditionally_authorized
                and evaluation.requested_action is None
                and evaluation.requested_operation is not None
                else ()
            ),
        )
