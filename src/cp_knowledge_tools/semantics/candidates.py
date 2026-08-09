from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SemanticValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    source_key: str
    source_ref: str
    snapshot_ref: str
    record_ref: str
    evidence_address_ref: str


@dataclass(frozen=True, slots=True)
class ExtractionProvenance:
    evidence_address_ref: str
    extractor_kind: str
    pattern: str
    capture_group: str | int
    parser: str
    parser_parameters: tuple[tuple[str, str], ...]
    extracted_text: str
    extracted_value: SemanticValue


@dataclass(frozen=True, slots=True)
class SemanticMappingProvenance:
    interpretation_rule_ref: str
    configured_fields: tuple[str, ...]
    value_mapping_from: SemanticValue = None
    value_mapping_to: SemanticValue = None


@dataclass(frozen=True, slots=True)
class ProducerProvenance:
    producer_ref: str
    producer_version: str
    method: str
    evidence: tuple[EvidenceProvenance, ...]
    extraction: ExtractionProvenance | None
    semantic_mapping: SemanticMappingProvenance


@dataclass(frozen=True, slots=True)
class ProposedEntity:
    entity_key: str
    label: str
    entity_class: str


@dataclass(frozen=True, slots=True)
class ProposedClaim:
    claim_key: str
    subject_entity_key: str | None
    predicate_ref: str | None
    value: SemanticValue
    object_entity_label: str | None = None
    statement: str | None = None
    time_modality: str | None = None
    value_qualifier: str | None = None


@dataclass(frozen=True, slots=True)
class ProposedEvent:
    event_key: str
    event_type_ref: str
    label: str
    event_time: str | None
    time_precision: str
    time_modality: str


@dataclass(frozen=True, slots=True)
class ProposedParticipation:
    participation_key: str
    entity_key: str
    event_key: str
    role: str


@dataclass(frozen=True, slots=True)
class ProposedRelationship:
    relationship_key: str
    subject_key: str
    predicate_ref: str
    object_key: str


@dataclass(frozen=True, slots=True)
class ProposedEvidenceLink:
    evidence_link_key: str
    evidence_address_ref: str
    role: str


@dataclass(frozen=True, slots=True)
class ProposedTime:
    role: str
    value: str | None
    precision: str
    modality: str


@dataclass(frozen=True, slots=True)
class EpistemicContext:
    status: str
    classification_basis: str


@dataclass(frozen=True, slots=True)
class Applicability:
    context_refs: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnownGap:
    gap_code: str
    interpretation_rule_ref: str
    detail: str
    evidence_address_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticCandidatePayload:
    """A non-canonical semantic proposal produced from Source/Evidence.

    ``candidate_payload_kind`` is deliberately implementation-local. This
    payload has no Candidate lifecycle identity or state, Review decision,
    canonicalization approval, Publication state, or Policy decision.
    """

    candidate_payload_kind: str
    interpretation_rule_ref: str
    proposed_entity: ProposedEntity | None = None
    proposed_claim: ProposedClaim | None = None
    proposed_event: ProposedEvent | None = None
    proposed_participation: ProposedParticipation | None = None
    proposed_relationship: ProposedRelationship | None = None
    evidence_links: tuple[ProposedEvidenceLink, ...] = ()
    time: tuple[ProposedTime, ...] = ()
    epistemic_context: EpistemicContext | None = None
    applicability: Applicability = Applicability()
    profile_refs: tuple[str, ...] = ()
    known_conflicts: tuple[str, ...] = ()
    known_gaps: tuple[KnownGap, ...] = ()
    producer_provenance: ProducerProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SemanticInterpretationResult:
    candidate_payloads: tuple[SemanticCandidatePayload, ...]
    known_gaps: tuple[KnownGap, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
