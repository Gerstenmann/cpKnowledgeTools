from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal

Independence = Literal[
    "independent",
    "dependent_or_derived",
    "shared_origin",
    "unknown",
]
ConflictOutcome = Literal[
    "hard_conflict",
    "qualification_or_compatible_difference",
]
TemporalBoundKind = Literal["lower", "upper", "interval"]

_INDEPENDENCE_VALUES = {
    "independent",
    "dependent_or_derived",
    "shared_origin",
    "unknown",
}
_TEMPORAL_BOUND_KINDS = {"lower", "upper", "interval"}


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class AtomicClaimLink:
    relationship_ref: str
    source_claim_ref: str
    target_claim_ref: str
    predicate: str

    def __post_init__(self) -> None:
        for field in (
            "relationship_ref",
            "source_claim_ref",
            "target_claim_ref",
            "predicate",
        ):
            _require_text(getattr(self, field), field)
        if self.source_claim_ref == self.target_claim_ref:
            raise ValueError("linked atomic Claim identities must remain distinct")

    @property
    def claim_refs(self) -> tuple[str, str]:
        return (self.source_claim_ref, self.target_claim_ref)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RationaleRelationship:
    relationship_ref: str
    reason_claim_ref: str
    target_ref: str
    evidence_link_ids: tuple[str, ...]
    profile_ref: str
    predicate: Literal["rationale_for"] = "rationale_for"
    causality_asserted: bool = False

    def __post_init__(self) -> None:
        for field in (
            "relationship_ref",
            "reason_claim_ref",
            "target_ref",
            "profile_ref",
        ):
            _require_text(getattr(self, field), field)
        if self.reason_claim_ref == self.target_ref:
            raise ValueError("Rationale Claim and explained target must be distinct")
        if not self.evidence_link_ids:
            raise ValueError("a reusable Rationale Claim requires Evidence")
        if self.predicate != "rationale_for" or self.causality_asserted:
            raise ValueError("rationale_for must not silently assert causality")

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "evidence_link_ids": list(self.evidence_link_ids),
        }


