from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_text
from cp_knowledge_tools.publication.codec import (
    PublicationUnitDocument,
    parse_publication_unit,
    render_publication_unit,
)

from .models import CoreDiagnostic, RuleOutcome
from .profiles import CORE_VOCABULARIES, ProfileComposition

RuleHandler = Callable[["RuleContext"], RuleOutcome]

_PRIMARY_KINDS = {
    "concept_definition",
    "entity_profile",
    "event_summary",
    "procedure",
    "decision_guidance",
    "lesson_learned",
    "evidence_synthesis",
}
_KNOWLEDGE_FUNCTIONS = {
    "descriptive",
    "explanatory",
    "procedural",
    "advisory",
    "evaluative",
    "comparative",
    "diagnostic",
    "predictive",
}
_EPISTEMIC_STATUSES = {
    "unassessed",
    "reported",
    "observed",
    "inferred",
    "hypothesized",
    "confirmed",
    "disputed",
}
_EVIDENCE_ROLES = {
    "supports",
    "contradicts",
    "qualifies",
    "reports_statement",
    "derivation_input",
}
_RELATIONSHIP_CLASSES = {
    "asserted_relationship",
    "event_participation",
    "structural_relationship",
}
_RELATIONSHIP_PREDICATES = set(CORE_VOCABULARIES["relationship_predicate"]["terms"])
_CONFLICT_DIMENSIONS = {
    "factual",
    "temporal",
    "contextual",
    "definitional",
    "normative",
    "authority",
}
_TIME_ROLES = {
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
_TIME_PRECISIONS = {
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
_TIME_MODALITIES = {"actual", "planned", "expected", "hypothetical"}


@dataclass(frozen=True)
class RuleContext:
    input_value: dict[str, Any]
    rule_definition: dict[str, Any]
    profile_payload: dict[str, Any]
    profile_composition: ProfileComposition | None = None

    def diagnostic(
        self,
        *,
        path: str,
        message: str,
        code: str | None = None,
        severity: str | None = None,
    ) -> CoreDiagnostic:
        return CoreDiagnostic(
            severity=severity or self.rule_definition["severity"],
            code=code or self.rule_definition["diagnostic_code"],
            path=path,
            message=message,
            validator_rule_ref=self.rule_definition["validator_rule_ref"],
            rule_sources=tuple(self.rule_definition.get("rule_sources", [])),
        )


def _profile_term_diagnostic(
    context: RuleContext,
    rule: dict[str, Any] | None,
    *,
    path: str,
    message: str,
) -> CoreDiagnostic:
    if rule is None:
        return context.diagnostic(path=path, message=message)
    return CoreDiagnostic(
        severity=rule["severity"],
        code=rule["diagnostic_code"],
        path=path,
        message=message,
        validator_rule_ref=rule["validator_rule_ref"],
        rule_sources=tuple(rule["rule_sources"]),
    )


def _manifest(input_value: dict[str, Any]) -> dict[str, Any] | None:
    value = input_value.get("manifest")
    return value if isinstance(value, dict) else None


def _document(input_value: dict[str, Any]) -> PublicationUnitDocument | None:
    manifest = _manifest(input_value)
    body = input_value.get("markdown_body")
    if manifest is None or not isinstance(body, str):
        return None
    return PublicationUnitDocument(deepcopy(manifest), body)


def _reference_key(value: Any) -> tuple[str, str, str, str]:
    if not isinstance(value, dict):
        return ("", "", "", "")
    return (
        str(value.get("stable_id", "")),
        str(value.get("version", "")),
        str(value.get("subject_type", "")),
        str(value.get("authority_context", "")),
    )


def _semantic_reference_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return _reference_key(actual) == _reference_key(expected)
    if isinstance(actual, dict):
        return actual.get("stable_id") == expected
    return actual == expected


def _id_key(name: str) -> Callable[[dict[str, Any]], tuple[str, str]]:
    def key(value: dict[str, Any]) -> tuple[str, str]:
        item = value.get(name)
        if isinstance(item, dict):
            return (str(item.get("stable_id", "")), str(item.get("version", "")))
        return (str(item or ""), "")

    return key


def _sorted_copy(values: Any, key: Callable[[dict[str, Any]], Any]) -> list[Any]:
    if not isinstance(values, list):
        return []
    copied = deepcopy(values)
    return sorted(copied, key=key)


def build_round_trip_projection(
    document: PublicationUnitDocument,
    profile_payload: dict[str, Any],
) -> dict[str, Any]:
    contract = profile_payload["semantic_projection_contract"]
    projection: dict[str, Any] = {}
    sortable = {
        "claims": _id_key("claim_ref"),
        "events": _id_key("event_ref"),
        "event_participations": _id_key("participation_ref"),
        "evidence_links": _id_key("evidence_link_id"),
        "structural_relationships": _id_key("relationship_id"),
        "conflict_sets": _id_key("conflict_set_id"),
        "policy_anchors": _id_key("policy_anchor_id"),
        "cross_view_mappings": _id_key("mapping_id"),
        "evidence_assessments": _id_key("assessment_ref"),
        "temporal_constraints": _id_key("constraint_ref"),
    }
    for field_name in contract["round_trip_projection"]:
        if field_name == "identity":
            projection[field_name] = {
                "knowledge_object_id": document.manifest.get("knowledge_object_id"),
                "knowledge_object_version": document.manifest.get(
                    "knowledge_object_version"
                ),
            }
        elif field_name == "body_sha256":
            projection[field_name] = sha256_text(document.markdown_body)
        elif field_name in sortable:
            projection[field_name] = _sorted_copy(
                document.manifest.get(field_name, []), sortable[field_name]
            )
        else:
            projection[field_name] = deepcopy(document.manifest.get(field_name))
    for field_name in ("evidence_assessments", "temporal_constraints"):
        if field_name in document.manifest and field_name not in projection:
            projection[field_name] = _sorted_copy(
                document.manifest.get(field_name, []), sortable[field_name]
            )
    return projection


def build_rebuild_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    claims = []
    for claim in manifest.get("claims", []):
        claims.append(
            {
                "claim_ref": deepcopy(claim.get("claim_ref")),
                "statement": deepcopy(claim.get("statement")),
                "epistemic_status": claim.get("epistemic_status"),
                "time": deepcopy(claim.get("time", [])),
                "evidence_link_ids": deepcopy(claim.get("evidence_link_ids", [])),
                "policy_anchor_ids": deepcopy(claim.get("policy_anchor_ids", [])),
                "conflict_set_ids": deepcopy(claim.get("conflict_set_ids", [])),
                "epistemic_context": deepcopy(claim.get("epistemic_context")),
                "evidence_assessment_refs": deepcopy(
                    claim.get("evidence_assessment_refs", [])
                ),
                "qualification_claim_refs": deepcopy(
                    claim.get("qualification_claim_refs", [])
                ),
            }
        )

    events = []
    for event in manifest.get("events", []):
        events.append(
            {
                "event_ref": deepcopy(event.get("event_ref")),
                "event_type_ref": event.get("event_type_ref"),
                "label": event.get("label"),
                "time": deepcopy(event.get("time", [])),
                "evidence_link_ids": deepcopy(event.get("evidence_link_ids", [])),
                "policy_anchor_ids": deepcopy(event.get("policy_anchor_ids", [])),
            }
        )

    participations = []
    for participation in manifest.get("event_participations", []):
        participations.append(
            {
                "participation_ref": deepcopy(participation.get("participation_ref")),
                "event_ref": deepcopy(participation.get("event_ref")),
                "entity_ref": deepcopy(participation.get("entity_ref")),
                "role": participation.get("role"),
                "time": deepcopy(participation.get("time", [])),
                "claim_refs": deepcopy(participation.get("claim_refs", [])),
                "evidence_link_ids": deepcopy(
                    participation.get("evidence_link_ids", [])
                ),
                "policy_anchor_ids": deepcopy(
                    participation.get("policy_anchor_ids", [])
                ),
            }
        )

    evidence = []
    for link in manifest.get("evidence_links", []):
        evidence.append(
            {
                "evidence_link_id": link.get("evidence_link_id"),
                "subject_ref": deepcopy(link.get("subject_ref")),
                "evidence_address_ref": deepcopy(link.get("evidence_address_ref")),
                "role": link.get("role"),
            }
        )

    return {
        "knowledge_object_ref": {
            "stable_id": manifest.get("knowledge_object_id"),
            "version": manifest.get("knowledge_object_version"),
        },
        "claim_index": sorted(claims, key=_id_key("claim_ref")),
        "event_index": sorted(events, key=_id_key("event_ref")),
        "participation_index": sorted(participations, key=_id_key("participation_ref")),
        "evidence_index": sorted(evidence, key=_id_key("evidence_link_id")),
        "evidence_assessment_index": _sorted_copy(
            manifest.get("evidence_assessments", []), _id_key("assessment_ref")
        ),
        "temporal_constraint_index": _sorted_copy(
            manifest.get("temporal_constraints", []), _id_key("constraint_ref")
        ),
        "conflict_index": _sorted_copy(
            manifest.get("conflict_sets", []), _id_key("conflict_set_id")
        ),
        "policy_index": _sorted_copy(
            manifest.get("policy_anchors", []), _id_key("policy_anchor_id")
        ),
    }


def _claim_material_projection(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(claim.get(key))
        for key in (
            "statement",
            "epistemic_status",
            "time",
            "evidence_link_ids",
            "authority_basis_refs",
            "conflict_set_ids",
            "epistemic_context",
            "evidence_assessment_refs",
            "qualification_claim_refs",
        )
    }


def _rule_claim_identity(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    previous = context.input_value.get("previous_publication_unit")
    candidate = context.input_value.get("candidate_publication_unit")
    if isinstance(previous, dict) and isinstance(candidate, dict):
        previous_manifest = _manifest(previous) or {}
        candidate_manifest = _manifest(candidate) or {}
        previous_claims = {
            _reference_key(claim.get("claim_ref")): claim
            for claim in previous_manifest.get("claims", [])
        }
        for index, claim in enumerate(candidate_manifest.get("claims", [])):
            old = previous_claims.get(_reference_key(claim.get("claim_ref")))
            if old is not None and _claim_material_projection(old) != (
                _claim_material_projection(claim)
            ):
                outcome.diagnostics.append(
                    context.diagnostic(
                        path=f"/claims/{index}/claim_ref",
                        message=(
                            "claim identity was reused for materially different meaning"
                        ),
                    )
                )
        return outcome

    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    seen: dict[tuple[str, str, str, str], tuple[int, dict[str, Any]]] = {}
    for index, claim in enumerate(manifest.get("claims", [])):
        key = _reference_key(claim.get("claim_ref"))
        if key in seen and _claim_material_projection(seen[key][1]) != (
            _claim_material_projection(claim)
        ):
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/claims/{index}/claim_ref",
                    message=(
                        "duplicate claim identity carries different material meaning"
                    ),
                )
            )
        seen[key] = (index, claim)
    return outcome


def _rule_conflict(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    claims = {
        _reference_key(claim.get("claim_ref")): claim
        for claim in manifest.get("claims", [])
    }
    for index, conflict in enumerate(manifest.get("conflict_sets", [])):
        conflict_id = conflict.get("conflict_set_id")
        refs = conflict.get("claim_refs")
        valid = isinstance(refs, list) and len(refs) >= 2
        dimensions = conflict.get("conflict_dimensions")
        valid = valid and bool(dimensions)
        valid = valid and all(
            dimension in _CONFLICT_DIMENSIONS
            for dimension in (dimensions if isinstance(dimensions, list) else [])
        )
        for ref in refs if isinstance(refs, list) else []:
            claim = claims.get(_reference_key(ref))
            valid = valid and claim is not None
            valid = valid and conflict_id in (claim or {}).get("conflict_set_ids", [])
        preferred = conflict.get("preferred_claim_ref")
        if preferred is not None:
            valid = valid and _reference_key(preferred) in {
                _reference_key(ref) for ref in (refs if isinstance(refs, list) else [])
            }
        if not valid:
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/conflict_sets/{index}",
                    message=(
                        "conflict alternatives or their references were not preserved"
                    ),
                )
            )
    return outcome


