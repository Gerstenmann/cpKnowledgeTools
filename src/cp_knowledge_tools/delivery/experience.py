from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from cp_knowledge_tools.derived.experience import ExperienceProjection
from cp_knowledge_tools.platform.hashing import canonical_json_hash
from cp_knowledge_tools.policy import PolicyDecision, PolicySubject

ExperienceQuery = Literal[
    "experience",
    "phases",
    "thread",
    "gaps",
    "lesson_learned_eligibility",
    "continuation_requirements",
    "reuse_match",
]


@dataclass(frozen=True, slots=True)
class ExperienceRetrievalRequest:
    retrieval_request_ref: str
    consumer_ref: str
    purpose: str
    knowledge_object_ref: PolicySubject
    query: ExperienceQuery
    experience_ref: str | None = None
    phase_ref: str | None = None
    thread_ref: str | None = None
    gap_ref: str | None = None
    required_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperienceRetrievalResult:
    retrieval_result_ref: str
    retrieval_request_ref: str
    policy_decision_ref: str
    outcome: Literal[
        "results",
        "no_available_results",
        "request_denied",
        "request_failed",
    ]
    query: ExperienceQuery
    projection_refs: tuple[str, ...]
    items: tuple[dict[str, Any], ...]
    evidence_content_resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def semantic_signature(self) -> str:
        payload = self.to_dict()
        payload.pop("retrieval_result_ref")
        return canonical_json_hash(payload)


class ExperienceRetriever:
    """Read or match authorized Derived Experience projections."""

    def retrieve(
        self,
        projection_loader: Callable[
            [], Sequence[ExperienceProjection | Mapping[str, Any]]
        ],
        request: ExperienceRetrievalRequest,
        decision: PolicyDecision,
    ) -> ExperienceRetrievalResult:
        authorization_failure = self._authorization_failure(request, decision)
        if authorization_failure is not None:
            return self._result(request, decision, authorization_failure, (), ())

        projections = tuple(
            self._as_dict(item) for item in projection_loader()
        )
        selected = tuple(
            item
            for item in projections
            if self._is_in_requested_scope(item, request)
        )
        if request.query == "reuse_match":
            selected = tuple(
                item
                for item in selected
                if set(request.required_terms).issubset(
                    self._reuse_terms(item)
                )
            )

        items = self._query(selected, request)
        outcome = "results" if items else "no_available_results"
        projection_refs = tuple(
            item["experience_projection_ref"] for item in selected
        )
        return self._result(
            request,
            decision,
            outcome,
            projection_refs,
            items,
        )

    def _authorization_failure(
        self,
        request: ExperienceRetrievalRequest,
        decision: PolicyDecision,
    ) -> Literal["request_denied"] | None:
        authorized = (
            decision.result == "permit"
            and decision.authorizes_legacy_operation("claim_read")
            and decision.actor_or_consumer_ref == request.consumer_ref
            and decision.purpose == request.purpose
            and request.knowledge_object_ref in decision.authorized_subject_refs
        )
        return None if authorized else "request_denied"

    def _is_in_requested_scope(
        self,
        projection: Mapping[str, Any],
        request: ExperienceRetrievalRequest,
    ) -> bool:
        publication_ref = projection.get("publication_unit_ref", {})
        if (
            publication_ref.get("stable_id")
            != request.knowledge_object_ref.stable_id
            or publication_ref.get("version")
            != request.knowledge_object_ref.version
        ):
            return False
        return (
            request.experience_ref is None
            or projection.get("experience_ref") == request.experience_ref
        )

    def _query(
        self,
        projections: Sequence[dict[str, Any]],
        request: ExperienceRetrievalRequest,
    ) -> tuple[dict[str, Any], ...]:
        if request.query in {"experience", "reuse_match"}:
            return tuple(projections)
        if request.query == "phases":
            return tuple(
                item
                for projection in projections
                for item in projection["phases"]
                if request.phase_ref is None
                or item["phase_ref"] == request.phase_ref
            )
        if request.query == "thread":
            return tuple(
                item
                for projection in projections
                for item in projection["threads"]
                if request.thread_ref is None
                or item["thread_ref"] == request.thread_ref
            )
        if request.query == "gaps":
            return tuple(
                item
                for projection in projections
                for item in projection["gaps"]
                if item["status"] == "unresolved"
                and (
                    request.gap_ref is None
                    or item["gap_ref"] == request.gap_ref
                )
            )
        if request.query == "lesson_learned_eligibility":
            return tuple(
                {
                    "experience_ref": projection["experience_ref"],
                    "lesson_learned_eligibility": projection[
                        "lesson_learned_eligibility"
                    ],
                    "lesson_learned_candidates": projection[
                        "lesson_learned_candidates"
                    ],
                }
                for projection in projections
            )
        if request.query == "continuation_requirements":
            return tuple(
                item
                for projection in projections
                for item in projection["continuation_requirements"]
            )
        return ()

    def _reuse_terms(self, projection: Mapping[str, Any]) -> set[str]:
        context = projection["reuse_context"]
        return {
            term
            for dimension in (
                "domain_terms",
                "topic_terms",
                "purpose_terms",
            )
            for term in context[dimension]
        }

    def _as_dict(
        self,
        projection: ExperienceProjection | Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(projection, ExperienceProjection):
            return projection.to_dict()
        return dict(projection)

    def _result(
        self,
        request: ExperienceRetrievalRequest,
        decision: PolicyDecision,
        outcome: Literal[
            "results",
            "no_available_results",
            "request_denied",
            "request_failed",
        ],
        projection_refs: tuple[str, ...],
        items: tuple[dict[str, Any], ...],
    ) -> ExperienceRetrievalResult:
        payload = {
            "request": request.retrieval_request_ref,
            "policy_decision": decision.policy_decision_ref,
            "outcome": outcome,
            "projection_refs": projection_refs,
            "items": items,
        }
        return ExperienceRetrievalResult(
            retrieval_result_ref=(
                f"ERES-{canonical_json_hash(payload)[:24].upper()}"
            ),
            retrieval_request_ref=request.retrieval_request_ref,
            policy_decision_ref=decision.policy_decision_ref,
            outcome=outcome,
            query=request.query,
            projection_refs=projection_refs,
            items=items,
        )
