from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cp_knowledge_tools.semantics.hardening import (
    ConflictCompatibilityAssessment,
    EvidenceAssessment,
    ProgramOccurrenceRelationship,
    TemporalConstraint,
)

_REQUIRED_ASSESSMENT_DIMENSIONS = {
    "independence",
    "directness",
    "source_role",
    "formality",
    "competence",
    "claim_authority",
    "specificity",
    "temporal_proximity",
    "perspective",
}
_CANONICAL_COMPATIBILITY_CHECKS = {
    "time_scope_checked",
    "context_checked",
    "perspective_checked",
    "granularity_checked",
    "qualification_checked",
}
_CONFLICT_CLASSIFICATIONS = {
    "hard_conflict",
    "qualification_or_compatible_difference",
}


@dataclass(frozen=True, slots=True)
class HardeningDiagnostic:
    code: str
    path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class HardeningValidationResult:
    diagnostics: tuple[HardeningDiagnostic, ...]

    @property
    def valid(self) -> bool:
        return not self.diagnostics


class HardeningContractValidator:
    """Read-only validation of the Post-R5 publication contract additions."""

    def validate(self, value: Mapping[str, Any]) -> HardeningValidationResult:
        diagnostics: list[HardeningDiagnostic] = []

        required_fields = {
            "claim_refs",
            "claim_relationships",
            "program_occurrences",
            "evidence_assessments",
            "temporal_constraints",
            "conflict_compatibility_assessments",
            "epistemic_context",
            "delivery_context",
        }
        for field in sorted(required_fields - set(value)):
            self._add(
                diagnostics,
                "hardening_contract_field_missing",
                f"/{field}",
                f"Required hardening contract field {field!r} is missing.",
            )

        if value.get("composite_claims"):
            self._add(
                diagnostics,
                "atomic_claim_identity_collapsed",
                "/composite_claims",
                "Atomic Claims must remain separate and explicitly related.",
            )

        for index, relationship in enumerate(value.get("claim_relationships", ())):
            predicate = relationship.get("predicate")
            if predicate == "causes" and (
                relationship.get("relationship_ref", "").lower().find("rationale") >= 0
            ):
                self._add(
                    diagnostics,
                    "rationale_not_structured_or_causality_invented",
                    f"/claim_relationships/{index}",
                    "Source-backed Rationale must use rationale_for, not causes.",
                )
            if predicate == "rationale_for" and not relationship.get(
                "evidence_link_ids"
            ):
                self._add(
                    diagnostics,
                    "rationale_not_structured_or_causality_invented",
                    f"/claim_relationships/{index}/evidence_link_ids",
                    "Rationale Claim requires Evidence.",
                )
            if predicate == "rationale_for" and not relationship.get("profile_ref"):
                self._add(
                    diagnostics,
                    "rationale_not_structured_or_causality_invented",
                    f"/claim_relationships/{index}/profile_ref",
                    "rationale_for must be owned by a concrete Profile.",
                )

        for index, relationship in enumerate(value.get("program_occurrences", ())):
            try:
                ProgramOccurrenceRelationship(
                    relationship_ref=relationship.get(
                        "relationship_ref", f"PROGRAM-OCCURRENCE-{index}"
                    ),
                    program_ref=relationship.get("program_ref"),
                    occurrence_ref=relationship.get("occurrence_ref"),
                    predicate=relationship.get("predicate"),
                )
            except (TypeError, ValueError) as error:
                self._add(
                    diagnostics,
                    "program_occurrence_identity_collapsed",
                    f"/program_occurrences/{index}",
                    str(error),
                )

        for index, assessment in enumerate(value.get("evidence_assessments", ())):
            path = f"/evidence_assessments/{index}"
            if assessment.get("independence_basis") == "source_count":
                self._add(
                    diagnostics,
                    "independence_inferred_from_source_count",
                    f"{path}/independence_basis",
                    "Evidence source count cannot establish Independence.",
                )
            if "global_score" in assessment:
                self._add(
                    diagnostics,
                    "evidence_dimensions_replaced_by_global_score",
                    f"{path}/global_score",
                    "A global score cannot replace Evidence dimensions.",
                )
            dimensions = assessment.get("dimensions", {})
            if set(dimensions) != _REQUIRED_ASSESSMENT_DIMENSIONS:
                self._add(
                    diagnostics,
                    "evidence_assessment_incomplete",
                    f"{path}/dimensions",
                    "Every required Evidence dimension must remain inspectable.",
                )
            else:
                try:
                    EvidenceAssessment.from_mapping(assessment)
                except (TypeError, ValueError) as error:
                    self._add(
                        diagnostics,
                        "evidence_assessment_incomplete",
                        path,
                        str(error),
                    )

        for index, constraint in enumerate(value.get("temporal_constraints", ())):
            try:
                TemporalConstraint.from_mapping(constraint)
            except (TypeError, ValueError) as error:
                self._add(
                    diagnostics,
                    "probabilistic_inference_marked_deterministic",
                    f"/temporal_constraints/{index}",
                    str(error),
                )

        for index, assessment in enumerate(
            value.get("conflict_compatibility_assessments", ())
        ):
            try:
                ConflictCompatibilityAssessment.from_mapping(assessment)
            except (TypeError, ValueError) as error:
                self._add(
                    diagnostics,
                    "hard_conflict_without_compatibility_checks",
                    f"/conflict_compatibility_assessments/{index}",
                    str(error),
                )

        delivery = value.get("delivery_context", {})
        if delivery.get("equivalent_unresolved_alternative_refs"):
            self._add(
                diagnostics,
                "correction_history_rendered_as_equal_alternative",
                "/delivery_context/equivalent_unresolved_alternative_refs",
                "Correction History cannot be an equal current alternative.",
            )
        if (
            delivery.get("current_opportunity") is True
            and delivery.get("currentness") != "verified_current"
        ):
            self._add(
                diagnostics,
                "historical_openness_projected_as_current",
                "/delivery_context/current_opportunity",
                "Current Opportunity requires verified_current.",
            )

        return HardeningValidationResult(tuple(diagnostics))

    def validate_publication_manifest(
        self, value: Mapping[str, Any]
    ) -> HardeningValidationResult:
        """Validate canonical hardening fields on an actual Publication Unit."""

        diagnostics: list[HardeningDiagnostic] = []
        hardening_present = (
            "evidence_assessments" in value
            or "temporal_constraints" in value
            or any(
                isinstance(claim, Mapping) and "epistemic_context" in claim
                for claim in value.get("claims", ())
            )
        )
        if not hardening_present:
            return HardeningValidationResult(())

        for field in ("evidence_assessments", "temporal_constraints"):
            if not isinstance(value.get(field), list):
                self._add(
                    diagnostics,
                    "canonical_hardening_field_missing",
                    f"/{field}",
                    f"Canonical Publication field {field!r} is required.",
                )

        claims = value.get("claims", ())
        claim_refs = {
            claim.get("claim_ref", {}).get("stable_id")
            for claim in claims
            if isinstance(claim, Mapping)
            and isinstance(claim.get("claim_ref"), Mapping)
        }
        assessment_refs: set[str] = set()
        for index, assessment in enumerate(value.get("evidence_assessments", ())):
            path = f"/evidence_assessments/{index}"
            try:
                parsed = EvidenceAssessment.from_mapping(assessment)
            except (AttributeError, TypeError, ValueError) as error:
                self._add(
                    diagnostics,
                    "canonical_evidence_assessment_invalid",
                    path,
                    str(error),
                )
                continue
            if parsed.claim_ref not in claim_refs or parsed.assessment_ref in (
                assessment_refs
            ):
                self._add(
                    diagnostics,
                    "canonical_evidence_assessment_invalid",
                    path,
                    "Evidence Assessment must have unique local Claim binding.",
                )
            assessment_refs.add(parsed.assessment_ref)

        for index, constraint in enumerate(value.get("temporal_constraints", ())):
            try:
                TemporalConstraint.from_mapping(constraint)
            except (AttributeError, TypeError, ValueError) as error:
                self._add(
                    diagnostics,
                    "canonical_temporal_constraint_invalid",
                    f"/temporal_constraints/{index}",
                    str(error),
                )

        for index, claim in enumerate(claims):
            if not isinstance(claim, Mapping):
                continue
            context = claim.get("epistemic_context")
            if not isinstance(context, Mapping):
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}/epistemic_context",
                    "Claim epistemic_context is required.",
                )
                continue
            required_lists = (
                "source_role_refs",
                "perspective_refs",
                "evidence_assessment_refs",
                "qualification_claim_refs",
                "observation_context_refs",
            )
            if any(
                not isinstance(context.get(field), list) for field in required_lists
            ):
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}/epistemic_context",
                    "Claim epistemic_context collections are incomplete.",
                )
            if not isinstance(context.get("confidence_dimensions"), Mapping):
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}/epistemic_context/confidence_dimensions",
                    "Claim confidence_dimensions must be an object.",
                )
            if claim.get("evidence_assessment_refs") != context.get(
                "evidence_assessment_refs"
            ) or claim.get("qualification_claim_refs") != context.get(
                "qualification_claim_refs"
            ):
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}",
                    "Claim hardening references must match epistemic_context.",
                )
            if set(context.get("evidence_assessment_refs", ())) - assessment_refs:
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}/evidence_assessment_refs",
                    "Claim Evidence Assessment reference does not resolve.",
                )
            if set(context.get("qualification_claim_refs", ())) - claim_refs:
                self._add(
                    diagnostics,
                    "canonical_epistemic_context_invalid",
                    f"/claims/{index}/qualification_claim_refs",
                    "Claim Qualification reference does not resolve.",
                )

        for index, conflict in enumerate(value.get("conflict_sets", ())):
            if not isinstance(conflict, Mapping):
                continue
            checks = conflict.get("compatibility_checks")
            classification = conflict.get("conflict_classification")
            valid_checks = (
                isinstance(checks, Mapping)
                and set(checks) == _CANONICAL_COMPATIBILITY_CHECKS
                and all(isinstance(checks[field], bool) for field in checks)
            )
            valid = valid_checks and classification in _CONFLICT_CLASSIFICATIONS
            if classification == "hard_conflict":
                valid = valid and all(checks.values())
            if not valid:
                self._add(
                    diagnostics,
                    "canonical_conflict_contract_invalid",
                    f"/conflict_sets/{index}",
                    "Canonical Conflict compatibility or classification is invalid.",
                )

        return HardeningValidationResult(tuple(diagnostics))

    def _add(
        self,
        diagnostics: list[HardeningDiagnostic],
        code: str,
        path: str,
        message: str,
    ) -> None:
        diagnostics.append(HardeningDiagnostic(code=code, path=path, message=message))
