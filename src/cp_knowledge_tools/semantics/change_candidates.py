from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from cp_knowledge_tools.platform.hashing import canonical_json_hash

from .findings import KnowledgeFinding

CandidateDisposition = Literal[
    "candidates",
    "no_change_candidate_yet",
    "blocked",
]
TargetResolution = Literal["determinate", "ambiguous", "unknown"]

_RESOLUTION_OPERATIONS = frozenset(
    {
        "create_new_identity",
        "revise_existing_identity",
        "merge_into_existing",
        "merge_into_new_identity",
        "split_into_new_identities",
        "merge_subjects",
        "split_subject",
        "merge",
        "split",
    }
)
_PUBLICATION_OR_LIFECYCLE_OPERATIONS = frozenset(
    {
        "retract_published_version",
        "deprecate_identity",
        "retire_identity",
        "supersede_version",
        "retract_version",
    }
)
_PUBLICATION_CHANGE_SET_OPERATIONS = frozenset({"publish_new_version"})
_REVIEW_OR_POLICY_OPERATIONS = frozenset({"approve", "reject", "permit", "deny"})
_DESTRUCTIVE_SHORTCUTS = frozenset({"delete", "overwrite"})


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported semantic payload value: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _flatten_payload(
    value: Any,
    path: tuple[str, ...] = (),
) -> tuple[tuple[tuple[str, ...], Any], ...]:
    if isinstance(value, Mapping):
        flattened: list[tuple[tuple[str, ...], Any]] = []
        for key, item in value.items():
            flattened.extend(_flatten_payload(item, (*path, str(key))))
        return tuple(flattened)
    return ((path, _canonical_value(value)),)


