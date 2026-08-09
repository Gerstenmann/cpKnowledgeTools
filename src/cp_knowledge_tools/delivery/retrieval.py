from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from cp_knowledge_tools.platform.hashing import canonical_json_hash
from cp_knowledge_tools.policy import PolicyDecision, PolicySubject

StateSelection = Literal["current", "all"]


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    retrieval_request_ref: str
    consumer_ref: str
    purpose: str
    knowledge_object_ref: PolicySubject
    semantic_subject_refs: tuple[str, ...]
    claim_predicate_refs: tuple[str, ...] = ()
    event_type_refs: tuple[str, ...] = ()
    state_selection: StateSelection = "current"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    retrieval_result_ref: str
    retrieval_request_ref: str
    consumer_ref: str
    purpose: str
    policy_decision_ref: str
    outcome: str
    publication_unit_ref: dict[str, str]
    projection_ref: str
    projection_semantic_hash: str
    claim_items: tuple[dict[str, Any], ...]
    event_items: tuple[dict[str, Any], ...]
    conflict_items: tuple[dict[str, Any], ...]
    evidence_content_resolved: bool
    evidence_resolution_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def semantic_signature(self) -> str:
        payload = self.to_dict()
        payload.pop("retrieval_result_ref")
        return canonical_json_hash(payload)


@dataclass(frozen=True, slots=True)
class EvidenceResolutionRequest:
    evidence_resolution_request_ref: str
    consumer_ref: str
    purpose: str
    evidence_ref: PolicySubject


