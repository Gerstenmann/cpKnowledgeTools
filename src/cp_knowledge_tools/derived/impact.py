"""Deterministic impact triage implementing CPKS-DEC-032 semantics."""

from __future__ import annotations

from enum import StrEnum

from .governance_state import DerivedGovernanceState, ReferenceEdge


class ImpactDisposition(StrEnum):
    NO_ACTION = "no_action"
    DERIVED_REFRESH = "derived_refresh"
    REVIEW_REQUIRED = "review_required"
    FOLLOWUP_CHANGE_REQUIRED = "followup_change_required"
    LIFECYCLE_ACTION_REQUIRED = "lifecycle_action_required"


class BaselineImpact(StrEnum):
    NONE = "none"
    DERIVED_STATE_ONLY = "derived_state_only"
    MATERIAL = "material"


MATERIAL_BASELINE_TOPICS = {
    "system_boundary",
    "primary_authority",
    "primary_component",
    "implementation_maturity",
    "operational_maturity",
    "system_exception",
    "committed_system_target",
}
DERIVED_BASELINE_TOPICS = {
    "active_version",
    "canonical_path",
    "file_count",
    "artifact_inventory",
    "decision_inventory",
    "dependency_inventory",
    "lifecycle_metadata",
}


def disposition_for_edge(
    edge: ReferenceEdge, *, material_change: bool = True
) -> ImpactDisposition:
    """Classify one reverse-reference edge without inventing semantic revalidation."""
    if edge.relation in {"validated_against", "implements_decisions", "supersedes"}:
        return ImpactDisposition.NO_ACTION
    if edge.relation == "related_decisions":
        return ImpactDisposition.NO_ACTION
    if edge.relation == "references":
        return ImpactDisposition.NO_ACTION
    if edge.relation in {"governed_by", "depends_on", "aligned_with"}:
        return (
            ImpactDisposition.REVIEW_REQUIRED
            if material_change
            else ImpactDisposition.DERIVED_REFRESH
        )
    return ImpactDisposition.NO_ACTION


def assess_impact(
    state: DerivedGovernanceState,
    changed_artifact_id: str,
    *,
    material_change: bool = True,
) -> dict[str, ImpactDisposition]:
    """Classify direct reverse-dependency candidates for one changed artifact line."""
    result: dict[str, ImpactDisposition] = {}
    priority = {
        ImpactDisposition.NO_ACTION: 0,
        ImpactDisposition.DERIVED_REFRESH: 1,
        ImpactDisposition.REVIEW_REQUIRED: 2,
        ImpactDisposition.FOLLOWUP_CHANGE_REQUIRED: 3,
        ImpactDisposition.LIFECYCLE_ACTION_REQUIRED: 4,
    }
    for edge in state.consumers_of(changed_artifact_id):
        disposition = disposition_for_edge(edge, material_change=material_change)
        old = result.get(edge.consumer_id)
        if old is None or priority[disposition] > priority[old]:
            result[edge.consumer_id] = disposition
    return result


def assess_baseline_impact(change_topics: set[str]) -> BaselineImpact:
    """Classify baseline impact by materiality rather than inventory drift."""
    if change_topics & MATERIAL_BASELINE_TOPICS:
        return BaselineImpact.MATERIAL
    if change_topics & DERIVED_BASELINE_TOPICS:
        return BaselineImpact.DERIVED_STATE_ONLY
    return BaselineImpact.NONE
