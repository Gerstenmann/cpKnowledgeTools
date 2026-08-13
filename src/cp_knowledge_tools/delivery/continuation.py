from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from cp_knowledge_tools.platform.hashing import canonical_json_hash

ContinuationOperation = Literal["discover", "read_metadata", "read_content"]
StopReason = Literal[
    "all_requested_gaps_resolved",
    "budget_exhausted",
    "discover_not_authorized",
    "metadata_not_authorized",
    "content_not_authorized",
    "no_relevant_candidates",
    "candidate_scope_exhausted",
    "policy_context_unresolved",
]


@dataclass(frozen=True, slots=True)
class CandidateScope:
    scope_ref: str
    allowed_source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContinuationBudget:
    max_candidate_sources: int
    max_search_rounds: int
    max_metadata_reads: int
    max_content_reads: int
    max_branches: int
    max_depth: int

    def __post_init__(self) -> None:
        for field_name in (
            "max_candidate_sources",
            "max_search_rounds",
            "max_metadata_reads",
            "max_content_reads",
            "max_branches",
            "max_depth",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True, slots=True)
class PolicyContext:
    policy_config_ref: str
    processing_zone: str
    profile_refs: tuple[str, ...]
    policy_anchor_ids: tuple[str, ...]


def derive_lesson_learned_required_gap_refs(
    experience_projection: Mapping[str, Any],
    gap_refs: tuple[str, ...],
) -> tuple[str, ...]:
    """Map requested gaps to phases required by the experience projection."""
    required_phases = {
        str(phase.get("phase_ref"))
        for phase in experience_projection.get("phases", ())
        if isinstance(phase, Mapping)
        and phase.get("required_for_lesson_learned") is True
        and phase.get("phase_ref")
    }
    phase_by_gap = {
        str(gap.get("gap_ref")): str(gap.get("phase_ref"))
        for gap in experience_projection.get("gaps", ())
        if isinstance(gap, Mapping) and gap.get("gap_ref") and gap.get("phase_ref")
    }
    return tuple(
        gap_ref
        for gap_ref in gap_refs
        if phase_by_gap.get(gap_ref) in required_phases
    )


