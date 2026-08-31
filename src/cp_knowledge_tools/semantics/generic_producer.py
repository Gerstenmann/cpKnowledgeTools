"""Provider-neutral, policy-before-call semantic producer.

No model client, credentials, retries, retrieval or publication implementation is
included. The trusted host admits/configures a backend and resolves Policy; this
core cannot establish provider or processing authority from a task declaration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes
from cp_knowledge_tools.policy import (
    PolicyConfiguration,
    PolicyDecision,
    PolicyDecisionValidator,
    PolicyEvaluator,
)

from .candidate_transport import CandidateDecoder
from .candidates import KnownGap, SemanticCandidatePayload, SemanticValue
from .hardening import EvidenceAssessment
from .invocation import (
    BackendIdentity,
    BackendRequest,
    EvidenceData,
    InvocationBounds,
    InvocationPolicyContext,
    PreparedInvocation,
    SemanticBackend,
    SemanticTask,
    prepare_invocation,
    timestamp,
)

__all__ = [
    "BackendIdentity",
    "BackendRequest",
    "GenericSemanticCandidateProducer",
    "InvocationBounds",
    "InvocationPolicyContext",
    "SemanticTask",
    "prepare_invocation",
]


@dataclass(frozen=True, slots=True)
class InvocationProvenance:
    producer_ref: str
    producer_version: str
    backend: BackendIdentity
    task: SemanticTask
    parameters: tuple[tuple[str, SemanticValue], ...]
    toolset: tuple[str, ...]
    normalized_refs: tuple[str, ...]
    evidence_address_refs: tuple[str, ...]
    snapshot_refs: tuple[str, ...]
    profile_refs: tuple[str, ...]
    policy_decision_ref: str
    policy_evaluation_fingerprint: str
    policy_configuration_fingerprint: str
    evaluated_policy_configuration_fingerprint: str
    processing_zone: str
    run_ref: str
    correlation_ref: str
    invocation_ref: str
    invoked_at: str
    configuration_fingerprint: str
    input_fingerprint: str
    raw_response_fingerprint: str
    accepted_candidate_fingerprint: str
    candidate_payload_fingerprints: tuple[str, ...]
    evidence_assessment_fingerprints: tuple[str, ...]
    fingerprint_contract: str = "sha256/cpkt.canonical-json@1; response=raw-bytes"


@dataclass(frozen=True, slots=True)
class GenericSemanticResult:
    candidate_payloads: tuple[SemanticCandidatePayload, ...]
    known_gaps: tuple[KnownGap, ...]
    evidence_assessments: tuple[EvidenceAssessment, ...]
    invocation_provenance: InvocationProvenance

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GenericSemanticCandidateProducer:
    def __init__(
        self, backend: SemanticBackend, *, clock: Callable[[], str] = _now
    ) -> None:
        self._backend = backend
        self._clock = clock

    def generate(
        self,
        invocation: PreparedInvocation,
        *,
        configuration: PolicyConfiguration | None,
        evaluator: PolicyEvaluator | None = None,
    ) -> GenericSemanticResult:
        invocation.validate()
        actual_time = timestamp(self._clock())
        if actual_time < timestamp(invocation.invoked_at):
            raise ValueError("invocation context is in the future")
        for bound, start in (
            (configuration.valid_from if configuration else None, True),
            (configuration.valid_until if configuration else None, False),
        ):
            if bound and (
                (start and actual_time < timestamp(bound))
                or (not start and actual_time > timestamp(bound))
            ):
                raise ValueError("policy configuration not current")
        original_configuration = configuration
        # The shared evaluator compares validity strings. Normalize this local
        # view to fixed-width UTC without changing the authoritative input.
        if configuration is not None:
            configuration = replace(
                configuration,
                valid_from=(
                    timestamp(configuration.valid_from).isoformat(
                        timespec="microseconds"
                    )
                    if configuration.valid_from
                    else None
                ),
                valid_until=(
                    timestamp(configuration.valid_until).isoformat(
                        timespec="microseconds"
                    )
                    if configuration.valid_until
                    else None
                ),
            )
        evaluation = replace(
            invocation.policy_evaluation,
            context_valid_at=actual_time.isoformat(timespec="microseconds"),
        )
        decision = (evaluator or PolicyEvaluator()).evaluate(evaluation, configuration)
        if (
            not isinstance(decision, PolicyDecision)
            or PolicyDecisionValidator().validate(decision, evaluation).disposition
            != "valid"
        ):
            raise ValueError("policy decision binding invalid")
        if decision.result not in {"permit", "conditions"}:
            raise ValueError("semantic processing not permitted")
        if configuration is None or original_configuration is None:
            raise ValueError("policy configuration unresolved")
        if not decision.decision_authority_ref or not decision.policy_rule_refs:
            raise ValueError("policy authority unresolved")
        if decision.valid_from and actual_time < timestamp(decision.valid_from):
            raise ValueError("policy decision not yet valid")
        if decision.valid_until and actual_time > timestamp(decision.valid_until):
            raise ValueError("policy decision expired")
        if decision.result == "conditions" and not decision.conditions:
            raise ValueError("policy conditions missing")
        for condition in decision.conditions:
            if (
                condition.contract_failure()
                or condition.state not in {"satisfied", "waived_by_authorized_override"}
                or not set(condition.required_evidence_refs)
                <= set(condition.fulfilment_evidence_refs)
                or not set(condition.subject_refs) <= set(evaluation.subject_refs)
                or actual_time < timestamp(condition.valid_from)
                or actual_time > timestamp(condition.valid_until)
            ):
                raise ValueError("policy condition not satisfied/bound")
        # No Source content crosses this boundary before the concrete decision.
        request = BackendRequest(
            invocation.invocation_ref,
            invocation.run_ref,
            invocation.correlation_ref,
            invocation.task,
            invocation.backend,
            invocation.bounds,
            tuple(EvidenceData(e.handle, e.address.text) for e in invocation.evidence),
            invocation.parameters,
            invocation.toolset,
            decision.policy_decision_ref,
            invocation.configuration_fingerprint,
            invocation.input_fingerprint,
        )
        raw = self._backend.invoke(request)
        invocation.validate()
        decoded = CandidateDecoder().decode(
            raw, invocation, produced_at=actual_time.isoformat()
        )
        provenance = InvocationProvenance(
            "cpkt.generic-semantic-producer",
            "1",
            invocation.backend,
            invocation.task,
            invocation.parameters,
            invocation.toolset,
            tuple(sorted({r for e in invocation.evidence for r in e.normalized_refs})),
            tuple(e.address.evidence_address_ref for e in invocation.evidence),
            tuple(c.snapshot.snapshot_ref for c in invocation.captures),
            invocation.policy.profile_refs,
            decision.policy_decision_ref,
            evaluation.context_fingerprint,
            canonical_json_hash(asdict(original_configuration)),
            canonical_json_hash(asdict(configuration)),
            invocation.backend.processing_zone,
            invocation.run_ref,
            invocation.correlation_ref,
            invocation.invocation_ref,
            actual_time.isoformat(),
            invocation.configuration_fingerprint,
            invocation.input_fingerprint,
            sha256_bytes(raw),
            canonical_json_hash(decoded.to_dict()),
            tuple(canonical_json_hash(c.to_dict()) for c in decoded.candidate_payloads),
            tuple(
                canonical_json_hash(a.to_dict()) for a in decoded.evidence_assessments
            ),
        )
        return GenericSemanticResult(
            decoded.candidate_payloads,
            decoded.known_gaps,
            decoded.evidence_assessments,
            provenance,
        )