def _lookup_path(value: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    current = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, _canonical_value(current)


def _payload_is_grounded(
    proposed: Mapping[str, Any] | None,
    grounding_payloads: Sequence[Mapping[str, Any]],
) -> bool:
    if proposed is None or not proposed or not grounding_payloads:
        return False
    for path, expected in _flatten_payload(proposed):
        if not any(
            (found := _lookup_path(payload, path))[0] and found[1] == expected
            for payload in grounding_payloads
        ):
            return False
    return True


@dataclass(frozen=True, slots=True)
class SemanticChangeOperationPolicy:
    """Caller-supplied operation vocabulary for one bounded context.

    The pipeline intentionally has no default project vocabulary. Operations
    owned by Resolution, Lifecycle, Review, Policy, or Publication remain
    foreign-layer operations even if a caller accidentally includes them.
    """

    allowed_operations: frozenset[str]
    policy_ref: str

    @classmethod
    def from_allowed(
        cls,
        allowed_operations: Iterable[str],
        *,
        policy_ref: str,
    ) -> SemanticChangeOperationPolicy:
        return cls(
            allowed_operations=frozenset(allowed_operations),
            policy_ref=policy_ref,
        )

    def failure_reason(self, operation: str) -> str | None:
        if operation in _RESOLUTION_OPERATIONS:
            return "wrong_layer_resolution_operation"
        if operation in _PUBLICATION_OR_LIFECYCLE_OPERATIONS:
            return "wrong_layer_publication_or_lifecycle_operation"
        if operation in _PUBLICATION_CHANGE_SET_OPERATIONS:
            return "wrong_layer_publication_change_set_operation"
        if operation in _REVIEW_OR_POLICY_OPERATIONS:
            return "foreign_review_or_policy_authority_operation"
        if operation in _DESTRUCTIVE_SHORTCUTS:
            return "wrong_layer_destructive_shortcut"
        if operation not in self.allowed_operations:
            return "semantic_change_operation_not_allowed"
        return None


@dataclass(frozen=True, slots=True)
class SemanticTarget:
    semantic_unit_kind: str
    target_refs: tuple[str, ...]
    target_version_refs: tuple[str, ...] = ()
    resolution: TargetResolution = "determinate"


@dataclass(frozen=True, slots=True)
class PriorKnowledgeState:
    prior_state_refs: tuple[str, ...]
    relevant_state_summary: str
    semantic_payload: Mapping[str, Any] | None = None
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticChangeProposal:
    semantic_change_operation: str
    proposed_semantic_effect: str
    proposed_semantic_payload: Mapping[str, Any] | None
    time_scope: tuple[str, ...] = ()
    epistemic_context: str | None = None
    conflict_treatment: tuple[str, ...] = ()
    relevant_constraints: tuple[str, ...] = ()
    preservation_constraints: tuple[str, ...] = ()
    prohibited_inferences: tuple[str, ...] = ()
    attempted_inferences: tuple[str, ...] = ()
    unresolved_identity_questions: tuple[str, ...] = ()
    identity_decisions: tuple[str, ...] = ()
    foreign_authority_outputs: tuple[str, ...] = ()
    overwrites_existing_assertion: bool = False
    effect_is_bounded: bool = True


@dataclass(frozen=True, slots=True)
class ChangeCandidateRequest:
    findings: tuple[KnowledgeFinding, ...]
    semantic_target: SemanticTarget | None
    prior_state: PriorKnowledgeState | None
    proposals: tuple[SemanticChangeProposal, ...]
    producer_ref: str = "cpKnowledgeTools"
    producer_version: str = "change-candidate-pipeline@0.1"


@dataclass(frozen=True, slots=True)
class ChangeCandidateRevision:
    """Immutable, non-canonical Agent-Interaction Change Candidate revision."""

    change_candidate_ref: str
    candidate_revision_ref: str
    candidate_revision: str
    semantic_unit_kind: str
    target_refs: tuple[str, ...]
    target_version_refs: tuple[str, ...]
    prior_state_refs: tuple[str, ...]
    relevant_state_summary: str
    semantic_change_operation: str
    proposed_semantic_effect: str
    _proposed_semantic_payload_json: str
    _prior_semantic_payload_json: str | None
    source_finding_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    time_scope: tuple[str, ...]
    event_time_values: tuple[str, ...]
    event_time_unknown: bool
    epistemic_context: tuple[str, ...]
    known_conflicts: tuple[str, ...]
    relevant_constraints: tuple[str, ...]
    preservation_constraints: tuple[str, ...]
    prohibited_inferences: tuple[str, ...]
    unresolved_identity_questions: tuple[str, ...]
    producer_provenance: tuple[str, ...]
    operation_policy_ref: str
    non_canonical: bool = True
    identity_scope: str = "implementation_local_non_canonical"
    requires_review: bool = True

    @property
    def proposed_semantic_payload(self) -> dict[str, Any]:
        """Return a detached projection; the stored revision cannot be mutated."""

        return json.loads(self._proposed_semantic_payload_json)

    @property
    def prior_semantic_payload(self) -> dict[str, Any] | None:
        if self._prior_semantic_payload_json is None:
            return None
        return json.loads(self._prior_semantic_payload_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_candidate_type": "knowledge_change",
            "change_candidate_ref": self.change_candidate_ref,
            "candidate_revision_ref": self.candidate_revision_ref,
            "candidate_revision": self.candidate_revision,
            "identity_scope": self.identity_scope,
            "source_finding_refs": list(self.source_finding_refs),
            "semantic_target": {
                "semantic_unit_kind": self.semantic_unit_kind,
                "target_refs": list(self.target_refs),
                "target_version_refs": list(self.target_version_refs),
            },
            "prior_state": {
                "prior_state_refs": list(self.prior_state_refs),
                "relevant_state_summary": self.relevant_state_summary,
                "semantic_payload": self.prior_semantic_payload,
            },
            "semantic_change_operation": self.semantic_change_operation,
            "primary_operation_count": 1,
            "proposed_semantic_effect": self.proposed_semantic_effect,
            "proposed_semantic_payload": self.proposed_semantic_payload,
            "source_refs": list(self.source_refs),
            "evidence_refs": list(self.evidence_refs),
            "source_and_evidence_refs": [*self.source_refs, *self.evidence_refs],
            "time_scope": list(self.time_scope),
            "time": {
                "event_time_values": list(self.event_time_values),
                "event_time_unknown": self.event_time_unknown,
            },
            "epistemic_context": list(self.epistemic_context),
            "known_conflicts": list(self.known_conflicts),
            "relevant_constraints": list(self.relevant_constraints),
            "preservation_constraints": list(self.preservation_constraints),
            "prohibited_inferences": list(self.prohibited_inferences),
            "identity_context": {
                "unresolved_identity_questions": list(
                    self.unresolved_identity_questions
                ),
            },
            "producer_provenance": list(self.producer_provenance),
            "operation_policy_ref": self.operation_policy_ref,
            "non_canonical": self.non_canonical,
            "requires_review": self.requires_review,
        }


@dataclass(frozen=True, slots=True)
class ChangeCandidateEvaluation:
    disposition: CandidateDisposition
    reason_code: str
    candidates: tuple[ChangeCandidateRevision, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "reason_code": self.reason_code,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class _CandidateDraft:
    equivalence_json: str
    finding_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    producer_provenance: tuple[str, ...]


class ChangeCandidatePipeline:
    """Create atomic, deduplicated Change Candidate revisions from Findings.

    This pipeline owns only the Agent-Interaction proposal layer. It does not
    register a KPR Lifecycle Candidate, decide Same-Object identity, create a
    Review Record, evaluate Policy, or request/perform Publication.
    """

    def __init__(self, operation_policy: SemanticChangeOperationPolicy) -> None:
        self._operation_policy = operation_policy

    def evaluate(self, request: ChangeCandidateRequest) -> ChangeCandidateEvaluation:
        return self.evaluate_many((request,))

    def evaluate_many(
        self,
        requests: Sequence[ChangeCandidateRequest],
    ) -> ChangeCandidateEvaluation:
        drafts: list[_CandidateDraft] = []
        no_candidate_reasons: list[str] = []
        split_requested = False

        for request in requests:
            common_failure = self._common_failure(request)
            if common_failure is not None:
                if common_failure.disposition == "blocked":
                    return common_failure
                no_candidate_reasons.append(common_failure.reason_code)
                continue

            split_requested = split_requested or len(request.proposals) > 1
            request_drafts: list[_CandidateDraft] = []
            for proposal in request.proposals:
                proposal_failure = self._proposal_failure(request, proposal)
                if proposal_failure is not None:
                    if proposal_failure.disposition == "blocked":
                        return proposal_failure
                    no_candidate_reasons.append(proposal_failure.reason_code)
                    request_drafts = []
                    break
                request_drafts.append(self._draft(request, proposal))
            drafts.extend(request_drafts)

        if not drafts:
            return ChangeCandidateEvaluation(
                disposition="no_change_candidate_yet",
                reason_code=(
                    no_candidate_reasons[0]
                    if no_candidate_reasons
                    else "knowledge_finding_missing"
                ),
            )

        candidates = self._materialize_grouped(drafts)
        if split_requested and len(candidates) > 1:
            reason_code = "split_into_atomic_candidates"
        elif len(drafts) > len(candidates):
            reason_code = "provenance_preserving_semantic_deduplication"
        else:
            reason_code = "change_candidate_created"
        return ChangeCandidateEvaluation(
            disposition="candidates",
            reason_code=reason_code,
            candidates=candidates,
        )

    def _common_failure(
        self,
        request: ChangeCandidateRequest,
    ) -> ChangeCandidateEvaluation | None:
        if not request.findings:
            return ChangeCandidateEvaluation(
                "no_change_candidate_yet", "knowledge_finding_missing"
            )
        if any(not finding.non_canonical for finding in request.findings):
            return ChangeCandidateEvaluation(
                "blocked", "canonical_input_not_allowed_for_change_candidate"
            )
        target = request.semantic_target
        if (
            target is None
            or target.resolution != "determinate"
            or not target.semantic_unit_kind
            or not target.target_refs
        ):
            return ChangeCandidateEvaluation(
                "no_change_candidate_yet", "target_not_determinable"
            )
        prior = request.prior_state
        if (
            prior is None
            or not prior.prior_state_refs
            or not prior.relevant_state_summary
        ):
            return ChangeCandidateEvaluation(
                "no_change_candidate_yet",
                "relevant_prior_state_not_determinable",
            )
        if not request.proposals:
            return ChangeCandidateEvaluation(
                "no_change_candidate_yet", "semantic_effect_not_determinable"
            )
        return None

    def _proposal_failure(
        self,
        request: ChangeCandidateRequest,
        proposal: SemanticChangeProposal,
    ) -> ChangeCandidateEvaluation | None:
        operation_failure = self._operation_policy.failure_reason(
            proposal.semantic_change_operation
        )
        if operation_failure is not None:
            return ChangeCandidateEvaluation("blocked", operation_failure)
        if not proposal.effect_is_bounded or not proposal.proposed_semantic_effect:
            return ChangeCandidateEvaluation(
                "no_change_candidate_yet", "semantic_effect_not_determinable"
            )
        if proposal.identity_decisions:
            return ChangeCandidateEvaluation(
                "blocked", "same_object_or_identity_resolution_preempted"
            )
        if proposal.foreign_authority_outputs:
            return ChangeCandidateEvaluation(
                "blocked", "foreign_authority_output_preempted"
            )
        if proposal.overwrites_existing_assertion:
            return ChangeCandidateEvaluation(
                "blocked", "conflict_overwrite_requires_resolution"
            )

        prohibited = set(proposal.prohibited_inferences)
        attempted = prohibited.intersection(proposal.attempted_inferences)
        if attempted.intersection({"performed", "repeated", "institutionalized"}):
            return ChangeCandidateEvaluation("blocked", "approved_state_overreach")
        if attempted.intersection({"permanently_rejected", "permanently_excluded"}):
            return ChangeCandidateEvaluation("blocked", "time_bounded_state_overreach")
        if attempted:
            return ChangeCandidateEvaluation(
                "blocked", "proposed_change_exceeds_finding_or_evidence"
            )

        grounding_payloads = [
            finding.semantic_observation
            for finding in request.findings
            if finding.semantic_observation is not None
        ]
        if not _payload_is_grounded(
            proposal.proposed_semantic_payload,
            grounding_payloads,
        ):
            return ChangeCandidateEvaluation(
                "blocked", "proposed_change_exceeds_finding_or_evidence"
            )
        return None

    def _draft(
        self,
        request: ChangeCandidateRequest,
        proposal: SemanticChangeProposal,
    ) -> _CandidateDraft:
        target = request.semantic_target
        prior = request.prior_state
        assert target is not None
        assert prior is not None
        assert proposal.proposed_semantic_payload is not None

        time_scope = _ordered_unique(
            (
                *proposal.time_scope,
                *(
                    value
                    for finding in request.findings
                    for value in finding.time_scope
                ),
            )
        )
        epistemic_context = _ordered_unique(
            (
                *((proposal.epistemic_context,) if proposal.epistemic_context else ()),
                *(
                    finding.epistemic_state
                    for finding in request.findings
                    if finding.epistemic_state
                ),
            )
        )
        known_conflicts = _ordered_unique(
            (
                *proposal.conflict_treatment,
                *(
                    value
                    for finding in request.findings
                    for value in finding.uncertainty_or_conflict
                ),
            )
        )
        event_time_values = _ordered_unique(
            finding.event_time
            for finding in request.findings
            if finding.event_time is not None
        )
        event_time_unknown = any(
            finding.event_time is None for finding in request.findings
        )
        equivalence = {
            "change_candidate_type": "knowledge_change",
            "semantic_target": {
                "semantic_unit_kind": target.semantic_unit_kind,
                "target_refs": list(_ordered_unique(target.target_refs)),
                "target_version_refs": list(
                    _ordered_unique(target.target_version_refs)
                ),
            },
            "prior_state": {
                "prior_state_refs": list(_ordered_unique(prior.prior_state_refs)),
                "relevant_state_summary": prior.relevant_state_summary,
                "semantic_payload": (
                    _canonical_value(prior.semantic_payload)
                    if prior.semantic_payload is not None
                    else None
                ),
            },
            "semantic_change_operation": proposal.semantic_change_operation,
            "proposed_semantic_effect": proposal.proposed_semantic_effect,
            "proposed_semantic_payload": _canonical_value(
                proposal.proposed_semantic_payload
            ),
            "time_scope": list(time_scope),
            "event_time_values": list(event_time_values),
            "event_time_unknown": event_time_unknown,
            "epistemic_context": list(epistemic_context),
            "known_conflicts": list(known_conflicts),
            "relevant_constraints": list(
                _ordered_unique(proposal.relevant_constraints)
            ),
            "preservation_constraints": list(
                _ordered_unique(proposal.preservation_constraints)
            ),
            "prohibited_inferences": list(
                _ordered_unique(proposal.prohibited_inferences)
            ),
            "unresolved_identity_questions": list(
                _ordered_unique(proposal.unresolved_identity_questions)
            ),
            "operation_policy_ref": self._operation_policy.policy_ref,
        }
        return _CandidateDraft(
            equivalence_json=_canonical_json(equivalence),
            finding_refs=_ordered_unique(
                finding.finding_ref for finding in request.findings
            ),
            source_refs=_ordered_unique(
                (
                    *prior.source_refs,
                    *(finding.source_ref for finding in request.findings),
                )
            ),
            evidence_refs=_ordered_unique(
                (
                    *prior.evidence_refs,
                    *(
                        evidence_ref
                        for finding in request.findings
                        for evidence_ref in finding.evidence_refs
                    ),
                )
            ),
            producer_provenance=_ordered_unique(
                (
                    request.producer_ref,
                    request.producer_version,
                    *(
                        f"{finding.producer_ref}:{finding.tool_or_model_ref}"
                        for finding in request.findings
                    ),
                )
            ),
        )

    def _materialize_grouped(
        self,
        drafts: Sequence[_CandidateDraft],
    ) -> tuple[ChangeCandidateRevision, ...]:
        grouped: dict[str, list[_CandidateDraft]] = {}
        for draft in drafts:
            grouped.setdefault(draft.equivalence_json, []).append(draft)

        candidates: list[ChangeCandidateRevision] = []
        for equivalence_json in sorted(grouped):
            group = grouped[equivalence_json]
            equivalence = json.loads(equivalence_json)
            candidate_hash = canonical_json_hash(equivalence)
            change_candidate_ref = f"CCL-{candidate_hash[:24]}"
            finding_refs = _ordered_unique(
                ref for draft in group for ref in draft.finding_refs
            )
            source_refs = _ordered_unique(
                ref for draft in group for ref in draft.source_refs
            )
            evidence_refs = _ordered_unique(
                ref for draft in group for ref in draft.evidence_refs
            )
            producer_provenance = _ordered_unique(
                ref for draft in group for ref in draft.producer_provenance
            )
            revision_hash = canonical_json_hash(
                {
                    "candidate_ref": change_candidate_ref,
                    "semantic_core": equivalence,
                    "source_finding_refs": list(finding_refs),
                    "source_refs": list(source_refs),
                    "evidence_refs": list(evidence_refs),
                    "producer_provenance": list(producer_provenance),
                }
            )
            target = equivalence["semantic_target"]
            prior = equivalence["prior_state"]
            candidates.append(
                ChangeCandidateRevision(
                    change_candidate_ref=change_candidate_ref,
                    candidate_revision_ref=f"CCR-{revision_hash[:24]}",
                    candidate_revision=f"local-{revision_hash[:12]}",
                    semantic_unit_kind=target["semantic_unit_kind"],
                    target_refs=tuple(target["target_refs"]),
                    target_version_refs=tuple(target["target_version_refs"]),
                    prior_state_refs=tuple(prior["prior_state_refs"]),
                    relevant_state_summary=prior["relevant_state_summary"],
                    semantic_change_operation=equivalence["semantic_change_operation"],
                    proposed_semantic_effect=equivalence["proposed_semantic_effect"],
                    _proposed_semantic_payload_json=_canonical_json(
                        equivalence["proposed_semantic_payload"]
                    ),
                    _prior_semantic_payload_json=(
                        _canonical_json(prior["semantic_payload"])
                        if prior["semantic_payload"] is not None
                        else None
                    ),
                    source_finding_refs=finding_refs,
                    source_refs=source_refs,
                    evidence_refs=evidence_refs,
                    time_scope=tuple(equivalence["time_scope"]),
                    event_time_values=tuple(equivalence["event_time_values"]),
                    event_time_unknown=equivalence["event_time_unknown"],
                    epistemic_context=tuple(equivalence["epistemic_context"]),
                    known_conflicts=tuple(equivalence["known_conflicts"]),
                    relevant_constraints=tuple(equivalence["relevant_constraints"]),
                    preservation_constraints=tuple(
                        equivalence["preservation_constraints"]
                    ),
                    prohibited_inferences=tuple(equivalence["prohibited_inferences"]),
                    unresolved_identity_questions=tuple(
                        equivalence["unresolved_identity_questions"]
                    ),
                    producer_provenance=producer_provenance,
                    operation_policy_ref=equivalence["operation_policy_ref"],
                )
            )
        return tuple(candidates)
