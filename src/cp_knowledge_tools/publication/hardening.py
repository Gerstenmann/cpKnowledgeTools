from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from cp_knowledge_tools.semantics.hardening import ConflictCompatibilityAssessment
from cp_knowledge_tools.validation.hardening import HardeningContractValidator

_EPISTEMIC_CONTEXT_LIST_FIELDS = (
    "source_role_refs",
    "perspective_refs",
    "evidence_assessment_refs",
    "qualification_claim_refs",
    "observation_context_refs",
)


@dataclass(frozen=True, slots=True)
class HardeningPublicationContext:
    claim_refs: tuple[str, ...]
    claim_relationships: tuple[dict[str, Any], ...]
    program_occurrences: tuple[dict[str, Any], ...]
    evidence_assessments: tuple[dict[str, Any], ...]
    temporal_constraints: tuple[dict[str, Any], ...]
    conflict_compatibility_assessments: tuple[dict[str, Any], ...]
    epistemic_context: tuple[dict[str, Any], ...]
    delivery_context: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> HardeningPublicationContext:
        result = HardeningContractValidator().validate(value)
        if not result.valid:
            codes = ", ".join(item.code for item in result.diagnostics)
            raise ValueError(f"invalid hardening publication context: {codes}")
        return cls(
            claim_refs=tuple(value.get("claim_refs", ())),
            claim_relationships=tuple(
                deepcopy(list(value.get("claim_relationships", ())))
            ),
            program_occurrences=tuple(
                deepcopy(list(value.get("program_occurrences", ())))
            ),
            evidence_assessments=tuple(
                deepcopy(list(value.get("evidence_assessments", ())))
            ),
            temporal_constraints=tuple(
                deepcopy(list(value.get("temporal_constraints", ())))
            ),
            conflict_compatibility_assessments=tuple(
                deepcopy(list(value.get("conflict_compatibility_assessments", ())))
            ),
            epistemic_context=tuple(deepcopy(list(value.get("epistemic_context", ())))),
            delivery_context=deepcopy(dict(value.get("delivery_context", {}))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_refs": list(self.claim_refs),
            "claim_relationships": deepcopy(list(self.claim_relationships)),
            "program_occurrences": deepcopy(list(self.program_occurrences)),
            "evidence_assessments": deepcopy(list(self.evidence_assessments)),
            "temporal_constraints": deepcopy(list(self.temporal_constraints)),
            "conflict_compatibility_assessments": deepcopy(
                list(self.conflict_compatibility_assessments)
            ),
            "epistemic_context": deepcopy(list(self.epistemic_context)),
            "delivery_context": deepcopy(self.delivery_context),
        }

    def canonical_publication_fields(
        self,
        *,
        claim_refs: tuple[str, ...],
        conflict_claim_refs: tuple[tuple[str, ...], ...],
    ) -> dict[str, Any]:
        """Bind sidecar domain state to the active canonical KM-PU field shape."""

        expected_claims = set(claim_refs)
        if set(self.claim_refs) != expected_claims:
            raise ValueError(
                "hardening Claim references must match the Publication Unit"
            )

        contexts: dict[str, dict[str, Any]] = {}
        for value in self.epistemic_context:
            claim_ref = value.get("claim_ref")
            if claim_ref not in expected_claims or claim_ref in contexts:
                raise ValueError(
                    "epistemic_context must bind each Publication Claim exactly once"
                )
            if any(
                not isinstance(value.get(field), list)
                for field in _EPISTEMIC_CONTEXT_LIST_FIELDS
            ) or not isinstance(value.get("confidence_dimensions"), dict):
                raise ValueError("epistemic_context has an incomplete canonical shape")
            contexts[claim_ref] = deepcopy(value)
        if set(contexts) != expected_claims:
            raise ValueError(
                "epistemic_context must bind each Publication Claim exactly once"
            )

        assessment_refs: set[str] = set()
        for assessment in self.evidence_assessments:
            assessment_ref = assessment.get("assessment_ref")
            if (
                not isinstance(assessment_ref, str)
                or not assessment_ref
                or assessment_ref in assessment_refs
                or assessment.get("claim_ref") not in expected_claims
            ):
                raise ValueError(
                    "Evidence Assessments require unique local Claim-bound references"
                )
            assessment_refs.add(assessment_ref)
        for claim_ref, context in contexts.items():
            unresolved = set(context["evidence_assessment_refs"]) - assessment_refs
            if unresolved:
                raise ValueError(
                    f"Claim {claim_ref!r} has unresolved Evidence Assessments"
                )
            unknown_qualifications = (
                set(context["qualification_claim_refs"]) - expected_claims
            )
            if unknown_qualifications:
                raise ValueError(
                    f"Claim {claim_ref!r} has unresolved Qualification Claims"
                )

        conflict_fields: dict[tuple[str, ...], dict[str, Any]] = {}
        for value in self.conflict_compatibility_assessments:
            assessment = ConflictCompatibilityAssessment.from_mapping(value)
            key = tuple(sorted(assessment.claim_refs))
            if key in conflict_fields:
                raise ValueError("Conflict compatibility assessment is duplicated")
            conflict_fields[key] = assessment.to_canonical_conflict_fields()
        expected_conflicts = {tuple(sorted(refs)) for refs in conflict_claim_refs}
        if set(conflict_fields) != expected_conflicts:
            raise ValueError(
                "each canonical conflict_set requires one compatibility assessment"
            )

        return {
            "evidence_assessments": deepcopy(list(self.evidence_assessments)),
            "temporal_constraints": deepcopy(list(self.temporal_constraints)),
            "claim_fields": {
                claim_ref: {
                    "epistemic_context": {
                        field: deepcopy(context[field])
                        for field in (
                            "source_role_refs",
                            "perspective_refs",
                            "evidence_assessment_refs",
                            "qualification_claim_refs",
                            "observation_context_refs",
                            "confidence_dimensions",
                        )
                    },
                    "evidence_assessment_refs": deepcopy(
                        context["evidence_assessment_refs"]
                    ),
                    "qualification_claim_refs": deepcopy(
                        context["qualification_claim_refs"]
                    ),
                }
                for claim_ref, context in contexts.items()
            },
            "conflict_fields": conflict_fields,
        }
