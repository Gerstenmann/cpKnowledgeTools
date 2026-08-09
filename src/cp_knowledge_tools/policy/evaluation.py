from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from cp_knowledge_tools.platform.hashing import canonical_json_hash

PolicyEffect = Literal["permit", "deny"]
PolicyOperation = Literal["claim_read", "evidence_resolution"]

SUPPORTED_OPERATIONS = frozenset({"claim_read", "evidence_resolution"})


@dataclass(frozen=True, slots=True)
class PolicySubject:
    subject_type: str
    stable_id: str
    version: str
    authority_context: str


@dataclass(frozen=True, slots=True)
class PolicyEvaluationInput:
    policy_evaluation_ref: str
    actor_or_consumer_ref: str
    purpose: str
    requested_operation: str
    subject_refs: tuple[PolicySubject, ...]
    policy_config_ref: str
    processing_zone: str
    profile_refs: tuple[str, ...]
    policy_anchor_ids: tuple[str, ...]
    requested_at: str
    context_valid_at: str


@dataclass(frozen=True, slots=True)
class PolicyRule:
    policy_rule_ref: str
    actor_or_consumer_ref: str
    purpose: str
    requested_operation: PolicyOperation
    subject_ref: PolicySubject
    required_policy_anchor_ids: tuple[str, ...]
    effect: PolicyEffect
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyConfiguration:
    policy_ref: str
    version: str
    status: str
    rules: tuple[PolicyRule, ...]

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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PolicyEvaluator:
    """Evaluate the two delivery operations required by the Core MVP.

    This is deliberately an exact-match evaluator, not a general policy engine.
    A permit exists only when one active, concrete configuration contains an
    applicable permit rule and no applicable deny or unresolved conflict.
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
            rule
            for rule in configuration.rules
            if self._applies(rule, evaluation)
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

        effect = effects.pop()
        reasons = tuple(rule.reason for rule in applicable)
        return self._decision(
            evaluation,
            configuration,
            effect,
            applicable,
            reasons,
        )

    def _input_failure(
        self,
        evaluation: PolicyEvaluationInput,
        configuration: PolicyConfiguration | None,
    ) -> str | None:
        if not evaluation.actor_or_consumer_ref:
            return "policy_actor_or_consumer_missing"
        if not evaluation.purpose:
            return "policy_purpose_missing"
        if evaluation.requested_operation not in SUPPORTED_OPERATIONS:
            return "requested_operation_unsupported"
        if not evaluation.subject_refs:
            return "policy_subject_missing"
        if not evaluation.processing_zone:
            return "processing_zone_unknown"
        if not evaluation.profile_refs:
            return "policy_profile_missing"
        if configuration is None:
            return "policy_configuration_missing"
        if configuration.status != "active":
            return "policy_configuration_not_active"
        if not configuration.policy_ref or not configuration.version:
            return "policy_configuration_unresolved"
        if evaluation.policy_config_ref != configuration.concrete_ref:
            return "policy_configuration_not_applicable"
        return None

    def _applies(
        self,
        rule: PolicyRule,
        evaluation: PolicyEvaluationInput,
    ) -> bool:
        return (
            rule.actor_or_consumer_ref == evaluation.actor_or_consumer_ref
            and rule.purpose == evaluation.purpose
            and rule.requested_operation == evaluation.requested_operation
            and rule.subject_ref in evaluation.subject_refs
            and set(rule.required_policy_anchor_ids).issubset(
                evaluation.policy_anchor_ids
            )
        )

    def _decision(
        self,
        evaluation: PolicyEvaluationInput,
        configuration: PolicyConfiguration | None,
        result: PolicyEffect,
        rules: tuple[PolicyRule, ...],
        reasons: tuple[str, ...],
    ) -> PolicyDecision:
        authorized = result == "permit"
        payload = {
            "evaluation": asdict(evaluation),
            "configuration_ref": (
                configuration.concrete_ref if configuration else None
            ),
            "result": result,
            "rule_refs": [rule.policy_rule_ref for rule in rules],
            "reasons": list(reasons),
        }
        return PolicyDecision(
            policy_decision_ref=f"PDEC-{canonical_json_hash(payload)[:24].upper()}",
            policy_evaluation_ref=evaluation.policy_evaluation_ref,
            result=result,
            authorized_actions=(evaluation.requested_operation,) if authorized else (),
            authorized_subject_refs=evaluation.subject_refs if authorized else (),
            authorized_scope=(
                configuration.concrete_ref
                if authorized and configuration is not None
                else None
            ),
            actor_or_consumer_ref=evaluation.actor_or_consumer_ref,
            purpose=evaluation.purpose,
            processing_zone=evaluation.processing_zone,
            policy_rule_refs=tuple(rule.policy_rule_ref for rule in rules),
            decision_reasons=reasons,
            decision_authority_ref=(
                configuration.concrete_ref
                if configuration is not None
                else "fail-closed-policy-boundary"
            ),
        )