def _rule_corpus(_context: RuleContext) -> RuleOutcome:
    # Corpus integrity is established before any case can be dispatched.
    return RuleOutcome(artifacts={"corpus_integrity_verified": True})


def _rule_epistemic(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    evidence = {
        item.get("evidence_link_id"): item
        for item in manifest.get("evidence_links", [])
        if isinstance(item, dict)
    }
    for index, claim in enumerate(manifest.get("claims", [])):
        if claim.get("epistemic_status") != "confirmed":
            continue
        linked = [
            evidence.get(link_id) for link_id in claim.get("evidence_link_ids", [])
        ]
        roles = {item.get("role") for item in linked if isinstance(item, dict)}
        authority = claim.get("authority_basis_refs")
        if roles and roles <= {"reports_statement"} and not authority:
            outcome.diagnostics.append(
                context.diagnostic(
                    code="reported_statement_used_as_confirmation",
                    path=f"/claims/{index}/epistemic_status",
                    message=(
                        "reported-statement Evidence alone cannot establish "
                        "confirmation"
                    ),
                )
            )
        elif not authority and "supports" not in roles:
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/claims/{index}/epistemic_status",
                    message=(
                        "confirmed Claim lacks supporting Evidence or Authority basis"
                    ),
                )
            )
    return outcome