@dataclass(frozen=True, slots=True)
class ContinuationRequest:
    continuation_request_ref: str
    consumer_ref: str
    purpose: str
    experience_ref: str
    continuation_requirement_ref: str
    gap_refs: tuple[str, ...]
    lesson_learned_required_gap_refs: tuple[str, ...]
    search_after: str
    candidate_scope: CandidateScope
    budget: ContinuationBudget
    policy_context: PolicyContext
    requested_at: str

    def __post_init__(self) -> None:
        requested = set(self.gap_refs)
        if not set(self.lesson_learned_required_gap_refs).issubset(requested):
            raise ValueError(
                "lesson_learned_required_gap_refs must be a subset of gap_refs"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    permitted: bool
    policy_decision_ref: str
    reason: str


@dataclass(frozen=True, slots=True)
class CandidateMetadata:
    candidate_ref: str
    source_time: str
    topic_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    evidence_ref: str
    source_ref: str
    resolved_gap_refs: tuple[str, ...]
    informed_gap_refs: tuple[str, ...]
    facts: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    candidate_sources: int
    search_rounds: int
    metadata_reads: int
    content_reads: int
    branches: int
    depth: int


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    continuation_result_ref: str
    continuation_request_ref: str
    outcome: str
    resolved_gaps: tuple[str, ...]
    unresolved_gaps: tuple[str, ...]
    evidence: tuple[CandidateEvidence, ...]
    evidence_refs: tuple[str, ...]
    sources_discovered: tuple[str, ...]
    metadata_reads: tuple[str, ...]
    content_reads: tuple[str, ...]
    branches: tuple[str, ...]
    budget_usage: BudgetUsage
    stop_reason: StopReason
    lesson_learned_eligibility: str
    policy_decision_refs: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def semantic_signature(self) -> str:
        payload = self.to_dict()
        payload.pop("continuation_result_ref")
        return canonical_json_hash(payload)


Discover = Callable[[ContinuationRequest, int, int], tuple[str, ...]]
ReadMetadata = Callable[[str], CandidateMetadata]
Rank = Callable[[CandidateMetadata, tuple[str, ...]], float]
ReadContent = Callable[[str], str]
Interpret = Callable[
    [CandidateMetadata, str, tuple[str, ...]], CandidateEvidence
]
Authorize = Callable[
    [ContinuationOperation, ContinuationRequest, str | None],
    AuthorizationDecision,
]


@dataclass(frozen=True, slots=True)
class ContinuationServices:
    discover: Discover
    read_metadata: ReadMetadata
    rank: Rank
    read_content: ReadContent
    interpret: Interpret


class ContinuationExecutor:
    """Run a policy-gated continuation request without mutating input state."""

    def execute(
        self,
        request: ContinuationRequest,
        services: ContinuationServices,
        authorize: Authorize,
    ) -> ContinuationResult:
        policy_refs: list[str] = []
        discovered: tuple[str, ...] = ()
        metadata_reads: list[str] = []
        content_reads: list[str] = []
        evidence: list[CandidateEvidence] = []
        resolved: set[str] = set()
        search_rounds = 0
        depth = 0

        if not self._policy_context_resolved(request.policy_context):
            return self._result(
                request,
                "denied",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                "policy_context_unresolved",
            )
        if (
            request.budget.max_search_rounds == 0
            or request.budget.max_candidate_sources == 0
            or request.budget.max_depth == 0
        ):
            return self._result(
                request,
                "partial",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                "budget_exhausted",
            )

        discover_decision = authorize("discover", request, None)
        policy_refs.append(discover_decision.policy_decision_ref)
        if not discover_decision.permitted:
            return self._result(
                request,
                "denied",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                "discover_not_authorized",
            )

        allowed = set(request.candidate_scope.allowed_source_refs)
        raw_discovered = services.discover(
            request,
            0,
            request.budget.max_candidate_sources,
        )
        search_rounds = 1
        discovered = tuple(
            candidate_ref
            for candidate_ref in dict.fromkeys(raw_discovered)
            if candidate_ref in allowed
        )[: request.budget.max_candidate_sources]
        depth = 1

        ranked: list[tuple[float, CandidateMetadata]] = []
        metadata_denied = False
        for candidate_ref in discovered:
            if len(metadata_reads) >= request.budget.max_metadata_reads:
                break
            decision = authorize("read_metadata", request, candidate_ref)
            policy_refs.append(decision.policy_decision_ref)
            if not decision.permitted:
                metadata_denied = True
                continue
            metadata = services.read_metadata(candidate_ref)
            metadata_reads.append(candidate_ref)
            if metadata.candidate_ref != candidate_ref:
                continue
            if not self._is_after(metadata.source_time, request.search_after):
                continue
            score = services.rank(metadata, request.gap_refs)
            if score > 0:
                ranked.append((score, metadata))

        if not metadata_reads and metadata_denied:
            return self._result(
                request,
                "denied",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                "metadata_not_authorized",
            )
        if not ranked:
            stop_reason: StopReason = (
                "budget_exhausted"
                if len(metadata_reads) < len(discovered)
                and len(metadata_reads) >= request.budget.max_metadata_reads
                else "no_relevant_candidates"
            )
            return self._result(
                request,
                "no_results",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                stop_reason,
            )

        content_denied = False
        content_budget_exhausted = False
        for _, metadata in sorted(
            ranked, key=lambda item: (-item[0], item[1].candidate_ref)
        ):
            if set(request.gap_refs).issubset(resolved):
                break
            if len(content_reads) >= request.budget.max_content_reads:
                content_budget_exhausted = True
                break
            decision = authorize("read_content", request, metadata.candidate_ref)
            policy_refs.append(decision.policy_decision_ref)
            if not decision.permitted:
                content_denied = True
                continue
            content = services.read_content(metadata.candidate_ref)
            content_reads.append(metadata.candidate_ref)
            interpreted = services.interpret(metadata, content, request.gap_refs)
            if interpreted.source_ref != metadata.candidate_ref:
                continue
            permitted_gaps = tuple(
                dict.fromkeys(
                    gap_ref
                    for gap_ref in interpreted.resolved_gap_refs
                    if gap_ref in request.gap_refs
                )
            )
            permitted_informed_gaps = tuple(
                dict.fromkeys(
                    gap_ref
                    for gap_ref in interpreted.informed_gap_refs
                    if gap_ref in request.gap_refs
                )
            )
            if not permitted_gaps and not permitted_informed_gaps:
                continue
            normalized = CandidateEvidence(
                evidence_ref=interpreted.evidence_ref,
                source_ref=interpreted.source_ref,
                resolved_gap_refs=permitted_gaps,
                informed_gap_refs=permitted_informed_gaps,
                facts=interpreted.facts,
            )
            evidence.append(normalized)
            resolved.update(permitted_gaps)

        requested = set(request.gap_refs)
        if requested.issubset(resolved):
            return self._result(
                request,
                "complete",
                resolved,
                evidence,
                discovered,
                metadata_reads,
                content_reads,
                policy_refs,
                search_rounds,
                depth,
                "all_requested_gaps_resolved",
            )
        if content_budget_exhausted:
            stop_reason = "budget_exhausted"
        elif content_denied and not content_reads:
            stop_reason = "content_not_authorized"
        else:
            stop_reason = "candidate_scope_exhausted"
        return self._result(
            request,
            "partial",
            resolved,
            evidence,
            discovered,
            metadata_reads,
            content_reads,
            policy_refs,
            search_rounds,
            depth,
            stop_reason,
        )

    @staticmethod
    def _policy_context_resolved(context: PolicyContext) -> bool:
        return bool(context.policy_config_ref and context.processing_zone)

    @staticmethod
    def _is_after(candidate_time: str, search_after: str) -> bool:
        try:
            return datetime.fromisoformat(candidate_time) > datetime.fromisoformat(
                search_after
            )
        except ValueError:
            return False

    def _result(
        self,
        request: ContinuationRequest,
        outcome: str,
        resolved: set[str],
        evidence: list[CandidateEvidence],
        discovered: tuple[str, ...],
        metadata_reads: list[str],
        content_reads: list[str],
        policy_refs: list[str],
        search_rounds: int,
        depth: int,
        stop_reason: StopReason,
    ) -> ContinuationResult:
        resolved_ordered = tuple(
            gap_ref for gap_ref in request.gap_refs if gap_ref in resolved
        )
        unresolved = tuple(
            gap_ref for gap_ref in request.gap_refs if gap_ref not in resolved
        )
        evidence_tuple = tuple(evidence)
        policy_tuple = tuple(dict.fromkeys(policy_refs))
        lesson_required = set(request.lesson_learned_required_gap_refs)
        usage = BudgetUsage(
            candidate_sources=len(discovered),
            search_rounds=search_rounds,
            metadata_reads=len(metadata_reads),
            content_reads=len(content_reads),
            branches=0,
            depth=depth,
        )
        payload = {
            "continuation_request_ref": request.continuation_request_ref,
            "outcome": outcome,
            "resolved_gaps": resolved_ordered,
            "unresolved_gaps": unresolved,
            "evidence": tuple(asdict(item) for item in evidence_tuple),
            "budget_usage": asdict(usage),
            "stop_reason": stop_reason,
            "policy_decision_refs": policy_tuple,
        }
        return ContinuationResult(
            continuation_result_ref=(
                f"CRES-{canonical_json_hash(payload)[:24].upper()}"
            ),
            continuation_request_ref=request.continuation_request_ref,
            outcome=outcome,
            resolved_gaps=resolved_ordered,
            unresolved_gaps=unresolved,
            evidence=evidence_tuple,
            evidence_refs=tuple(item.evidence_ref for item in evidence_tuple),
            sources_discovered=discovered,
            metadata_reads=tuple(metadata_reads),
            content_reads=tuple(content_reads),
            branches=(),
            budget_usage=usage,
            stop_reason=stop_reason,
            lesson_learned_eligibility=(
                "eligible"
                if lesson_required and lesson_required.issubset(resolved)
                else "insufficient_evidence"
            ),
            policy_decision_refs=policy_tuple,
            diagnostics=(stop_reason,),
        )