@dataclass(frozen=True, slots=True)
class EvidenceResolutionResult:
    evidence_resolution_request_ref: str
    policy_decision_ref: str
    status: str
    evidence_ref: PolicySubject
    content: str | None
    content_resolved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeRetriever:
    """Query semantic states from a rebuildable Derived Retrieval Projection."""

    def retrieve(
        self,
        projection: Mapping[str, Any],
        request: RetrievalRequest,
        decision: PolicyDecision,
    ) -> RetrievalResult:
        denial = self._authorization_failure(request, decision)
        if denial is not None:
            return self._empty_result(projection, request, decision, denial)

        publication_ref = dict(projection["knowledge_object_ref"])
        if (
            publication_ref["stable_id"] != request.knowledge_object_ref.stable_id
            or publication_ref["version"] != request.knowledge_object_ref.version
        ):
            return self._empty_result(
                projection,
                request,
                decision,
                "request_failed",
            )

        claims = self._select_claims(projection, request)
        events = self._select_events(projection, request)
        selected_claim_refs = {
            item["claim_ref"]["stable_id"] for item in claims
        }
        conflicts = tuple(
            item
            for item in projection["conflict_index"]
            if selected_claim_refs.intersection(
                ref["stable_id"] for ref in item["claim_refs"]
            )
        )
        evidence_by_subject: dict[str, list[dict[str, Any]]] = {}
        for link in projection["evidence_index"]:
            subject_id = link["subject_ref"]["stable_id"]
            evidence_by_subject.setdefault(subject_id, []).append(link)

        claim_items = tuple(
            self._claim_result_item(
                item,
                conflicts,
                evidence_by_subject,
                request.state_selection,
            )
            for item in claims
        )
        event_items = tuple(self._event_result_item(item) for item in events)
        outcome = "results" if claim_items or event_items else "no_available_results"
        payload = {
            "request_ref": request.retrieval_request_ref,
            "policy_decision_ref": decision.policy_decision_ref,
            "projection_ref": projection["projection_ref"],
            "claim_items": claim_items,
            "event_items": event_items,
            "conflict_items": conflicts,
        }
        return RetrievalResult(
            retrieval_result_ref=f"RRES-{canonical_json_hash(payload)[:24].upper()}",
            retrieval_request_ref=request.retrieval_request_ref,
            consumer_ref=request.consumer_ref,
            purpose=request.purpose,
            policy_decision_ref=decision.policy_decision_ref,
            outcome=outcome,
            publication_unit_ref=publication_ref,
            projection_ref=projection["projection_ref"],
            projection_semantic_hash=projection["semantic_hash"],
            claim_items=claim_items,
            event_items=event_items,
            conflict_items=conflicts,
            evidence_content_resolved=False,
            evidence_resolution_status="citation_only",
        )

    def _authorization_failure(
        self,
        request: RetrievalRequest,
        decision: PolicyDecision,
    ) -> str | None:
        if decision.result != "permit":
            return "request_denied"
        if "claim_read" not in decision.authorized_actions:
            return "request_denied"
        if decision.actor_or_consumer_ref != request.consumer_ref:
            return "request_denied"
        if decision.purpose != request.purpose:
            return "request_denied"
        if request.knowledge_object_ref not in decision.authorized_subject_refs:
            return "request_denied"
        return None

    def _select_claims(
        self,
        projection: Mapping[str, Any],
        request: RetrievalRequest,
    ) -> tuple[dict[str, Any], ...]:
        subject_refs = set(request.semantic_subject_refs)
        predicates = set(request.claim_predicate_refs)
        matches = [
            item
            for item in projection["claim_index"]
            if item["statement"]["subject_ref"]["stable_id"] in subject_refs
            and item["statement"]["predicate_ref"] in predicates
        ]
        if request.state_selection == "all":
            return tuple(matches)

        preferred_ids = {
            conflict["preferred_claim_ref"]["stable_id"]
            for conflict in projection["conflict_index"]
        }
        selected: list[dict[str, Any]] = []
        for predicate in request.claim_predicate_refs:
            group = [
                item
                for item in matches
                if item["statement"]["predicate_ref"] == predicate
            ]
            preferred = [
                item
                for item in group
                if item["claim_ref"]["stable_id"] in preferred_ids
            ]
            selected.extend(preferred or group)
        return tuple(selected)

    def _select_events(
        self,
        projection: Mapping[str, Any],
        request: RetrievalRequest,
    ) -> tuple[dict[str, Any], ...]:
        event_types = set(request.event_type_refs)
        return tuple(
            item
            for item in projection["event_index"]
            if item["event_type_ref"] in event_types
        )

    def _claim_result_item(
        self,
        claim: dict[str, Any],
        conflicts: tuple[dict[str, Any], ...],
        evidence_by_subject: dict[str, list[dict[str, Any]]],
        state_selection: StateSelection,
    ) -> dict[str, Any]:
        claim_id = claim["claim_ref"]["stable_id"]
        relevant_conflicts = tuple(
            conflict
            for conflict in conflicts
            if claim_id in {ref["stable_id"] for ref in conflict["claim_refs"]}
        )
        is_historical = state_selection == "all" and any(
            "temporal" in conflict["conflict_dimensions"]
            and conflict["preferred_claim_ref"]["stable_id"] != claim_id
            for conflict in relevant_conflicts
        )
        evidence_links = tuple(evidence_by_subject.get(claim_id, ()))
        return {
            "subject_ref": claim["claim_ref"],
            "semantic_subject_ref": claim["statement"]["subject_ref"],
            "statement": claim["statement"],
            "epistemic_status": claim["epistemic_status"],
            "state_role": "historical" if is_historical else "current",
            "conflict_refs": tuple(
                conflict["conflict_set_id"] for conflict in relevant_conflicts
            ),
            "preferred_in_conflict": bool(relevant_conflicts) and not is_historical,
            "evidence_refs": tuple(
                link["evidence_address_ref"] for link in evidence_links
            ),
            "evidence_links": evidence_links,
            "evidence_content_resolved": False,
        }

    def _event_result_item(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "subject_ref": event["event_ref"],
            "event_type_ref": event["event_type_ref"],
            "label": event["label"],
            "time": event["time"],
            "evidence_link_ids": tuple(event["evidence_link_ids"]),
            "evidence_content_resolved": False,
        }

    def _empty_result(
        self,
        projection: Mapping[str, Any],
        request: RetrievalRequest,
        decision: PolicyDecision,
        outcome: str,
    ) -> RetrievalResult:
        publication_ref = {
            "subject_type": request.knowledge_object_ref.subject_type,
            "stable_id": request.knowledge_object_ref.stable_id,
            "version": request.knowledge_object_ref.version,
            "authority_context": request.knowledge_object_ref.authority_context,
        }
        if outcome == "request_denied":
            projection_ref = "not_accessed"
            projection_hash = "not_accessed"
        else:
            projection_ref = str(projection.get("projection_ref", "not_accessed"))
            projection_hash = str(projection.get("semantic_hash", "not_accessed"))
        result_hash = canonical_json_hash(
            {"request": request.retrieval_request_ref, "outcome": outcome}
        )
        return RetrievalResult(
            retrieval_result_ref=f"RRES-{result_hash[:24].upper()}",
            retrieval_request_ref=request.retrieval_request_ref,
            consumer_ref=request.consumer_ref,
            purpose=request.purpose,
            policy_decision_ref=decision.policy_decision_ref,
            outcome=outcome,
            publication_unit_ref=publication_ref,
            projection_ref=projection_ref,
            projection_semantic_hash=projection_hash,
            claim_items=(),
            event_items=(),
            conflict_items=(),
            evidence_content_resolved=False,
            evidence_resolution_status="not_authorized",
        )