def _rule_event(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    events = {
        _reference_key(event.get("event_ref")): event
        for event in manifest.get("events", [])
        if isinstance(event, dict)
    }
    composition = context.profile_composition
    core_roles = set(CORE_VOCABULARIES["event_participation_role"]["terms"])
    profile_roles = composition.profile_role_terms if composition else {}
    event_type_terms = composition.profile_event_type_terms if composition else {}
    event_type_namespaces = (
        composition.profile_event_type_namespaces if composition else ()
    )
    for index, event in enumerate(manifest.get("events", [])):
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type_ref")
        matching_namespace = next(
            (
                namespace
                for namespace in event_type_namespaces
                if isinstance(event_type, str)
                and event_type.startswith(f"{namespace}.")
            ),
            None,
        )
        if matching_namespace is not None and event_type not in event_type_terms:
            known = next(
                (
                    item
                    for item in event_type_terms.values()
                    if item["namespace"] == matching_namespace
                ),
                None,
            )
            rule = known.get("validator_rule") if known else None
            outcome.diagnostics.append(
                _profile_term_diagnostic(
                    context,
                    rule,
                    path=f"/events/{index}/event_type_ref",
                    message="event type is outside the effective Profile Vocabulary",
                )
            )
    for index, participation in enumerate(manifest.get("event_participations", [])):
        role = participation.get("role")
        if not role:
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/event_participations/{index}/role",
                    message="event participation has no controlled role",
                )
            )
        elif role not in core_roles and role not in profile_roles:
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/event_participations/{index}/role",
                    message=(
                        "event participation role is outside the effective controlled "
                        "Vocabulary"
                    ),
                )
            )
        elif (
            not isinstance(participation.get("entity_ref"), dict)
            or _reference_key(participation.get("event_ref")) not in events
        ):
            outcome.diagnostics.append(
                context.diagnostic(
                    path=f"/event_participations/{index}",
                    message=(
                        "event participation does not resolve to an event and entity"
                    ),
                )
            )
        elif role in profile_roles:
            role_term = profile_roles[role]
            allowed = role_term.get("allowed_event_types")
            event = events[_reference_key(participation.get("event_ref"))]
            event_type = event.get("event_type_ref")
            event_term = event_type_terms.get(event_type, {})
            event_code = event_term.get("code")
            if (
                isinstance(allowed, list)
                and event_type not in allowed
                and (event_code not in allowed)
            ):
                outcome.diagnostics.append(
                    _profile_term_diagnostic(
                        context,
                        role_term.get("validator_rule"),
                        path=f"/event_participations/{index}/role",
                        message=(
                            "Profile event participation role is not allowed for "
                            f"event type {event_type!r}"
                        ),
                    )
                )
    return outcome


