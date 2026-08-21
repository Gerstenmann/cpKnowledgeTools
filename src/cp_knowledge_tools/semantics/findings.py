from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal

from cp_knowledge_tools.platform.hashing import stable_token

FindingDisposition = Literal["finding", "no_finding", "blocked"]


@dataclass(frozen=True, slots=True)
class SemanticState:
    """Source-neutral semantic state used for material-delta comparison."""

    semantic_payload: Mapping[str, Any] | None
    evidence_refs: tuple[str, ...] = ()
    time_scope: tuple[str, ...] = ()
    epistemic_state: str | None = None
    conflict_refs: tuple[str, ...] = ()
    applicability: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_payload": (
                deepcopy(dict(self.semantic_payload))
                if self.semantic_payload is not None
                else None
            ),
            "evidence_refs": list(self.evidence_refs),
            "time_scope": list(self.time_scope),
            "epistemic_state": self.epistemic_state,
            "conflict_refs": list(self.conflict_refs),
            "applicability": list(self.applicability),
        }


@dataclass(frozen=True, slots=True)
class FindingInput:
    """Evidence-grounded observation to evaluate against a relevant prior state."""

    task_ref: str
    source_result_ref: str
    source_ref: str
    subject_refs: tuple[str, ...]
    prior_state_ref: str | None
    prior_state: SemanticState | None
    observed_state: SemanticState
    description: str
    delta_class: tuple[str, ...]
    evidence_content_read: bool
    content_read_authorized: bool
    evidence_resolvable: bool
    semantic_assertion: bool
    finding_type: str = "observation"
    uncertainty_or_conflict: tuple[str, ...] = ()
    prohibited_inferences: tuple[str, ...] = ()
    attempted_inferences: tuple[str, ...] = ()
    event_time: str | None = None
    producer_ref: str = "cpKnowledgeTools"
    tool_or_model_ref: str = "material-delta-finding-evaluator@0.1"


@dataclass(frozen=True, slots=True)
class KnowledgeFinding:
    """Immutable non-canonical Finding produced from a material semantic delta."""

    finding_ref: str
    finding_revision: str
    task_ref: str
    source_continuation_result_ref: str
    source_ref: str
    subject_refs: tuple[str, ...]
    prior_state_ref: str | None
    finding_type: str
    description: str
    delta_class: tuple[str, ...]
    semantic_observation: dict[str, Any] | None
    evidence_refs: tuple[str, ...]
    time_scope: tuple[str, ...]
    epistemic_state: str | None
    uncertainty_or_conflict: tuple[str, ...]
    material_delta: bool
    material_delta_dimensions: tuple[str, ...]
    non_canonical: bool
    event_time: str | None
    producer_ref: str
    tool_or_model_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FindingEvaluation:
    disposition: FindingDisposition
    reason_code: str
    material_delta_dimensions: tuple[str, ...] = ()
    finding: KnowledgeFinding | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "reason_code": self.reason_code,
            "material_delta_dimensions": list(self.material_delta_dimensions),
            "finding": self.finding.to_dict() if self.finding is not None else None,
        }


class MaterialDeltaFindingEvaluator:
    """Evaluate whether read, authorized Evidence justifies a Knowledge Finding.

    The evaluator decides only Finding eligibility and material-delta dimensions.
    It does not create Change Candidates, make Same-Object decisions, perform
    reviews, evaluate publication policy, or publish Knowledge.
    """

    def evaluate(self, item: FindingInput) -> FindingEvaluation:
        eligibility_failure = self._eligibility_failure(item)
        if eligibility_failure is not None:
            return eligibility_failure

        prohibited = set(item.prohibited_inferences)
        attempted = set(item.attempted_inferences)
        if prohibited & attempted:
            return FindingEvaluation(
                disposition="blocked",
                reason_code="finding_epistemic_or_scope_overreach",
            )

        dimensions = self._material_delta_dimensions(
            item.prior_state,
            item.observed_state,
        )
        if not dimensions:
            return FindingEvaluation(
                disposition="no_finding",
                reason_code="no_material_semantic_delta",
            )

        finding = self._finding(item, dimensions)
        return FindingEvaluation(
            disposition="finding",
            reason_code="material_semantic_delta",
            material_delta_dimensions=dimensions,
            finding=finding,
        )

    def _eligibility_failure(
        self,
        item: FindingInput,
    ) -> FindingEvaluation | None:
        if not item.evidence_content_read:
            return FindingEvaluation("no_finding", "evidence_content_not_read")
        if not item.content_read_authorized:
            return FindingEvaluation("no_finding", "evidence_content_not_authorized")
        if not item.evidence_resolvable or not item.observed_state.evidence_refs:
            return FindingEvaluation("no_finding", "evidence_not_resolvable")
        if not item.semantic_assertion:
            return FindingEvaluation("no_finding", "input_is_not_semantic_assertion")
        return None

    def _material_delta_dimensions(
        self,
        prior: SemanticState | None,
        observed: SemanticState,
    ) -> tuple[str, ...]:
        if prior is None:
            return ("semantic",)

        dimensions: list[str] = []
        if self._normalized_payload(prior.semantic_payload) != self._normalized_payload(
            observed.semantic_payload
        ):
            dimensions.append("semantic")
        if set(prior.evidence_refs) != set(observed.evidence_refs):
            dimensions.append("evidence")
        if prior.time_scope != observed.time_scope:
            dimensions.append("time")
        if prior.epistemic_state != observed.epistemic_state:
            dimensions.append("epistemic")
        if set(prior.conflict_refs) != set(observed.conflict_refs):
            dimensions.append("conflict")
        if set(prior.applicability) != set(observed.applicability):
            dimensions.append("applicability")
        return tuple(dimensions)

    @staticmethod
    def _normalized_payload(value: Mapping[str, Any] | None) -> Any:
        if value is None:
            return None
        return deepcopy(dict(value))

    def _finding(
        self,
        item: FindingInput,
        dimensions: tuple[str, ...],
    ) -> KnowledgeFinding:
        finding_ref = stable_token(
            "FND",
            item.task_ref,
            item.source_result_ref,
            item.source_ref,
            item.subject_refs,
            item.prior_state_ref,
            item.observed_state.to_dict(),
            item.delta_class,
            item.uncertainty_or_conflict,
        )
        return KnowledgeFinding(
            finding_ref=finding_ref,
            finding_revision="0.1",
            task_ref=item.task_ref,
            source_continuation_result_ref=item.source_result_ref,
            source_ref=item.source_ref,
            subject_refs=item.subject_refs,
            prior_state_ref=item.prior_state_ref,
            finding_type=item.finding_type,
            description=item.description,
            delta_class=item.delta_class,
            semantic_observation=(
                deepcopy(dict(item.observed_state.semantic_payload))
                if item.observed_state.semantic_payload is not None
                else None
            ),
            evidence_refs=item.observed_state.evidence_refs,
            time_scope=item.observed_state.time_scope,
            epistemic_state=item.observed_state.epistemic_state,
            uncertainty_or_conflict=item.uncertainty_or_conflict,
            material_delta=True,
            material_delta_dimensions=dimensions,
            non_canonical=True,
            event_time=item.event_time,
            producer_ref=item.producer_ref,
            tool_or_model_ref=item.tool_or_model_ref,
        )
