"""Plan targeted validation from derived impact candidates."""

from __future__ import annotations

from dataclasses import dataclass

from .governance_state import DerivedGovernanceState
from .impact import ImpactDisposition, assess_impact


@dataclass(frozen=True, slots=True)
class IncrementalValidationPlan:
    changed_artifact_id: str
    validate_artifact_ids: tuple[str, ...]
    refresh_only_artifact_ids: tuple[str, ...]
    no_action_artifact_ids: tuple[str, ...]


def plan_incremental_validation(
    state: DerivedGovernanceState,
    changed_artifact_id: str,
    *,
    material_change: bool = True,
) -> IncrementalValidationPlan:
    dispositions = assess_impact(
        state, changed_artifact_id, material_change=material_change
    )
    validate = sorted(
        artifact_id
        for artifact_id, disposition in dispositions.items()
        if disposition
        in {
            ImpactDisposition.REVIEW_REQUIRED,
            ImpactDisposition.FOLLOWUP_CHANGE_REQUIRED,
            ImpactDisposition.LIFECYCLE_ACTION_REQUIRED,
        }
    )
    refresh = sorted(
        artifact_id
        for artifact_id, disposition in dispositions.items()
        if disposition == ImpactDisposition.DERIVED_REFRESH
    )
    no_action = sorted(
        artifact_id
        for artifact_id, disposition in dispositions.items()
        if disposition == ImpactDisposition.NO_ACTION
    )
    return IncrementalValidationPlan(
        changed_artifact_id=changed_artifact_id,
        validate_artifact_ids=tuple(validate),
        refresh_only_artifact_ids=tuple(refresh),
        no_action_artifact_ids=tuple(no_action),
    )