def _rule_policy(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    execution = context.input_value.get("execution_context")
    if manifest is None or not isinstance(execution, dict):
        return outcome

    expected = execution.get("expected_access")
    decisions = execution.get("policy_decisions")
    applicability = execution.get("profile_applicability")
    if not isinstance(expected, dict) or not isinstance(decisions, dict):
        outcome.diagnostics.append(
            context.diagnostic(
                path="/execution_context/policy_decisions",
                message="independent policy decisions are missing",
            )
        )
        return outcome

    claim_access = expected.get("claim_read")
    evidence_access = expected.get("evidence_resolution")
    distinct_decisions = len(decisions) >= 2
    values = list(decisions.values())
    independent = (
        claim_access in {"permit", "deny"}
        and evidence_access in {"permit", "deny"}
        and claim_access in values
        and evidence_access in values
        and distinct_decisions
    )
    if not independent:
        outcome.diagnostics.append(
            context.diagnostic(
                path="/execution_context/expected_access/evidence_resolution",
                message="Claim Read was treated as Evidence Resolution authority",
            )
        )

    invariant_names: list[str] = []
    if independent:
        invariant_names.append(
            "claim_read_and_evidence_resolution_independently_decided"
        )
    if isinstance(applicability, dict):
        empty_resolved = (
            applicability.get("resolution_status") == "resolved"
            and applicability.get("determination") == "no_profile_applicable"
            and applicability.get("applicable_profile_refs") == []
            and applicability.get("profile_refs_complete") is True
            and manifest.get("profile_refs") == []
        )
        if empty_resolved:
            invariant_names.append(
                "empty_profile_refs_accepted_when_no_runtime_profile_applies"
            )

    validator_profiles = {
        "cpks.profile.core-knowledge",
        "cpks.profile.contract-conformance",
        "cpks.profile.canonicalization.canonical-json-value",
    }
    runtime_refs = manifest.get("profile_refs", [])
    contains_validator_profile = any(
        (
            item.get("stable_id")
            if isinstance(item, dict)
            else str(item).split("@", 1)[0]
        )
        in validator_profiles
        for item in runtime_refs
    )
    if contains_validator_profile:
        outcome.diagnostics.append(
            context.diagnostic(
                path="/profile_refs",
                message="validator Profile was used as a runtime authorization Profile",
            )
        )
    else:
        invariant_names.append(
            "validator_profiles_not_used_as_runtime_authorization_profiles"
        )
    invariant_order = (
        "empty_profile_refs_accepted_when_no_runtime_profile_applies",
        "claim_read_and_evidence_resolution_independently_decided",
        "validator_profiles_not_used_as_runtime_authorization_profiles",
    )
    outcome.artifacts["invariants"] = [
        name for name in invariant_order if name in invariant_names
    ]
    return outcome


def _rule_profile(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    extension = context.input_value.get("profile_extension")
    if not isinstance(extension, dict):
        return outcome
    namespace = extension.get("namespace")
    if isinstance(namespace, str) and (
        namespace == "cpks.vocab.core" or namespace.startswith("cpks.vocab.core.")
    ):
        outcome.diagnostics.append(
            context.diagnostic(
                path="/profile_extension/namespace",
                message="Profile extension collides with the Core Vocabulary namespace",
            )
        )
    return outcome


def _rule_rebuild(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    first = build_rebuild_projection(manifest)
    first_hash = canonical_json_hash(first)
    del first
    second = build_rebuild_projection(manifest)
    second_hash = canonical_json_hash(second)
    same = first_hash == second_hash

    evidence_roles_preserved = all(
        item.get("role") is not None for item in second["evidence_index"]
    )
    conflicts_preserved = len(second["conflict_index"]) == len(
        manifest.get("conflict_sets", [])
    )
    policy_preserved = len(second["policy_index"]) == len(
        manifest.get("policy_anchors", [])
    )
    canonical_refs_preserved = all(
        isinstance(item.get("claim_ref"), dict) for item in second["claim_index"]
    ) and all(isinstance(item.get("event_ref"), dict) for item in second["event_index"])
    rebuild = {
        "canonical_references_preserved": canonical_refs_preserved,
        "conflicts_preserved": conflicts_preserved,
        "evidence_roles_preserved": evidence_roles_preserved,
        "policy_anchors_preserved": policy_preserved,
        "projection_hash": second_hash,
        "same_hash_after_delete_and_rebuild": same,
    }
    outcome.artifacts.update({"derived_projection": second, "rebuild": rebuild})
    if not all(
        (
            same,
            evidence_roles_preserved,
            conflicts_preserved,
            policy_preserved,
            canonical_refs_preserved,
        )
    ):
        outcome.diagnostics.append(
            context.diagnostic(
                path="/derived_projection",
                message="derived projection changed after deletion and rebuild",
            )
        )
    return outcome


def _rule_round_trip(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    document = _document(context.input_value)
    if document is None:
        return outcome
    before = build_round_trip_projection(document, context.profile_payload)
    rendered = render_publication_unit(document)
    reparsed = parse_publication_unit(rendered)
    after = build_round_trip_projection(reparsed, context.profile_payload)
    before_hash = canonical_json_hash(before)
    after_hash = canonical_json_hash(after)
    identity_preserved = before.get("identity") == after.get("identity")
    references_preserved = all(
        before.get(key) == after.get(key)
        for key in (
            "claims",
            "events",
            "event_participations",
            "evidence_links",
            "structural_relationships",
            "conflict_sets",
            "policy_anchors",
            "evidence_assessments",
            "temporal_constraints",
        )
    )
    anchors_preserved = before.get("cross_view_mappings") == after.get(
        "cross_view_mappings"
    )
    logical_equivalent = before == after
    round_trip = {
        "anchors_preserved": anchors_preserved,
        "identity_preserved": identity_preserved,
        "logical_equivalent": logical_equivalent,
        "references_preserved": references_preserved,
        "same_semantic_projection_hash_after_reparse": before_hash == after_hash,
        "semantic_projection_hash": after_hash,
    }
    outcome.artifacts.update({"round_trip": round_trip, "semantic_projection": after})
    if not all(round_trip.values()):
        outcome.diagnostics.append(
            context.diagnostic(
                path="/publication_unit",
                message=(
                    "Publication Unit parse/render/reparse changed semantic meaning"
                ),
            )
        )
    return outcome


def _schema_diagnostic(context: RuleContext, path: str, message: str) -> CoreDiagnostic:
    return context.diagnostic(path=path, message=message)


def _rule_schema(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    manifest = _manifest(context.input_value)
    if manifest is None:
        outcome.diagnostics.append(
            _schema_diagnostic(context, "/manifest", "manifest must be an object")
        )
        return outcome
    required_string_fields = (
        "document_type",
        "schema_ref",
        "template_ref",
        "semantic_model_ref",
        "vocabulary_set_ref",
        "knowledge_object_id",
        "knowledge_object_version",
        "title",
        "language",
        "primary_kind",
    )
    for field_name in required_string_fields:
        if not isinstance(manifest.get(field_name), str) or not manifest[field_name]:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/{field_name}",
                    f"required string field {field_name!r} is missing",
                )
            )
    required_list_fields = (
        "knowledge_functions",
        "profile_refs",
        "claims",
        "events",
        "event_participations",
        "evidence_links",
        "structural_relationships",
        "conflict_sets",
        "policy_anchors",
        "cross_view_mappings",
        "review_record_refs",
        "policy_decision_refs",
    )
    for field_name in required_list_fields:
        if not isinstance(manifest.get(field_name), list):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/{field_name}",
                    f"required list field {field_name!r} is missing",
                )
            )
    for field_name in ("applicability", "human_readable", "publication", "integrity"):
        if not isinstance(manifest.get(field_name), dict):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/{field_name}",
                    f"required object field {field_name!r} is missing",
                )
            )

    hardening_present = any(
        field in manifest for field in ("evidence_assessments", "temporal_constraints")
    )
    exact_values = {
        "document_type": "knowledge_object_publication_unit",
        "schema_ref": (
            "CPKS-SPEC-KM-PU@0.3" if hardening_present else "CPKS-SPEC-KM-PU@0.2"
        ),
        "semantic_model_ref": (
            "CPKS-SPEC-KM@0.21" if hardening_present else "CPKS-SPEC-KM@0.20"
        ),
        "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
    }
    if not hardening_present:
        exact_values["template_ref"] = "CPKS-TPL-KM-PU@0.2"
    for field_name, expected in exact_values.items():
        if field_name in manifest and manifest.get(field_name) != expected:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/{field_name}",
                    f"{field_name!r} must equal {expected!r}",
                )
            )
    if hardening_present and manifest.get("template_ref") in {
        "CPKS-TPL-KM-PU@0.1",
        "CPKS-TPL-KM-PU@0.2",
    }:
        outcome.diagnostics.append(
            _schema_diagnostic(
                context,
                "/template_ref",
                "KM-PU 0.3 cannot claim compatibility through an older Template",
            )
        )
    version = manifest.get("knowledge_object_version")
    if isinstance(version, str) and not re.fullmatch(
        r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", version
    ):
        outcome.diagnostics.append(
            _schema_diagnostic(
                context,
                "/knowledge_object_version",
                "Knowledge Object version has an invalid syntax",
            )
        )
    if manifest.get("primary_kind") not in _PRIMARY_KINDS:
        outcome.diagnostics.append(
            _schema_diagnostic(
                context,
                "/primary_kind",
                "primary_kind is outside the closed Core Vocabulary",
            )
        )
    functions = manifest.get("knowledge_functions", [])
    if isinstance(functions, list) and (
        len(functions) != len(set(functions))
        or any(item not in _KNOWLEDGE_FUNCTIONS for item in functions)
    ):
        outcome.diagnostics.append(
            _schema_diagnostic(
                context,
                "/knowledge_functions",
                "knowledge_functions are duplicated or outside the Core Vocabulary",
            )
        )

    applicability = manifest.get("applicability")
    if isinstance(applicability, dict):
        for field_name in (
            "domain_refs",
            "entity_refs",
            "organization_refs",
            "product_refs",
            "purposes",
            "valid_time",
        ):
            if not isinstance(applicability.get(field_name), list):
                outcome.diagnostics.append(
                    _schema_diagnostic(
                        context,
                        f"/applicability/{field_name}",
                        "required applicability collection is missing",
                    )
                )

    def valid_reference(value: Any) -> bool:
        return isinstance(value, dict) and all(
            isinstance(value.get(field_name), str) and value[field_name]
            for field_name in (
                "subject_type",
                "stable_id",
                "version",
                "authority_context",
            )
        )

    for index, claim in enumerate(manifest.get("claims", [])):
        if not isinstance(claim, dict):
            continue
        for field_name in (
            "time",
            "evidence_link_ids",
            "authority_basis_refs",
            "policy_anchor_ids",
            "conflict_set_ids",
        ):
            if not isinstance(claim.get(field_name), list):
                outcome.diagnostics.append(
                    _schema_diagnostic(
                        context,
                        f"/claims/{index}/{field_name}",
                        "required Claim collection is missing",
                    )
                )
        if not valid_reference(claim.get("claim_ref")):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/claims/{index}/claim_ref",
                    "Claim reference is incomplete",
                )
            )
        if claim.get("epistemic_status") not in _EPISTEMIC_STATUSES:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/claims/{index}/epistemic_status",
                    "epistemic_status is outside the closed Core Vocabulary",
                )
            )
        statement = claim.get("statement")
        if (
            not isinstance(statement, dict)
            or not valid_reference(statement.get("subject_ref"))
            or not isinstance(statement.get("predicate_ref"), str)
            or not isinstance(statement.get("object"), dict)
            or statement.get("object", {}).get("kind") not in {"literal", "reference"}
        ):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/claims/{index}/statement",
                    "Claim statement is structurally invalid",
                )
            )

    for index, link in enumerate(manifest.get("evidence_links", [])):
        if not isinstance(link, dict):
            continue
        if (
            not isinstance(link.get("evidence_link_id"), str)
            or not valid_reference(link.get("subject_ref"))
            or not valid_reference(link.get("evidence_address_ref"))
        ):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/evidence_links/{index}",
                    "Evidence Link identity or references are incomplete",
                )
            )
        if link.get("role") not in _EVIDENCE_ROLES:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/evidence_links/{index}/role",
                    "Evidence role is outside the closed Core Vocabulary",
                )
            )

    for index, relationship in enumerate(manifest.get("structural_relationships", [])):
        if not isinstance(relationship, dict):
            continue
        if relationship.get("relationship_class") not in _RELATIONSHIP_CLASSES:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/structural_relationships/{index}/relationship_class",
                    "relationship_class is outside the closed Core Vocabulary",
                )
            )
        if relationship.get("predicate") not in _RELATIONSHIP_PREDICATES:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/structural_relationships/{index}/predicate",
                    "relationship predicate is outside the closed Core Vocabulary",
                )
            )

    publication = manifest.get("publication")
    if isinstance(publication, dict):
        if "publication_finalization_plan_ref" not in publication:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    "/publication/publication_finalization_plan_ref",
                    "publication_finalization_plan_ref is required by KM-PU 0.2",
                )
            )
        elif publication.get("publication_finalization_plan_ref") is not None and (
            not isinstance(publication.get("publication_finalization_plan_ref"), str)
            or not publication["publication_finalization_plan_ref"]
        ):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    "/publication/publication_finalization_plan_ref",
                    (
                        "publication_finalization_plan_ref must be null or "
                        "a concrete reference"
                    ),
                )
            )
        if publication.get("publication_state") not in {
            "unpublished",
            "published",
            "superseded",
        }:
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    "/publication/publication_state",
                    "publication_state is outside the controlled lifecycle",
                )
            )

    claim_refs = {
        _reference_key(item.get("claim_ref"))
        for item in manifest.get("claims", [])
        if isinstance(item, dict)
    }
    event_refs = {
        _reference_key(item.get("event_ref"))
        for item in manifest.get("events", [])
        if isinstance(item, dict)
    }
    evidence_ids = {
        item.get("evidence_link_id")
        for item in manifest.get("evidence_links", [])
        if isinstance(item, dict)
    }
    local_id_specs = (
        ("claims", "claim_ref"),
        ("events", "event_ref"),
        ("event_participations", "participation_ref"),
        ("evidence_links", "evidence_link_id"),
        ("structural_relationships", "relationship_id"),
        ("conflict_sets", "conflict_set_id"),
        ("policy_anchors", "policy_anchor_id"),
        ("cross_view_mappings", "mapping_id"),
    )
    for collection_name, identity_field in local_id_specs:
        identities: list[Any] = []
        for item in manifest.get(collection_name, []):
            if not isinstance(item, dict):
                identities.append(None)
                continue
            identity = item.get(identity_field)
            identities.append(
                _reference_key(identity) if isinstance(identity, dict) else identity
            )
        if any(not identity for identity in identities) or len(identities) != len(
            set(identities)
        ):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/{collection_name}",
                    f"{identity_field} values are missing or duplicated",
                )
            )
    for collection_name in ("claims", "events", "event_participations"):
        for index, item in enumerate(manifest.get(collection_name, [])):
            if not isinstance(item, dict):
                outcome.diagnostics.append(
                    _schema_diagnostic(
                        context,
                        f"/{collection_name}/{index}",
                        "semantic item must be an object",
                    )
                )
                continue
            for link_id in item.get("evidence_link_ids", []):
                if link_id not in evidence_ids:
                    outcome.diagnostics.append(
                        _schema_diagnostic(
                            context,
                            f"/{collection_name}/{index}/evidence_link_ids",
                            f"local Evidence Link {link_id!r} does not resolve",
                        )
                    )
    for index, participation in enumerate(manifest.get("event_participations", [])):
        if (
            isinstance(participation, dict)
            and _reference_key(participation.get("event_ref")) not in event_refs
        ):
            outcome.diagnostics.append(
                _schema_diagnostic(
                    context,
                    f"/event_participations/{index}/event_ref",
                    "local Event reference does not resolve",
                )
            )
    for index, conflict in enumerate(manifest.get("conflict_sets", [])):
        for ref in conflict.get("claim_refs", []) if isinstance(conflict, dict) else []:
            if _reference_key(ref) not in claim_refs:
                outcome.diagnostics.append(
                    _schema_diagnostic(
                        context,
                        f"/conflict_sets/{index}/claim_refs",
                        "local Claim reference does not resolve",
                    )
                )
    execution = context.input_value.get("execution_context")
    if (
        isinstance(execution, dict)
        and execution.get("all_declared_references_resolve") is False
    ):
        outcome.diagnostics.append(
            _schema_diagnostic(
                context,
                "/execution_context/all_declared_references_resolve",
                "declared external references do not resolve",
            )
        )
    return outcome


