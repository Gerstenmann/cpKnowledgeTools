"""Closed, bounded untrusted transport projection of existing Candidate roles.

This module owns technical wire syntax, not an ontology or Policy. Parsing and
all cross-reference checks finish before shared Candidate dataclasses are built.
No state is published or registered by this decoder.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import MISSING, asdict, dataclass, fields
from typing import Any, get_args, get_type_hints

from cp_knowledge_tools.platform.hashing import canonical_json_hash

from .candidates import (
    Applicability,
    EpistemicContext,
    EvidenceProvenance,
    KnownGap,
    ProducerProvenance,
    ProposedClaim,
    ProposedEntity,
    ProposedEvent,
    ProposedEvidenceLink,
    ProposedParticipation,
    ProposedRelationship,
    ProposedTime,
    SemanticCandidatePayload,
)
from .hardening import EvidenceAssessment, EvidenceDimensions
from .invocation import InvocationBounds, PreparedInvocation

# Technical projection of the governed fields in CPKS-SPEC-KM-VOC@0.1.
# Entity classes, event types and scalar predicates remain bounded identifiers.
EVIDENCE_ROLES = frozenset(
    {"supports", "contradicts", "qualifies", "reports_statement", "derivation_input"}
)
EPISTEMIC = frozenset(
    {
        "unassessed",
        "reported",
        "observed",
        "inferred",
        "hypothesized",
        "confirmed",
        "disputed",
    }
)
PRECISIONS = frozenset(
    {
        "unknown",
        "year",
        "quarter",
        "season",
        "month",
        "week",
        "day",
        "hour",
        "minute",
        "second",
    }
)
MODALITIES = frozenset({"actual", "planned", "expected", "hypothetical"})
TIME_ROLES = frozenset(
    {
        "event_time",
        "valid_time",
        "assertion_time",
        "source_time",
        "observed_at",
        "recorded_at",
        "reviewed_at",
        "published_at",
        "retired_at",
    }
)
PARTICIPATION_ROLES = frozenset(
    {
        "initiator",
        "actor",
        "subject",
        "participant",
        "organizer",
        "recipient",
        "beneficiary",
        "affected_party",
        "observer",
        "location",
        "instrument",
    }
)
ASSERTED_PREDICATES = frozenset(
    {
        "is_a",
        "part_of",
        "depends_on",
        "causes",
        "enables",
        "precedes",
        "follows",
        "equivalent_to",
        "contradicts",
        "qualifies",
        "supersedes",
        "invalidates",
        "is_alternative_to",
    }
)
PROPOSALS: dict[str, type] = {
    "entity": ProposedEntity,
    "claim": ProposedClaim,
    "event": ProposedEvent,
    "participation": ProposedParticipation,
    "relationship": ProposedRelationship,
}
LOCAL_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")


def _object(
    value: Any, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or not required <= value.keys()
        or value.keys() - required - (optional or set())
    ):
        raise ValueError("unknown or missing transport fields")
    return value


def _list(value: Any) -> list[Any]:
    if type(value) is not list:
        raise ValueError("transport array required")
    return value


def _text(value: Any, *, key: bool = False) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or (key and not LOCAL_KEY.fullmatch(value))
    ):
        raise ValueError("invalid transport text/reference")
    return value


def _enum(value: Any, values: frozenset[str]) -> str:
    if type(value) is not str or value not in values:
        raise ValueError("unsupported controlled vocabulary value")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("nonstandard JSON constant")


def _parse(raw: bytes, bounds: InvocationBounds) -> dict[str, Any]:
    if type(raw) is not bytes or len(raw) > bounds.max_response_bytes:
        raise ValueError("response exceeds byte bound or is not bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        depth = 0
        quoted = escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > bounds.max_nesting_depth:
                    raise ValueError("response exceeds nesting bound")
            elif char in "]}":
                depth -= 1
        parsed = json.loads(text, object_pairs_hook=_unique, parse_constant=_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UTF8 JSON response") from exc
    count = 0

    def bounded(value: Any) -> None:
        nonlocal count
        count += 1
        if count > bounds.max_nodes:
            raise ValueError("response exceeds node bound")
        if type(value) is str:
            if len(value) > bounds.max_string_chars:
                raise ValueError("response exceeds string bound")
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise ValueError("invalid Unicode scalar") from exc
        elif type(value) is float and not math.isfinite(value):
            raise ValueError("nonfinite JSON number")
        elif type(value) in (dict, list):
            if len(value) > bounds.max_list_items:
                raise ValueError("response exceeds collection bound")
            for child in value.items() if type(value) is dict else value:
                if type(value) is dict:
                    bounded(child[0])
                    bounded(child[1])
                else:
                    bounded(child)

    bounded(parsed)
    return _object(
        parsed,
        {
            "transport_version",
            "invocation_ref",
            "candidates",
            "gaps",
            "identity_proposals",
            "evidence_assessments",
        },
    )


def _proposal(kind: str, value: Any) -> dict[str, Any]:
    cls = PROPOSALS[kind]
    required = {f.name for f in fields(cls) if f.default is MISSING}
    allowed = {f.name for f in fields(cls)}
    result = dict(_object(value, required, allowed - required))
    hints = get_type_hints(cls)
    for field in fields(cls):
        if field.name not in result:
            result[field.name] = field.default
        child = result[field.name]
        expected = hints[field.name]
        types = get_args(expected) or (expected,)
        if type(child) not in types:
            raise ValueError("wrong proposal field type")
        if type(child) is str:
            _text(child, key=field.name.endswith(("_key", "_ref")))
    return result


def _time(value: Any, kind: str) -> dict[str, Any]:
    result = _object(value, {"role", "value", "precision", "modality"})
    _enum(result["role"], TIME_ROLES)
    _enum(result["precision"], PRECISIONS)
    _enum(result["modality"], MODALITIES)
    if result["value"] is not None:
        _text(result["value"])
    if result["value"] is None and result["precision"] != "unknown":
        raise ValueError("unknown time/precision mismatch")
    if result["role"] == "event_time" and kind not in {"event", "participation"}:
        raise ValueError("event time requires occurrence context")
    return result


def _gap(value: Any, handles: dict[str, Any]) -> dict[str, Any]:
    gap = _object(value, {"gap_code", "detail", "evidence_handles"})
    _text(gap["gap_code"], key=True)
    _text(gap["detail"])
    refs = _list(gap["evidence_handles"])
    if (
        not refs
        or any(type(ref) is not str or ref not in handles for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        raise ValueError("gap evidence unresolved")
    return gap


@dataclass(frozen=True, slots=True)
class DecodedCandidates:
    candidate_payloads: tuple[SemanticCandidatePayload, ...]
    known_gaps: tuple[KnownGap, ...]
    evidence_assessments: tuple[EvidenceAssessment, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CandidateDecoder:
    def decode(
        self, raw: bytes, invocation: PreparedInvocation, *, produced_at: str
    ) -> DecodedCandidates:
        root = _parse(raw, invocation.bounds)
        if (
            root["transport_version"] != "1"
            or root["invocation_ref"] != invocation.invocation_ref
        ):
            raise ValueError("response invocation/version mismatch")
        handles = {e.handle: e for e in invocation.evidence}
        rows = _list(root["candidates"])
        if len(rows) > invocation.bounds.max_candidates:
            raise ValueError("too many candidates")
        keys: dict[str, str] = {}
        link_claims: dict[str, str] = {}
        validated: list[dict[str, Any]] = []
        for value in rows:
            row = _object(
                value,
                {"kind", "proposal", "evidence"},
                {
                    "time",
                    "epistemic_context",
                    "applicability",
                    "known_conflicts",
                    "gaps",
                },
            )
            kind = _text(row["kind"])
            if kind not in PROPOSALS:
                raise ValueError("unsupported candidate kind")
            proposal = _proposal(kind, row["proposal"])
            key = _text(proposal[f"{kind}_key"], key=True)
            if key in keys:
                raise ValueError("duplicate candidate local key")
            keys[key] = kind
            links = _list(row["evidence"])
            if not links:
                raise ValueError("candidate requires evidence")
            for link in links:
                _object(link, {"key", "handle", "role"})
                _text(link["key"], key=True)
                if link["key"] in link_claims:
                    raise ValueError("duplicate evidence link key")
                link_claims[link["key"]] = key
                if type(link["handle"]) is not str or link["handle"] not in handles:
                    raise ValueError("unknown invocation evidence handle")
                _enum(link["role"], EVIDENCE_ROLES)
            times = [_time(t, kind) for t in _list(row.get("time", []))]
            if len({t["role"] for t in times}) != len(times):
                raise ValueError("duplicate candidate time role")
            epistemic = row.get("epistemic_context")
            if epistemic is not None:
                _object(epistemic, {"status", "classification_basis"})
                _enum(epistemic["status"], EPISTEMIC)
                _text(epistemic["classification_basis"])
                if epistemic["status"] == "confirmed" and not any(
                    link["role"] == "supports" for link in links
                ):
                    raise ValueError("reported evidence cannot confer confirmation")
            applicability = _object(
                row.get("applicability", {"context_refs": [], "conditions": []}),
                {"context_refs", "conditions"},
            )
            for ref in _list(applicability["context_refs"]):
                _text(ref, key=True)
            for condition in _list(applicability["conditions"]):
                _text(condition)
            conflicts = _list(row.get("known_conflicts", []))
            for conflict in conflicts:
                _text(conflict)
            gaps = [_gap(g, handles) for g in _list(row.get("gaps", []))]
            validated.append(
                {
                    "kind": kind,
                    "key": key,
                    "proposal": proposal,
                    "links": links,
                    "time": times,
                    "epistemic": epistemic,
                    "applicability": applicability,
                    "conflicts": conflicts,
                    "gaps": gaps,
                }
            )

        def reference(key: str | None, allowed: set[str]) -> None:
            if key is None or keys.get(key) not in allowed:
                raise ValueError("unresolved/wrong-kind candidate reference")

        for row in validated:
            kind, proposal = row["kind"], row["proposal"]
            if kind == "claim":
                if not proposal["statement"] and not proposal["predicate_ref"]:
                    raise ValueError("claim statement or predicate required")
                if proposal["subject_entity_key"] is not None:
                    reference(proposal["subject_entity_key"], {"entity"})
                elif proposal["predicate_ref"]:
                    raise ValueError("structured claim requires subject")
                if proposal["object_entity_label"] is not None:
                    if (
                        proposal["value"] is not None
                        or sum(
                            r["kind"] == "entity"
                            and r["proposal"]["label"]
                            == proposal["object_entity_label"]
                            for r in validated
                        )
                        != 1
                    ):
                        raise ValueError("ambiguous claim object")
                if proposal["time_modality"] is not None:
                    _enum(proposal["time_modality"], MODALITIES)
            elif kind == "participation":
                reference(proposal["entity_key"], {"entity"})
                reference(proposal["event_key"], {"event"})
                _enum(proposal["role"], PARTICIPATION_ROLES)
            elif kind == "relationship":
                reference(proposal["subject_key"], {"entity", "event", "claim"})
                reference(proposal["object_key"], {"entity", "event", "claim"})
                _enum(proposal["predicate_ref"], ASSERTED_PREDICATES)
                if proposal["subject_key"] == proposal["object_key"]:
                    raise ValueError("relationship endpoints must remain distinct")
            elif kind == "event":
                event_time = _time(
                    {
                        "role": "event_time",
                        "value": proposal["event_time"],
                        "precision": proposal["time_precision"],
                        "modality": proposal["time_modality"],
                    },
                    kind,
                )
                if any(
                    t["role"] == "event_time" and t != event_time for t in row["time"]
                ):
                    raise ValueError("inconsistent event time")
        gaps = [_gap(g, handles) for g in _list(root["gaps"])]
        questions: dict[str, list[str]] = {}
        for proposal in _list(root["identity_proposals"]):
            _object(proposal, {"left_key", "right_key", "rationale"})
            left, right = proposal["left_key"], proposal["right_key"]
            _text(left, key=True)
            _text(right, key=True)
            reference(left, {"entity"})
            reference(right, {"entity"})
            if left == right:
                raise ValueError("identity proposal requires distinct local objects")
            _text(proposal["rationale"])
            question = f"Unresolved identity {left} / {right}: {proposal['rationale']}"
            questions.setdefault(left, []).append(question)
            questions.setdefault(right, []).append(question)
        assessments = _list(root["evidence_assessments"])
        for assessment in assessments:
            _object(
                assessment,
                {"claim_key", "evidence_link_keys", "dimensions", "uncertainty"},
            )
            reference(_text(assessment["claim_key"], key=True), {"claim"})
            refs = _list(assessment["evidence_link_keys"])
            if not refs or any(
                type(r) is not str or link_claims.get(r) != assessment["claim_key"]
                for r in refs
            ):
                raise ValueError("assessment link/claim binding mismatch")
            dimensions = _object(
                assessment["dimensions"], {f.name for f in fields(EvidenceDimensions)}
            )
            for value in dimensions.values():
                _text(value)
            _enum(
                dimensions["independence"],
                frozenset(
                    {"independent", "dependent_or_derived", "shared_origin", "unknown"}
                ),
            )
            _text(assessment["uncertainty"])

        # Only the fully checked response can reach shared contract construction.
        def build_gap(gap: dict[str, Any]) -> KnownGap:
            return KnownGap(
                gap["gap_code"],
                None,
                gap["detail"],
                tuple(
                    handles[h].address.evidence_address_ref
                    for h in gap["evidence_handles"]
                ),
                invocation.task.concrete_ref,
            )

        candidates: list[SemanticCandidatePayload] = []
        for row in validated:
            evidence = tuple(dict.fromkeys(link["handle"] for link in row["links"]))
            provenance = ProducerProvenance(
                "cpkt.generic-semantic-producer",
                "1",
                invocation.backend.method,
                tuple(
                    EvidenceProvenance(
                        handles[h].address.source_key,
                        handles[h].address.source_ref,
                        handles[h].address.snapshot_ref,
                        handles[h].address.record_ref,
                        handles[h].address.evidence_address_ref,
                    )
                    for h in evidence
                ),
                None,
                None,
                invocation.invocation_ref,
                invocation.task.concrete_ref,
            )
            candidates.append(
                SemanticCandidatePayload(
                    candidate_payload_kind=row["kind"],
                    interpretation_rule_ref=None,
                    **{
                        f"proposed_{row['kind']}": PROPOSALS[row["kind"]](
                            **row["proposal"]
                        )
                    },
                    evidence_links=tuple(
                        ProposedEvidenceLink(
                            link["key"],
                            handles[link["handle"]].address.evidence_address_ref,
                            link["role"],
                        )
                        for link in row["links"]
                    ),
                    time=tuple(ProposedTime(**t) for t in row["time"]),
                    epistemic_context=EpistemicContext(**row["epistemic"])
                    if row["epistemic"]
                    else None,
                    applicability=Applicability(
                        tuple(row["applicability"]["context_refs"]),
                        tuple(row["applicability"]["conditions"]),
                    ),
                    profile_refs=invocation.policy.profile_refs,
                    known_conflicts=tuple(row["conflicts"]),
                    known_gaps=tuple(build_gap(g) for g in row["gaps"]),
                    producer_provenance=provenance,
                    semantic_task_ref=invocation.task.concrete_ref,
                    unresolved_identity_questions=tuple(questions.get(row["key"], ())),
                )
            )
        return DecodedCandidates(
            tuple(candidates),
            tuple(build_gap(g) for g in gaps),
            tuple(
                EvidenceAssessment(
                    "EA-"
                    + canonical_json_hash(
                        {
                            "invocation": invocation.invocation_ref,
                            "assessment": a,
                        }
                    )[:24],
                    a["claim_key"],
                    invocation.policy.purpose,
                    tuple(a["evidence_link_keys"]),
                    EvidenceDimensions(**a["dimensions"]),
                    invocation.backend.method,
                    "cpkt.generic-semantic-producer",
                    produced_at,
                    a["uncertainty"],
                )
                for a in assessments
            ),
        )