class EvidenceResolver:
    """Resolve Evidence content only after an independent permit decision."""

    def resolve(
        self,
        request: EvidenceResolutionRequest,
        decision: PolicyDecision,
        content_loader: Callable[[], str],
    ) -> EvidenceResolutionResult:
        authorized = (
            decision.result == "permit"
            and "evidence_resolution" in decision.authorized_actions
            and decision.actor_or_consumer_ref == request.consumer_ref
            and decision.purpose == request.purpose
            and request.evidence_ref in decision.authorized_subject_refs
        )
        if not authorized:
            return EvidenceResolutionResult(
                evidence_resolution_request_ref=request.evidence_resolution_request_ref,
                policy_decision_ref=decision.policy_decision_ref,
                status="not_authorized",
                evidence_ref=request.evidence_ref,
                content=None,
                content_resolved=False,
            )
        return EvidenceResolutionResult(
            evidence_resolution_request_ref=request.evidence_resolution_request_ref,
            policy_decision_ref=decision.policy_decision_ref,
            status="resolved",
            evidence_ref=request.evidence_ref,
            content=content_loader(),
            content_resolved=True,
        )


class RetrievalRenderer:
    """Render structured results without defining domain or retrieval semantics."""

    def render(
        self,
        result: RetrievalResult,
        *,
        reference_labels: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        labels = reference_labels or {}
        lines = [self._render_claim(item, labels) for item in result.claim_items]
        lines.extend(self._render_event(item) for item in result.event_items)
        current_values = [
            self._object_value(item["statement"]["object"], labels)
            for item in result.claim_items
            if item["state_role"] == "current"
        ]
        epistemic = {item["epistemic_status"] for item in result.claim_items}
        event_modalities = {
            value["modality"]
            for item in result.event_items
            for value in item["time"]
        }
        return {
            "rendered_answer": " ".join(lines),
            "current_state_text": "; ".join(current_values),
            "epistemic_status": epistemic.pop() if len(epistemic) == 1 else "mixed",
            "claims_actual_occurrence": "actual" in event_modalities,
            "evidence_resolution": result.evidence_resolution_status,
        }

    def _render_claim(
        self,
        item: dict[str, Any],
        labels: Mapping[str, str],
    ) -> str:
        statement = item["statement"]
        predicate = statement["predicate_ref"].rsplit(".", 1)[-1].replace("_", " ")
        value = self._object_value(statement["object"], labels)
        role = item["state_role"]
        epistemic = item["epistemic_status"]
        return f"{role.capitalize()} {epistemic} {predicate}: {value}."

    def _render_event(self, item: dict[str, Any]) -> str:
        rendered_times = []
        for time_value in item["time"]:
            value = time_value["start"] or "unknown"
            rendered_times.append(
                f"{time_value['modality']} {self._humanize_literal(value)}"
            )
        return f"Event {item['label']}: {', '.join(rendered_times)}."

    def _object_value(
        self,
        value: dict[str, Any],
        labels: Mapping[str, str],
    ) -> str:
        if value["kind"] == "reference":
            stable_id = value["reference"]["stable_id"]
            return labels.get(stable_id, stable_id)
        return self._humanize_literal(value["value"])

    def _humanize_literal(self, value: Any) -> str:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).strftime("%-d %B %Y")
            except ValueError:
                return value.replace("_", " ")
        return str(value)