def _parse_date_boundary(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _intervals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start = _parse_date_boundary(left.get("start"))
    right_start = _parse_date_boundary(right.get("start"))
    left_end = _parse_date_boundary(left.get("end")) or left_start
    right_end = _parse_date_boundary(right.get("end")) or right_start
    if None in (left_start, right_start, left_end, right_end):
        return True
    return left_start <= right_end and right_start <= left_end


def _rule_time(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome(artifacts={"conflict_required": False})
    manifest = _manifest(context.input_value)
    if manifest is None:
        return outcome
    owners = (
        ("claims", manifest.get("claims", [])),
        ("events", manifest.get("events", [])),
        ("event_participations", manifest.get("event_participations", [])),
    )
    for collection_name, items in owners:
        for item_index, item in enumerate(items):
            for time_index, temporal in enumerate(item.get("time", [])):
                valid = isinstance(temporal, dict)
                if valid:
                    role = temporal.get("role")
                    value_kind = temporal.get("value_kind")
                    precision = temporal.get("precision")
                    modality = temporal.get("modality")
                    valid = (
                        role in _TIME_ROLES
                        and value_kind in {"instant", "interval", "unknown"}
                        and precision in _TIME_PRECISIONS
                        and modality in _TIME_MODALITIES
                        and isinstance(temporal.get("approximate"), bool)
                    )
                    if value_kind == "instant":
                        valid = valid and bool(temporal.get("start"))
                        valid = valid and temporal.get("end") is None
                    elif value_kind == "interval":
                        valid = valid and bool(
                            temporal.get("start") or temporal.get("end")
                        )
                    elif value_kind == "unknown":
                        valid = (
                            valid
                            and precision == "unknown"
                            and temporal.get("start") is None
                            and temporal.get("end") is None
                        )
                if not valid:
                    outcome.diagnostics.append(
                        context.diagnostic(
                            path=f"/{collection_name}/{item_index}/time/{time_index}",
                            message=(
                                "temporal role, value, precision, or modality "
                                "is invalid"
                            ),
                        )
                    )

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for claim in manifest.get("claims", []):
        statement = claim.get("statement", {})
        key = (
            _reference_key(statement.get("subject_ref")),
            statement.get("predicate_ref"),
        )
        groups.setdefault(key, []).append(claim)
    for claims in groups.values():
        for left_index, left in enumerate(claims):
            for right in claims[left_index + 1 :]:
                if left.get("statement", {}).get("object") == right.get(
                    "statement", {}
                ).get("object"):
                    continue
                left_times = left.get("time", [])
                right_times = right.get("time", [])
                if (
                    not left_times
                    or not right_times
                    or any(
                        _intervals_overlap(left_time, right_time)
                        for left_time in left_times
                        for right_time in right_times
                    )
                ):
                    outcome.artifacts["conflict_required"] = True
    return outcome


_ANCHOR_PATTERN = re.compile(r'<a\s+id=["\']([^"\']+)["\']\s*>\s*</a>')


def _rule_cross_view(context: RuleContext) -> RuleOutcome:
    outcome = RuleOutcome()
    document = _document(context.input_value)
    if document is None:
        return outcome
    mappings = document.manifest.get("cross_view_mappings", [])
    mapped = {
        item.get("narrative_anchor")
        for item in mappings
        if isinstance(item, dict) and item.get("material") is True
    }
    body_anchors = set(_ANCHOR_PATTERN.findall(document.markdown_body))
    presentation_anchors = {
        value
        for value in document.manifest.get("human_readable", {}).values()
        if isinstance(value, str)
    }
    supporting_anchors = {
        item.get("narrative_anchor")
        for collection in ("evidence_links", "policy_anchors")
        for item in document.manifest.get(collection, [])
        if isinstance(item, dict)
    }
    material_items = (
        ("claims", "claim_ref"),
        ("events", "event_ref"),
        ("event_participations", "participation_ref"),
        ("conflict_sets", "conflict_set_id"),
    )
    required: set[str] = set()
    semantic_by_anchor: dict[str, Any] = {}
    for collection_name, ref_name in material_items:
        for item in document.manifest.get(collection_name, []):
            if not isinstance(item, dict) or not item.get("narrative_anchor"):
                continue
            anchor = item["narrative_anchor"]
            required.add(anchor)
            semantic_by_anchor[anchor] = item.get(ref_name)
    mapping_by_anchor = {
        item.get("narrative_anchor"): item
        for item in mappings
        if isinstance(item, dict) and item.get("material") is True
    }
    wrong_semantic_mapping = {
        anchor
        for anchor, expected_ref in semantic_by_anchor.items()
        if anchor in mapping_by_anchor
        and not _semantic_reference_matches(
            mapping_by_anchor[anchor].get("semantic_ref"), expected_ref
        )
    }
    unmapped = (required - mapped) | (
        body_anchors - mapped - presentation_anchors - supporting_anchors
    )
    missing_body = mapped - body_anchors
    for anchor in sorted(unmapped | missing_body | wrong_semantic_mapping):
        outcome.diagnostics.append(
            context.diagnostic(
                path=f"/markdown_body#{anchor}",
                message=(
                    "material narrative anchor lacks a bidirectional semantic mapping"
                ),
            )
        )
    return outcome


RULE_REGISTRY: dict[str, RuleHandler] = {
    "CK-CLAIM-ID-001": _rule_claim_identity,
    "CK-CONFLICT-001": _rule_conflict,
    "CK-CORP-001": _rule_corpus,
    "CK-EPI-001": _rule_epistemic,
    "CK-EVT-001": _rule_event,
    "CK-POL-001": _rule_policy,
    "CK-PROFILE-001": _rule_profile,
    "CK-RB-001": _rule_rebuild,
    "CK-RT-001": _rule_round_trip,
    "CK-SCH-001": _rule_schema,
    "CK-TIME-001": _rule_time,
    "CK-XVIEW-001": _rule_cross_view,
}