@dataclass(frozen=True, slots=True)
class ProgramOccurrenceRelationship:
    relationship_ref: str
    program_ref: str
    occurrence_ref: str
    predicate: Literal["part_of", "depends_on"]

    def __post_init__(self) -> None:
        for field in ("relationship_ref", "program_ref", "occurrence_ref"):
            _require_text(getattr(self, field), field)
        if self.program_ref == self.occurrence_ref:
            raise ValueError(
                "Program and concrete occurrence identities must be distinct"
            )
        if self.predicate not in {"part_of", "depends_on"}:
            raise ValueError(
                "Program/Occurrence relationship must be part_of or depends_on"
            )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvidenceDimensions:
    independence: Independence
    directness: str
    source_role: str
    formality: str
    competence: str
    claim_authority: str
    specificity: str
    temporal_proximity: str
    perspective: str

    def __post_init__(self) -> None:
        if self.independence not in _INDEPENDENCE_VALUES:
            raise ValueError(
                "independence must be independent, dependent_or_derived, "
                "shared_origin, or unknown"
            )
        for field in (
            "directness",
            "source_role",
            "formality",
            "competence",
            "claim_authority",
            "specificity",
            "temporal_proximity",
            "perspective",
        ):
            _require_text(getattr(self, field), field)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> EvidenceDimensions:
        return cls(**{field: value.get(field) for field in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    assessment_ref: str
    claim_ref: str
    purpose: str
    evidence_link_ids: tuple[str, ...]
    dimensions: EvidenceDimensions
    method: str
    assessed_by: str
    assessed_at: str
    uncertainty: str

    def __post_init__(self) -> None:
        for field in (
            "assessment_ref",
            "claim_ref",
            "purpose",
            "method",
            "assessed_by",
            "assessed_at",
        ):
            _require_text(getattr(self, field), field)
        if not self.evidence_link_ids:
            raise ValueError("Evidence Assessment requires concrete Evidence Links")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> EvidenceAssessment:
        return cls(
            assessment_ref=value.get("assessment_ref"),
            claim_ref=value.get("claim_ref"),
            purpose=value.get("purpose"),
            evidence_link_ids=tuple(value.get("evidence_link_ids", ())),
            dimensions=EvidenceDimensions.from_mapping(value.get("dimensions", {})),
            method=value.get("method"),
            assessed_by=value.get("assessed_by"),
            assessed_at=value.get("assessed_at"),
            uncertainty=value.get("uncertainty", "unknown"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_ref": self.assessment_ref,
            "claim_ref": self.claim_ref,
            "purpose": self.purpose,
            "evidence_link_ids": list(self.evidence_link_ids),
            "dimensions": self.dimensions.to_dict(),
            "method": self.method,
            "assessed_by": self.assessed_by,
            "assessed_at": self.assessed_at,
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True, slots=True)
class TemporalConstraint:
    constraint_ref: str
    subject_ref: str
    bound_kind: TemporalBoundKind
    lower_bound: str | None
    upper_bound: str | None
    precision: str
    modality: str
    input_refs: tuple[str, ...]
    evidence_link_ids: tuple[str, ...]
    rule_ref: str
    derivation_provenance: tuple[str, ...]
    certainty: Literal["deterministic"] = "deterministic"
    derivation_kind: str = "deterministic_rule"

    def __post_init__(self) -> None:
        for field in (
            "constraint_ref",
            "subject_ref",
            "bound_kind",
            "precision",
            "modality",
            "rule_ref",
            "derivation_kind",
        ):
            _require_text(getattr(self, field), field)
        if self.lower_bound is None and self.upper_bound is None:
            raise ValueError("Temporal Constraint requires at least one hard bound")
        if self.bound_kind not in _TEMPORAL_BOUND_KINDS:
            raise ValueError("bound_kind must be one of lower, upper, or interval")
        if self.bound_kind == "lower" and self.lower_bound is None:
            raise ValueError("bound_kind lower requires lower_bound")
        if self.bound_kind == "upper" and self.upper_bound is None:
            raise ValueError("bound_kind upper requires upper_bound")
        if not self.input_refs or not self.evidence_link_ids:
            raise ValueError(
                "Temporal Constraint requires Input and Evidence references"
            )
        if not self.derivation_provenance:
            raise ValueError("Temporal Constraint requires derivation provenance")
        if self.certainty != "deterministic":
            raise ValueError("hard Temporal Constraint certainty must be deterministic")
        if "probabil" in self.derivation_kind.lower() or "plausib" in (
            self.derivation_kind.lower()
        ):
            raise ValueError(
                "probabilistic inference cannot populate a hard Temporal Constraint"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TemporalConstraint:
        return cls(
            constraint_ref=value.get("constraint_ref"),
            subject_ref=value.get("subject_ref"),
            bound_kind=value.get("bound_kind"),
            lower_bound=value.get("lower_bound"),
            upper_bound=value.get("upper_bound"),
            precision=value.get("precision"),
            modality=value.get("modality"),
            input_refs=tuple(value.get("input_refs", ())),
            evidence_link_ids=tuple(value.get("evidence_link_ids", ())),
            rule_ref=value.get("rule_ref"),
            derivation_provenance=tuple(value.get("derivation_provenance", ())),
            certainty=value.get("certainty", "deterministic"),
            derivation_kind=value.get("derivation_kind", "deterministic_rule"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "input_refs": list(self.input_refs),
            "evidence_link_ids": list(self.evidence_link_ids),
            "derivation_provenance": list(self.derivation_provenance),
        }


@dataclass(frozen=True, slots=True)
class CompatibilityChecks:
    time: bool
    context: bool
    perspective: bool
    observation_granularity: bool
    qualification: bool

    @classmethod
    def all_checked(cls) -> CompatibilityChecks:
        return cls(True, True, True, True, True)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CompatibilityChecks:
        return cls(
            time=value.get("time") is True,
            context=value.get("context") is True,
            perspective=value.get("perspective") is True,
            observation_granularity=(value.get("observation_granularity") is True),
            qualification=value.get("qualification") is True,
        )

    @property
    def complete(self) -> bool:
        return all(asdict(self).values())

    def to_canonical_dict(self) -> dict[str, bool]:
        """Translate the internal domain names to the active KM-PU shape."""

        return {
            "time_scope_checked": self.time,
            "context_checked": self.context,
            "perspective_checked": self.perspective,
            "granularity_checked": self.observation_granularity,
            "qualification_checked": self.qualification,
        }


@dataclass(frozen=True, slots=True)
class ConflictCompatibilityAssessment:
    assessment_ref: str
    claim_refs: tuple[str, ...]
    checks: CompatibilityChecks
    remaining_material_incompatibility: bool
    outcome: ConflictOutcome

    def __post_init__(self) -> None:
        _require_text(self.assessment_ref, "assessment_ref")
        if len(set(self.claim_refs)) < 2:
            raise ValueError("Conflict assessment requires distinct Claim identities")
        if self.outcome == "hard_conflict":
            if not self.checks.complete:
                raise ValueError("hard Conflict requires all compatibility checks")
            if not self.remaining_material_incompatibility:
                raise ValueError(
                    "hard Conflict requires remaining material incompatibility"
                )
        elif self.outcome == "qualification_or_compatible_difference":
            if self.remaining_material_incompatibility:
                raise ValueError(
                    "compatible difference cannot retain hard incompatibility"
                )
        else:
            raise ValueError(f"unsupported Conflict outcome: {self.outcome!r}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ConflictCompatibilityAssessment:
        return cls(
            assessment_ref=value.get("assessment_ref"),
            claim_refs=tuple(value.get("claim_refs", ())),
            checks=CompatibilityChecks.from_mapping(value.get("checks", {})),
            remaining_material_incompatibility=(
                value.get("remaining_material_incompatibility") is True
            ),
            outcome=value.get("outcome"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_ref": self.assessment_ref,
            "claim_refs": list(self.claim_refs),
            "checks": asdict(self.checks),
            "remaining_material_incompatibility": (
                self.remaining_material_incompatibility
            ),
            "outcome": self.outcome,
        }

    def to_canonical_conflict_fields(self) -> dict[str, Any]:
        """Encode this domain assessment into canonical KM-PU conflict fields."""

        return {
            "compatibility_checks": self.checks.to_canonical_dict(),
            "conflict_classification": self.outcome,
        }


_IDENTITY_FIELDS = {
    "entities": "entity_ref",
    "claims": "claim_ref",
    "events": "event_ref",
    "relationships": "relationship_ref",
    "evidence_links": "evidence_link_id",
}


def integrate_cumulative_knowledge_state(
    baseline: Mapping[str, list[dict[str, Any]]],
    increment: Mapping[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Add knowledge without discarding or silently rewriting prior state."""

    result: dict[str, list[dict[str, Any]]] = {}
    for collection, identity_field in _IDENTITY_FIELDS.items():
        baseline_items = deepcopy(list(baseline.get(collection, ())))
        increment_items = deepcopy(list(increment.get(collection, ())))
        by_identity: dict[str, dict[str, Any]] = {}
        ordered: list[dict[str, Any]] = []
        for item in (*baseline_items, *increment_items):
            identity = item.get(identity_field)
            _require_text(identity, f"{collection}.{identity_field}")
            previous = by_identity.get(identity)
            if previous is None:
                by_identity[identity] = item
                ordered.append(item)
            elif previous != item:
                raise ValueError(
                    f"cumulative state collision for {collection} identity {identity!r}"
                )
        result[collection] = ordered
    return result
