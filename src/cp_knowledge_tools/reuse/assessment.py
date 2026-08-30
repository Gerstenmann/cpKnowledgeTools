"""Assessment validation and handover; judgments come from the reviewing agent."""

from __future__ import annotations

from typing import Protocol

from cp_knowledge_tools.platform.hashing import canonical_json_hash

from .models import (
    COMPARISON_DIMENSIONS,
    CandidateAssessment,
    CandidateFacts,
    DependencyAcceptanceState,
    IntegrationHandover,
    InternalInspection,
    LicenseState,
    ResearchGateResult,
    ReuseAssessment,
    ReuseDisposition,
    ReuseError,
)


class DecisionSource(Protocol):
    """Trusted host adapter for reviewed decisions, never candidate-owned JSON.

    Resolve current decisions and live rule homes outside the core. The host must
    enforce reviewer authority, applicable policy and condition fulfilment.
    A request, stored preview or candidate metadata must not mint acceptance.
    """

    def resolve(self, assessment_id: str, candidate_id: str) -> CandidateAssessment: ...


def research_gate(
    inspection: InternalInspection, *, internal_sufficient: bool, rationale: str
) -> ResearchGateResult:
    if not rationale.strip() or not inspection.fingerprint:
        raise ReuseError("research gate requires inspection and a rationale")
    # The agent applies live DEV-P05. Text/symbol matches cannot prove fit.
    return ResearchGateResult(
        "not_required" if internal_sufficient else "required",
        rationale,
        inspection.fingerprint,
    )


def validate_assessment(assessment: ReuseAssessment) -> tuple[str, ...]:
    errors = []
    if not isinstance(assessment.overall_strategy, ReuseDisposition):
        errors.append("unknown overall reuse disposition")
    if (
        assessment.research_gate.status not in {"required", "not_required"}
        or not assessment.research_gate.rationale.strip()
        or not assessment.research_question.question.strip()
    ):
        errors.append("research gate and question must be explicit")
    facts = {f.snapshot.candidate_id: f for f in assessment.candidates}
    decisions = {d.candidate_id: d for d in assessment.decisions}
    comparisons = {c.candidate_id: c for c in assessment.comparison}
    if len(facts) != len(assessment.candidates):
        errors.append("duplicate candidates")
    if len(decisions) != len(assessment.decisions) or len(comparisons) != len(
        assessment.comparison
    ):
        errors.append("duplicate decisions or comparisons")
    if facts.keys() != decisions.keys() or facts.keys() != comparisons.keys():
        errors.append("every representative candidate needs comparison and decision")
    for candidate_id, fact in facts.items():
        decision = decisions.get(candidate_id)
        if decision and not isinstance(decision.disposition, ReuseDisposition):
            errors.append(f"unknown candidate disposition: {candidate_id}")
        if decision and (
            decision.assessment_id != assessment.assessment_id
            or decision.snapshot_fingerprint != fact.snapshot.fingerprint
            or not decision.rationale.strip()
        ):
            errors.append(f"unbound or unexplained decision: {candidate_id}")
        comparison = comparisons.get(candidate_id)
        if comparison and (
            set(dict(comparison.dimensions)) != set(COMPARISON_DIMENSIONS)
            or not all(v.strip() for _, v in comparison.dimensions)
            or len(comparison.dimensions) != len(COMPARISON_DIMENSIONS)
        ):
            errors.append(f"incomplete comparison: {candidate_id}")
    if not all(
        (
            assessment.decision_rationale.strip(),
            assessment.representative_set_rationale.strip(),
            assessment.internal_alternative.strip(),
            assessment.build_alternative.strip(),
        )
    ):
        errors.append("strategy, representative scope and alternatives need rationales")
    if (
        assessment.research_gate.internal_inspection_fingerprint
        != assessment.internal_inspection.fingerprint
    ):
        errors.append("research gate not bound to internal inspection")
    return tuple(errors)


def accepted_decision(
    facts: CandidateFacts, decisions: DecisionSource, assessment_id: str
) -> CandidateAssessment:
    decision = decisions.resolve(assessment_id, facts.snapshot.candidate_id)
    if (
        decision.assessment_id != assessment_id
        or decision.candidate_id != facts.snapshot.candidate_id
        or decision.snapshot_fingerprint != facts.snapshot.fingerprint
    ):
        raise ReuseError("decision not bound to assessed candidate snapshot")
    if (
        decision.acceptance
        not in {
            DependencyAcceptanceState.ACCEPTED,
            DependencyAcceptanceState.ACCEPTED_WITH_CONDITIONS,
        }
        or decision.hard_blocks
        or decision.unresolved_conditions
    ):
        raise ReuseError("acceptance review_required or blocked")
    if (
        not decision.decision_ref
        or not decision.rationale
        or not decision.policy_refs
        or not decision.security_finding
    ):
        raise ReuseError(
            "acceptance requires reviewed decision and live policy references"
        )
    if (
        facts.license_state is LicenseState.CONFLICTING
        or not decision.license_resolved
        or not decision.license_finding
        or not decision.license_expression
        or decision.license_expression.casefold() in {"unknown", "unresolved", "none"}
        or not decision.license_evidence_paths
    ):
        raise ReuseError("license review_required")
    available = {
        e.path
        for e in facts.evidence
        if e.kind in {"declared_license", "license_metadata"}
        or e.kind == "license_file"
        and e.value == "nonempty"
    }
    if not set(decision.license_evidence_paths) <= available:
        raise ReuseError("license evidence unresolved")
    if (
        facts.declared_licenses
        and decision.license_expression not in facts.declared_licenses
    ):
        raise ReuseError("license decision conflicts with declared evidence")
    # A plain LICENSE may be resolved by the trusted reviewer; no text guessing.
    return decision


def integration_handover(
    facts: CandidateFacts,
    decisions: DecisionSource,
    *,
    assessment_id: str,
    integration_boundary: str,
    dependency_specification: str,
    verification_steps: tuple[str, ...],
) -> IntegrationHandover:
    decision = accepted_decision(facts, decisions, assessment_id)
    if decision.disposition not in {ReuseDisposition.USE, ReuseDisposition.WRAP}:
        raise ReuseError("integration handover requires USE or WRAP")
    if (
        not integration_boundary
        or not dependency_specification
        or not verification_steps
    ):
        raise ReuseError("integration boundary, pin strategy and verification required")
    return IntegrationHandover(
        assessment_id,
        facts.snapshot.candidate_id,
        decision.disposition,
        facts.snapshot.source,
        facts.snapshot.commit,
        integration_boundary,
        dependency_specification,
        verification_steps,
    )


def decision_fingerprint(decision: CandidateAssessment) -> str:
    from cp_knowledge_tools.operations.results import to_primitive

    return canonical_json_hash(to_primitive(decision))
