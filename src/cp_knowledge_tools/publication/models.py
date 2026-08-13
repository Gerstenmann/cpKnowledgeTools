from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PublicationSemanticReference:
    """Concrete reference used by a Publication Unit assembly input."""

    subject_type: str
    stable_id: str
    version: str = "0.1"
    authority_context: str = "Semantic Core"

    def to_dict(self) -> dict[str, str]:
        return {
            "subject_type": self.subject_type,
            "stable_id": self.stable_id,
            "version": self.version,
            "authority_context": self.authority_context,
        }

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.subject_type,
            self.stable_id,
            self.version,
            self.authority_context,
        )


@dataclass(frozen=True)
class PublicationApplicability:
    """Explicit applicability supplied by the publication caller."""

    domain_refs: tuple[PublicationSemanticReference, ...] = ()
    entity_refs: tuple[PublicationSemanticReference, ...] = ()
    organization_refs: tuple[PublicationSemanticReference, ...] = ()
    product_refs: tuple[PublicationSemanticReference, ...] = ()
    purposes: tuple[str, ...] = ()
    valid_time: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_refs": [item.to_dict() for item in self.domain_refs],
            "entity_refs": [item.to_dict() for item in self.entity_refs],
            "organization_refs": [item.to_dict() for item in self.organization_refs],
            "product_refs": [item.to_dict() for item in self.product_refs],
            "purposes": list(self.purposes),
            "valid_time": deepcopy(list(self.valid_time)),
        }


@dataclass(frozen=True)
class PublicationPolicyAnchor:
    """Policy metadata to embed without evaluating or inventing a decision."""

    policy_anchor_id: str
    subject_refs: tuple[PublicationSemanticReference, ...]
    policy_refs: tuple[str, ...]
    dimensions: tuple[str, ...]
    narrative_anchor: str
    policy_decision_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_anchor_id": self.policy_anchor_id,
            "subject_refs": [item.to_dict() for item in self.subject_refs],
            "policy_refs": list(self.policy_refs),
            "policy_decision_refs": list(self.policy_decision_refs),
            "dimensions": list(self.dimensions),
            "narrative_anchor": self.narrative_anchor,
        }


@dataclass(frozen=True)
class PublicationPolicyBinding:
    """Bind one concrete semantic subject to caller-selected policy anchors."""

    semantic_ref: PublicationSemanticReference
    policy_anchor_ids: tuple[str, ...]


@dataclass(frozen=True)
class PublicationInterpretationProvenance:
    producer_ref: PublicationSemanticReference
    method: str
    produced_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_ref": self.producer_ref.to_dict(),
            "method": self.method,
            "produced_at": self.produced_at,
        }


@dataclass(frozen=True)
class PublicationAssemblyPlan:
    """Caller-owned structural and policy inputs for one unpublished unit."""

    knowledge_object_id: str
    knowledge_object_version: str
    title: str
    language: str
    primary_kind: str
    knowledge_functions: tuple[str, ...]
    applicability: PublicationApplicability
    profile_refs: tuple[str, ...]
    policy_anchors: tuple[PublicationPolicyAnchor, ...]
    policy_bindings: tuple[PublicationPolicyBinding, ...]
    evidence_link_interpretation_provenance: PublicationInterpretationProvenance

    @property
    def knowledge_object_ref(self) -> PublicationSemanticReference:
        return PublicationSemanticReference(
            subject_type="knowledge_object",
            stable_id=self.knowledge_object_id,
            version=self.knowledge_object_version,
        )


@dataclass(frozen=True)
class PublicationRepresentationItem:
    """One caller-authored narrative item tied to a concrete semantic ref."""

    semantic_ref: PublicationSemanticReference
    narrative_anchor: str
    representation_role: str
    rendered_text: str
    heading: str
    mapping_id: str | None = None
    material: bool = False


@dataclass(frozen=True)
class PublicationRepresentationSection:
    """A rendered Markdown section and its optional cross-view mapping."""

    narrative_anchor: str
    heading: str
    rendered_text: str = ""
    semantic_ref: PublicationSemanticReference | None = None
    representation_role: str | None = None
    mapping_id: str | None = None
    material: bool = False
    items: tuple[PublicationRepresentationItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PublicationRepresentation:
    """Explicit human-readable view in Publication Unit section order."""

    summary: PublicationRepresentationSection
    applicability: PublicationRepresentationSection
    details: PublicationRepresentationSection
    claims: PublicationRepresentationSection
    events: PublicationRepresentationSection
    evidence: PublicationRepresentationSection
    conflicts: PublicationRepresentationSection
    policy: PublicationRepresentationSection
    publication: PublicationRepresentationSection
    body_language: str

    def sections(self) -> tuple[PublicationRepresentationSection, ...]:
        return (
            self.summary,
            self.applicability,
            self.details,
            self.claims,
            self.events,
            self.evidence,
            self.conflicts,
            self.policy,
            self.publication,
        )
