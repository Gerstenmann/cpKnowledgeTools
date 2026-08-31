"""Host-owned technical invocation bindings, never processing authority.

Only BackendRequest crosses the model boundary. Captures, resolvers and Policy
Configuration stay with the trusted host. Source text is an untrusted data field.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_text
from cp_knowledge_tools.policy import (
    PolicyEvaluationInput,
    PolicySubject,
    ProfileApplicability,
)
from cp_knowledge_tools.sources.models import (
    CapturedSource,
    EvidenceAddress,
    NormalizedRecord,
    NormalizedSourceRepresentation,
    StructuredSegment,
)

from .candidates import SemanticValue


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("invocation timestamp requires timezone")
    return result.astimezone(UTC)


def _text(*values: str) -> None:
    if any(type(v) is not str or not v.strip() for v in values):
        raise ValueError("nonempty invocation reference/text required")


@dataclass(frozen=True, slots=True)
class InvocationBounds:
    """Explicit task-specific resource bounds, not global Candidate rules."""

    max_response_bytes: int
    max_candidates: int
    max_list_items: int
    max_string_chars: int
    max_nesting_depth: int
    max_nodes: int
    max_input_chars: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError("positive invocation bounds required")


@dataclass(frozen=True, slots=True)
class SemanticTask:
    task_ref: str
    version: str
    instructions: str
    instruction_version: str
    transport_version: str = "1"
    rule_basis_refs: tuple[str, ...] = (
        "CPKS-SPEC-KM@0.22",
        "CPKS-SPEC-KM-VOC@0.1",
        "CPKS-SPEC-SRC@0.6",
        "CPKS-SPEC-KPR@0.5",
        "CPKS-SPEC-VAL@0.4",
        "CPKS-SPEC-SEC@0.4",
        "CPKS-SPEC-SEC-VOC@0.1",
        "CPKT-SPEC-ARCH@1.14",
    )

    @property
    def concrete_ref(self) -> str:
        return f"{self.task_ref}@{self.version}"


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    backend_ref: str
    backend_version: str
    method: str
    processing_zone: str
    provider_ref: str | None = None
    model_ref: str | None = None
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class InvocationPolicyContext:
    actor_ref: str
    purpose: str
    policy_config_ref: str
    profile_refs: tuple[str, ...]
    profile_applicability: ProfileApplicability
    agent_authority_context: str | None = None


@dataclass(frozen=True, slots=True)
class InvocationEvidenceBinding:
    handle: str
    address: EvidenceAddress
    normalized_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceData:
    handle: str
    content: str


@dataclass(frozen=True, slots=True)
class BackendRequest:
    invocation_ref: str
    run_ref: str
    correlation_ref: str
    task: SemanticTask
    backend: BackendIdentity
    bounds: InvocationBounds
    evidence: tuple[EvidenceData, ...]
    parameters: tuple[tuple[str, SemanticValue], ...]
    toolset: tuple[str, ...]
    policy_decision_ref: str
    configuration_fingerprint: str
    input_fingerprint: str


class SemanticBackend(Protocol):
    def invoke(self, request: BackendRequest) -> bytes:
        """Return untrusted UTF8 JSON; enforce bounds while receiving transport."""
        ...


class EvidenceResolver(Protocol):
    def resolve(self, captured: CapturedSource, address: EvidenceAddress) -> bool:
        """Trusted Source integrity port; grants no access/processing authority."""
        ...


@dataclass(frozen=True, slots=True)
class PreparedInvocation:
    task: SemanticTask
    backend: BackendIdentity
    bounds: InvocationBounds
    representations: tuple[NormalizedSourceRepresentation, ...]
    captures: tuple[CapturedSource, ...]
    evidence: tuple[InvocationEvidenceBinding, ...]
    resolver: EvidenceResolver
    policy: InvocationPolicyContext
    run_ref: str
    correlation_ref: str
    invocation_ref: str
    invoked_at: str
    parameters: tuple[tuple[str, SemanticValue], ...]
    toolset: tuple[str, ...]
    input_fingerprint: str
    configuration_fingerprint: str

    def input_payload(self) -> dict[str, object]:
        return {
            "representations": [rep.to_dict() for rep in self.representations],
            "captures": [
                {
                    "snapshot": asdict(c.snapshot),
                    "record": asdict(c.record),
                    "raw": asdict(c.raw_reference),
                }
                for c in self.captures
            ],
            "evidence": [asdict(e) for e in self.evidence],
        }

    def configuration_payload(self) -> dict[str, object]:
        return {
            "task": asdict(self.task),
            "backend": asdict(self.backend),
            "bounds": asdict(self.bounds),
            "policy": asdict(self.policy),
            "parameters": self.parameters,
            "toolset": self.toolset,
            "run_ref": self.run_ref,
            "correlation_ref": self.correlation_ref,
            "invocation_ref": self.invocation_ref,
            "invoked_at": self.invoked_at,
        }

    @property
    def policy_evaluation(self) -> PolicyEvaluationInput:
        scope = "semantic-invocation:" + canonical_json_hash(
            {
                "input": self.input_fingerprint,
                "config": self.configuration_fingerprint,
            }
        )
        subjects = tuple(
            PolicySubject(
                "evidence_address",
                e.address.evidence_address_ref,
                e.address.content_hash,
                "Source and Evidence",
            )
            for e in self.evidence
        ) + tuple(
            PolicySubject(
                "source_snapshot",
                c.snapshot.snapshot_ref,
                c.raw_reference.fingerprint.value,
                "Source and Evidence",
            )
            for c in self.captures
        )
        anchors = tuple(
            sorted(
                {p for c in self.captures for p in c.snapshot.policy_refs}
                | {p for e in self.evidence for p in e.address.policy_refs}
                | {
                    p
                    for rep in self.representations
                    for item in rep.records
                    for p in item.policy_refs
                }
                | {
                    p
                    for rep in self.representations
                    for item in rep.segments
                    for p in item.policy_refs
                }
            )
        )
        return PolicyEvaluationInput(
            policy_evaluation_ref=f"{self.invocation_ref}:policy",
            actor_or_consumer_ref=self.policy.actor_ref,
            purpose=self.policy.purpose,
            requested_operation=None,
            subject_refs=subjects,
            policy_config_ref=self.policy.policy_config_ref,
            processing_zone=self.backend.processing_zone,
            profile_refs=self.policy.profile_refs,
            profile_applicability=self.policy.profile_applicability,
            policy_anchor_ids=anchors,
            requested_at=self.invoked_at,
            context_valid_at=self.invoked_at,
            requested_action="process",
            requested_data_operations=(
                "read_content",
                "transform",
                "classify",
                "derive",
                "create",
            ),
            requested_effect_scope=scope,
            agent_authority_context=self.policy.agent_authority_context,
        )

    def validate(self) -> None:
        if (
            canonical_json_hash(self.input_payload()) != self.input_fingerprint
            or canonical_json_hash(self.configuration_payload())
            != self.configuration_fingerprint
        ):
            raise ValueError("invocation binding changed")
        _validate_grounding(self)


def _validate_grounding(invocation: PreparedInvocation) -> None:
    captures = {c.snapshot.snapshot_ref: c for c in invocation.captures}
    if len(captures) != len(invocation.captures) or not captures:
        raise ValueError("duplicate/missing snapshot")
    for captured_source in captures.values():
        captured_source.validate()
    if not invocation.representations or len(
        {rep.representation_ref for rep in invocation.representations}
    ) != len(invocation.representations):
        raise ValueError("duplicate/missing normalized representation")
    for rep in invocation.representations:
        rep.validate()
        for raw in rep.raw_references:
            capture = captures.get(raw.snapshot_ref)
            if (
                not capture
                or raw != capture.raw_reference
                or capture.record not in rep.source_records
            ):
                raise ValueError("normalized source dependency mismatch")
    seen: set[str] = set()
    seen_addresses: set[str] = set()
    for binding in invocation.evidence:
        address = binding.address
        if binding.handle in seen or address.evidence_address_ref in seen_addresses:
            raise ValueError("duplicate evidence handle/address")
        seen.add(binding.handle)
        seen_addresses.add(address.evidence_address_ref)
        captured = captures.get(address.snapshot_ref)
        if (
            not captured
            or (
                address.source_key,
                address.source_ref,
                address.record_ref,
                address.raw_content_ref,
            )
            != (
                captured.record.source_key,
                captured.record.source_ref,
                captured.record.record_ref,
                captured.raw_reference.raw_content_ref,
            )
            or sha256_text(address.text) != address.content_hash
        ):
            raise ValueError("source/snapshot/evidence integrity mismatch")
        if invocation.resolver.resolve(captured, address) is not True:
            raise ValueError("evidence address does not resolve")
        expected = _normalized_refs(invocation.representations, address)
        if not expected or expected != binding.normalized_refs:
            raise ValueError("evidence not bound to normalized input")
    if not seen or len(seen) > invocation.bounds.max_list_items:
        raise ValueError("evidence scope outside invocation bounds")
    if (
        sum(len(e.address.text) for e in invocation.evidence)
        > invocation.bounds.max_input_chars
    ):
        raise ValueError("input content exceeds invocation bound")


def _normalized_refs(
    representations: tuple[NormalizedSourceRepresentation, ...],
    address: EvidenceAddress,
) -> tuple[str, ...]:
    refs: set[str] = set()
    for rep in representations:
        items: tuple[NormalizedRecord | StructuredSegment, ...] = (
            *rep.records,
            *rep.segments,
        )
        for item in items:
            if address.text in item.content and any(
                (m.source_ref, m.snapshot_ref, m.record_ref, m.raw_content_ref)
                == (
                    address.source_ref,
                    address.snapshot_ref,
                    address.record_ref,
                    address.raw_content_ref,
                )
                for m in item.inputs
            ):
                refs.add(
                    item.segment_ref
                    if isinstance(item, StructuredSegment)
                    else item.normalized_record_ref
                )
    return tuple(sorted(refs))


def prepare_invocation(
    *,
    task: SemanticTask,
    backend: BackendIdentity,
    bounds: InvocationBounds,
    representations: tuple[NormalizedSourceRepresentation, ...],
    captures: tuple[CapturedSource, ...],
    evidence_addresses: tuple[EvidenceAddress, ...],
    resolver: EvidenceResolver,
    policy: InvocationPolicyContext,
    run_ref: str,
    correlation_ref: str,
    invocation_ref: str,
    invoked_at: str,
    parameters: tuple[tuple[str, SemanticValue], ...] = (),
    toolset: tuple[str, ...] = (),
) -> PreparedInvocation:
    from dataclasses import replace

    _text(
        task.task_ref,
        task.version,
        task.instructions,
        task.instruction_version,
        backend.backend_ref,
        backend.backend_version,
        backend.method,
        backend.processing_zone,
        policy.actor_ref,
        policy.purpose,
        policy.policy_config_ref,
        run_ref,
        correlation_ref,
        invocation_ref,
    )
    invoked_at = timestamp(invoked_at).isoformat()
    if task.transport_version != "1" or not task.rule_basis_refs:
        raise ValueError("unsupported semantic task contract")
    if type(parameters) is not tuple or len(dict(parameters)) != len(parameters):
        raise ValueError("invalid/duplicate backend parameters")
    for key, value in parameters:
        _text(key)
        if type(value) not in (str, int, float, bool, type(None)) or (
            type(value) is float and not math.isfinite(value)
        ):
            raise ValueError("invalid backend parameter value")
    if type(toolset) is not tuple or len(set(toolset)) != len(toolset):
        raise ValueError("invalid toolset")
    _text(*toolset)
    namespace = sha256_text(invocation_ref)[:24]
    evidence = tuple(
        InvocationEvidenceBinding(
            f"E:{namespace}:{i + 1}",
            address,
            _normalized_refs(representations, address),
        )
        for i, address in enumerate(evidence_addresses)
    )
    prepared = PreparedInvocation(
        task,
        backend,
        bounds,
        representations,
        captures,
        evidence,
        resolver,
        policy,
        run_ref,
        correlation_ref,
        invocation_ref,
        invoked_at,
        parameters,
        toolset,
        "",
        "",
    )
    prepared = replace(
        prepared,
        input_fingerprint=canonical_json_hash(prepared.input_payload()),
        configuration_fingerprint=canonical_json_hash(prepared.configuration_payload()),
    )
    prepared.validate()
    return prepared
