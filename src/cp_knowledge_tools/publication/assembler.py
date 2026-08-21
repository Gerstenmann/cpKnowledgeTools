from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from cp_knowledge_tools.validation.hardening import HardeningContractValidator

from .codec import (
    PublicationUnitDocument,
    load_publication_unit,
    render_publication_unit,
)
from .contracts import PUBLICATION_UNIT_TEMPLATE_BY_SCHEMA
from .hardening import HardeningPublicationContext
from .models import (
    PublicationAssemblyPlan,
    PublicationRepresentation,
    PublicationRepresentationItem,
    PublicationRepresentationSection,
    PublicationSemanticReference,
)


class PublicationAssemblyError(ValueError):
    """Raised when explicit publication inputs are structurally inconsistent."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _semantic_ref(
    subject_type: str,
    stable_id: str,
    *,
    authority_context: str = "Semantic Core",
) -> PublicationSemanticReference:
    return PublicationSemanticReference(
        subject_type=subject_type,
        stable_id=stable_id,
        version="0.1",
        authority_context=authority_context,
    )


def _time_value(
    role: str,
    value: str | None,
    precision: str,
    modality: str,
) -> dict[str, Any]:
    if value is None:
        return {
            "role": role,
            "value_kind": "unknown",
            "precision": "unknown",
            "modality": modality,
            "start": None,
            "end": None,
            "timezone": None,
            "approximate": False,
            "uncertainty": None,
            "source_ref": None,
        }
    timezone_match = re.search(r"(Z|[+-]\d{2}:\d{2})$", value)
    timezone = timezone_match.group(1) if timezone_match else None
    return {
        "role": role,
        "value_kind": "instant",
        "precision": precision,
        "modality": modality,
        "start": value,
        "end": None,
        "timezone": timezone,
        "approximate": False,
        "uncertainty": None,
        "source_ref": None,
    }


class PublicationUnitAssembler:
    """Build an unpublished Publication Unit from explicit, source-neutral inputs."""

    def assemble(
        self,
        semantic: dict[str, Any],
        *,
        plan: PublicationAssemblyPlan,
        representation: PublicationRepresentation,
        output_path: Path,
        publication_finalization_plan_ref: str | None = None,
        review_record_refs: tuple[str, ...] = (),
        policy_decision_refs: tuple[str, ...] = (),
        cross_view_report_ref: str | None = None,
        hardening_context: (
            HardeningPublicationContext | Mapping[str, Any] | None
        ) = None,
        compatible_template_ref: str | None = None,
    ) -> dict[str, Any]:
        semantic_refs = self._semantic_refs(semantic, plan)
        bindings = self._validate_plan(plan, semantic_refs)
        representation_indexes = self._validate_representation(
            semantic,
            plan,
            representation,
            semantic_refs,
        )

        claims = [
            self._claim_manifest(
                claim,
                semantic,
                plan,
                bindings,
                representation_indexes["claims"],
            )
            for claim in semantic["claims"]
        ]
        events = [
            self._event_manifest(
                event,
                semantic,
                bindings,
                representation_indexes["events"],
            )
            for event in semantic["events"]
        ]
        participations = [
            self._participation_manifest(
                participation,
                semantic,
                bindings,
                representation_indexes["events"],
            )
            for participation in semantic["participations"]
        ]
        evidence_links = [
            self._evidence_link_manifest(
                link,
                plan,
                bindings,
                representation_indexes["evidence"],
            )
            for link in semantic["evidence_links"]
        ]
        conflicts = [
            self._conflict_manifest(
                conflict,
                representation_indexes["conflicts"],
            )
            for conflict in semantic["conflict_sets"]
        ]
        canonical_hardening: dict[str, Any] | None = None
        if hardening_context is not None:
            try:
                context = (
                    hardening_context
                    if isinstance(hardening_context, HardeningPublicationContext)
                    else HardeningPublicationContext.from_mapping(hardening_context)
                )
                canonical_hardening = context.canonical_publication_fields(
                    claim_refs=tuple(item["claim_ref"] for item in semantic["claims"]),
                    conflict_claim_refs=tuple(
                        tuple(item["claim_refs"]) for item in semantic["conflict_sets"]
                    ),
                )
            except (TypeError, ValueError) as error:
                raise PublicationAssemblyError("PUB-HARD-001", str(error)) from error
            for claim, semantic_claim in zip(claims, semantic["claims"], strict=True):
                claim.update(
                    canonical_hardening["claim_fields"][semantic_claim["claim_ref"]]
                )
            for conflict, semantic_conflict in zip(
                conflicts, semantic["conflict_sets"], strict=True
            ):
                key = tuple(sorted(semantic_conflict["claim_refs"]))
                conflict.update(canonical_hardening["conflict_fields"][key])

        policy_anchors = [item.to_dict() for item in plan.policy_anchors]
        if policy_decision_refs:
            for policy_anchor in policy_anchors:
                policy_anchor["policy_decision_refs"] = list(policy_decision_refs)

        publication = {
            "publication_state": "unpublished",
            "publication_record_ref": None,
            "published_at": None,
            "publisher_ref": None,
            "predecessor_publication_ref": None,
        }
        if publication_finalization_plan_ref:
            publication["publication_finalization_plan_ref"] = (
                publication_finalization_plan_ref
            )

        schema_ref = (
            "CPKS-SPEC-KM-PU@0.3"
            if canonical_hardening is not None
            else (
                "CPKS-SPEC-KM-PU@0.2"
                if publication_finalization_plan_ref
                else "CPKS-SPEC-KM-PU@0.1"
            )
        )
        if canonical_hardening is not None and not compatible_template_ref:
            raise PublicationAssemblyError(
                "PUB-HARD-002",
                "KM-PU 0.3 assembly requires an explicit compatible Template ref",
            )
        manifest = {
            "document_type": "knowledge_object_publication_unit",
            "schema_ref": schema_ref,
            "template_ref": (
                compatible_template_ref
                if canonical_hardening is not None
                else PUBLICATION_UNIT_TEMPLATE_BY_SCHEMA[schema_ref]
            ),
            "semantic_model_ref": (
                "CPKS-SPEC-KM@0.21"
                if canonical_hardening is not None
                else "CPKS-SPEC-KM@0.20"
            ),
            "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
            "knowledge_object_id": plan.knowledge_object_id,
            "knowledge_object_version": plan.knowledge_object_version,
            "title": plan.title,
            "language": plan.language,
            "canonical_path": None,
            "primary_kind": plan.primary_kind,
            "knowledge_functions": list(plan.knowledge_functions),
            "applicability": plan.applicability.to_dict(),
            "profile_refs": list(plan.profile_refs),
            "claims": claims,
            "events": events,
            "event_participations": participations,
            "evidence_links": evidence_links,
            "structural_relationships": [],
            "conflict_sets": conflicts,
            "policy_anchors": policy_anchors,
            "cross_view_mappings": self._cross_view_mappings(representation),
            "human_readable": {
                "body_language": representation.body_language,
                "summary_anchor": representation.summary.narrative_anchor,
                "details_anchor": representation.details.narrative_anchor,
                "claims_anchor": representation.claims.narrative_anchor,
                "events_anchor": representation.events.narrative_anchor,
                "evidence_anchor": representation.evidence.narrative_anchor,
                "conflicts_anchor": representation.conflicts.narrative_anchor,
                "applicability_anchor": representation.applicability.narrative_anchor,
                "policy_anchor": representation.policy.narrative_anchor,
                "publication_anchor": representation.publication.narrative_anchor,
            },
            "review_record_refs": list(review_record_refs),
            "policy_decision_refs": list(policy_decision_refs),
            "publication": publication,
            "integrity": {
                "content_hash": None,
                "cross_view_validation": {
                    "status": "pending",
                    "report_ref": cross_view_report_ref,
                },
            },
        }
        if canonical_hardening is not None:
            manifest["evidence_assessments"] = canonical_hardening[
                "evidence_assessments"
            ]
            manifest["temporal_constraints"] = canonical_hardening[
                "temporal_constraints"
            ]

            validation = HardeningContractValidator().validate_publication_manifest(
                manifest
            )
            if not validation.valid:
                detail = ", ".join(
                    f"{item.code}@{item.path}" for item in validation.diagnostics
                )
                raise PublicationAssemblyError("PUB-HARD-001", detail)

        body = self._render_body(plan, representation)
        self._validate_cross_view(manifest, representation, body)
        manifest["integrity"]["cross_view_validation"]["status"] = "pass"

        document = PublicationUnitDocument(manifest=manifest, markdown_body=body)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_publication_unit(document), encoding="utf-8")
        return manifest

    def _semantic_refs(
        self,
        semantic: dict[str, Any],
        plan: PublicationAssemblyPlan,
    ) -> dict[tuple[str, str, str, str], PublicationSemanticReference]:
        required = (
            "entities",
            "claims",
            "evidence_links",
            "events",
            "participations",
            "conflict_sets",
        )
        missing = [key for key in required if not isinstance(semantic.get(key), list)]
        if missing:
            raise PublicationAssemblyError(
                "PUB-SEM-001",
                f"semantic state lacks list collections: {', '.join(missing)}",
            )

        refs = [plan.knowledge_object_ref]
        refs.extend(
            _semantic_ref("entity", item["entity_ref"]) for item in semantic["entities"]
        )
        refs.extend(
            _semantic_ref("claim", item["claim_ref"]) for item in semantic["claims"]
        )
        refs.extend(
            _semantic_ref("event", item["event_ref"]) for item in semantic["events"]
        )
        refs.extend(
            _semantic_ref("event_participation", item["participation_ref"])
            for item in semantic["participations"]
        )
        refs.extend(
            _semantic_ref("evidence_link", item["evidence_link_ref"])
            for item in semantic["evidence_links"]
        )
        refs.extend(
            _semantic_ref(
                "evidence_address",
                item["evidence_address_ref"],
                authority_context="Source and Evidence",
            )
            for item in semantic["evidence_links"]
        )
        refs.extend(
            _semantic_ref("conflict_set", item["conflict_set_ref"])
            for item in semantic["conflict_sets"]
        )
        refs.extend(
            subject_ref
            for policy_anchor in plan.policy_anchors
            for subject_ref in policy_anchor.subject_refs
        )
        return {item.key: item for item in refs}

    def _validate_plan(
        self,
        plan: PublicationAssemblyPlan,
        semantic_refs: dict[tuple[str, str, str, str], PublicationSemanticReference],
    ) -> dict[tuple[str, str, str, str], tuple[str, ...]]:
        if not plan.knowledge_object_id or not plan.knowledge_object_version:
            raise PublicationAssemblyError(
                "PUB-PLAN-001",
                "knowledge object identity and version are required",
            )
        anchor_ids = [item.policy_anchor_id for item in plan.policy_anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise PublicationAssemblyError(
                "PUB-POL-001",
                "policy anchor identifiers must be unique",
            )
        known_anchor_ids = set(anchor_ids)
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]] = {}
        for binding in plan.policy_bindings:
            if binding.semantic_ref.key not in semantic_refs:
                raise PublicationAssemblyError(
                    "PUB-POL-002",
                    "policy binding references unknown semantic subject "
                    f"{binding.semantic_ref.stable_id}",
                )
            if binding.semantic_ref.key in bindings:
                raise PublicationAssemblyError(
                    "PUB-POL-003",
                    "policy binding subject is duplicated: "
                    f"{binding.semantic_ref.stable_id}",
                )
            unknown = set(binding.policy_anchor_ids) - known_anchor_ids
            if not binding.policy_anchor_ids or unknown:
                raise PublicationAssemblyError(
                    "PUB-POL-004",
                    "policy binding must name existing anchors; unknown="
                    f"{sorted(unknown)}",
                )
            bindings[binding.semantic_ref.key] = binding.policy_anchor_ids

        for anchor in plan.policy_anchors:
            if not anchor.subject_refs:
                raise PublicationAssemblyError(
                    "PUB-POL-005",
                    f"policy anchor {anchor.policy_anchor_id} has no subject",
                )
            for subject_ref in anchor.subject_refs:
                if subject_ref.key not in semantic_refs:
                    raise PublicationAssemblyError(
                        "PUB-POL-006",
                        "policy anchor references unknown semantic subject "
                        f"{subject_ref.stable_id}",
                    )
        return bindings

    def _validate_representation(
        self,
        semantic: dict[str, Any],
        plan: PublicationAssemblyPlan,
        representation: PublicationRepresentation,
        semantic_refs: dict[tuple[str, str, str, str], PublicationSemanticReference],
    ) -> dict[str, dict[tuple[str, str, str, str], PublicationRepresentationItem]]:
        if representation.body_language != plan.language:
            raise PublicationAssemblyError(
                "PUB-REP-001",
                "representation language must match the assembly plan",
            )
        sections = representation.sections()
        anchors: list[str] = []
        mapping_ids: list[str] = []
        for section in sections:
            anchors.append(section.narrative_anchor)
            self._validate_representation_member(section, semantic_refs, mapping_ids)
            for item in section.items:
                anchors.append(item.narrative_anchor)
                self._validate_representation_member(item, semantic_refs, mapping_ids)
        if len(anchors) != len(set(anchors)):
            raise PublicationAssemblyError(
                "PUB-REP-002",
                "representation narrative anchors must be unique",
            )
        if len(mapping_ids) != len(set(mapping_ids)):
            raise PublicationAssemblyError(
                "PUB-REP-003",
                "cross-view mapping identifiers must be unique",
            )
        missing_policy_anchors = {
            item.narrative_anchor for item in plan.policy_anchors
        } - set(anchors)
        if missing_policy_anchors:
            raise PublicationAssemblyError(
                "PUB-REP-004",
                "policy narrative anchors are absent from representation: "
                f"{sorted(missing_policy_anchors)}",
            )

        indexes = {
            "claims": self._item_index(representation.claims),
            "events": self._item_index(representation.events),
            "evidence": self._item_index(representation.evidence),
            "conflicts": self._item_index(representation.conflicts),
        }
        expected = {
            "claims": {
                _semantic_ref("claim", item["claim_ref"]).key
                for item in semantic["claims"]
            },
            "events": {
                *(
                    _semantic_ref("event", item["event_ref"]).key
                    for item in semantic["events"]
                ),
                *(
                    _semantic_ref("event_participation", item["participation_ref"]).key
                    for item in semantic["participations"]
                ),
            },
            "evidence": {
                _semantic_ref("evidence_link", item["evidence_link_ref"]).key
                for item in semantic["evidence_links"]
            },
            "conflicts": {
                _semantic_ref("conflict_set", item["conflict_set_ref"]).key
                for item in semantic["conflict_sets"]
            },
        }
        for section_name, expected_refs in expected.items():
            actual_refs = set(indexes[section_name])
            if actual_refs != expected_refs:
                raise PublicationAssemblyError(
                    "PUB-REP-005",
                    f"{section_name} representation refs differ from semantic state; "
                    f"missing={sorted(expected_refs - actual_refs)}, "
                    f"extra={sorted(actual_refs - expected_refs)}",
                )
        return indexes

    def _validate_representation_member(
        self,
        member: PublicationRepresentationSection | PublicationRepresentationItem,
        semantic_refs: dict[tuple[str, str, str, str], PublicationSemanticReference],
        mapping_ids: list[str],
    ) -> None:
        semantic_ref = member.semantic_ref
        if semantic_ref is not None and semantic_ref.key not in semantic_refs:
            raise PublicationAssemblyError(
                "PUB-REP-006",
                f"representation references unknown subject {semantic_ref.stable_id}",
            )
        if member.material:
            if (
                semantic_ref is None
                or not member.mapping_id
                or not member.representation_role
            ):
                raise PublicationAssemblyError(
                    "PUB-REP-007",
                    "material representation requires semantic ref, mapping id, "
                    "and role",
                )
            mapping_ids.append(member.mapping_id)
        elif member.mapping_id is not None:
            raise PublicationAssemblyError(
                "PUB-REP-008",
                "non-material representation cannot define a mapping id",
            )

    def _item_index(
        self,
        section: PublicationRepresentationSection,
    ) -> dict[tuple[str, str, str, str], PublicationRepresentationItem]:
        result: dict[tuple[str, str, str, str], PublicationRepresentationItem] = {}
        for item in section.items:
            if item.semantic_ref.key in result:
                raise PublicationAssemblyError(
                    "PUB-REP-009",
                    "semantic reference appears more than once in section: "
                    f"{item.semantic_ref.stable_id}",
                )
            result[item.semantic_ref.key] = item
        return result

    def _policy_ids(
        self,
        semantic_ref: PublicationSemanticReference,
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]],
    ) -> list[str]:
        try:
            return list(bindings[semantic_ref.key])
        except KeyError as exc:
            raise PublicationAssemblyError(
                "PUB-POL-007",
                "no explicit policy binding for semantic subject "
                f"{semantic_ref.stable_id}",
            ) from exc

    def _claim_manifest(
        self,
        claim: dict[str, Any],
        semantic: dict[str, Any],
        plan: PublicationAssemblyPlan,
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]],
        representation_items: dict[
            tuple[str, str, str, str], PublicationRepresentationItem
        ],
    ) -> dict[str, Any]:
        claim_ref = _semantic_ref("claim", claim["claim_ref"])
        if claim["object_ref"]:
            object_payload = {
                "kind": "reference",
                "reference": _semantic_ref("entity", claim["object_ref"]).to_dict(),
                "value": None,
                "datatype": None,
                "language": None,
            }
        else:
            object_payload = {
                "kind": "literal",
                "reference": None,
                "value": claim["value"],
                "datatype": type(claim["value"]).__name__,
                "language": plan.language if isinstance(claim["value"], str) else None,
            }
        return {
            "claim_ref": claim_ref.to_dict(),
            "statement": {
                "subject_ref": _semantic_ref("entity", claim["subject_ref"]).to_dict(),
                "predicate_ref": claim["predicate_ref"],
                "object": object_payload,
            },
            "epistemic_status": claim["epistemic_status"],
            "time": [
                _time_value(
                    item["role"],
                    item["value"],
                    item["precision"],
                    item["modality"],
                )
                for item in claim.get("time", [])
            ],
            "evidence_link_ids": [
                link["evidence_link_ref"]
                for link in semantic["evidence_links"]
                if link["subject_type"] == "claim"
                and link["subject_ref"] == claim["claim_ref"]
            ],
            "authority_basis_refs": [],
            "policy_anchor_ids": self._policy_ids(claim_ref, bindings),
            "conflict_set_ids": [
                conflict["conflict_set_ref"]
                for conflict in semantic["conflict_sets"]
                if claim["claim_ref"] in conflict["claim_refs"]
            ],
            "narrative_anchor": representation_items[claim_ref.key].narrative_anchor,
        }

    def _event_manifest(
        self,
        event: dict[str, Any],
        semantic: dict[str, Any],
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]],
        representation_items: dict[
            tuple[str, str, str, str], PublicationRepresentationItem
        ],
    ) -> dict[str, Any]:
        event_ref = _semantic_ref("event", event["event_ref"])
        return {
            "event_ref": event_ref.to_dict(),
            "event_type_ref": event["event_type_ref"],
            "label": event["label"],
            "time": [
                _time_value(
                    "event_time",
                    event["event_time"],
                    event["time_precision"],
                    event["time_modality"],
                )
            ],
            "evidence_link_ids": [
                link["evidence_link_ref"]
                for link in semantic["evidence_links"]
                if link["subject_type"] == "event"
                and link["subject_ref"] == event["event_ref"]
            ],
            "policy_anchor_ids": self._policy_ids(event_ref, bindings),
            "narrative_anchor": representation_items[event_ref.key].narrative_anchor,
        }

    def _participation_manifest(
        self,
        participation: dict[str, Any],
        semantic: dict[str, Any],
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]],
        representation_items: dict[
            tuple[str, str, str, str], PublicationRepresentationItem
        ],
    ) -> dict[str, Any]:
        participation_ref = _semantic_ref(
            "event_participation", participation["participation_ref"]
        )
        return {
            "participation_ref": participation_ref.to_dict(),
            "event_ref": _semantic_ref("event", participation["event_ref"]).to_dict(),
            "entity_ref": _semantic_ref(
                "entity", participation["entity_ref"]
            ).to_dict(),
            "role": participation["role"],
            "time": [],
            "claim_refs": [],
            "evidence_link_ids": [
                link["evidence_link_ref"]
                for link in semantic["evidence_links"]
                if link["subject_type"] == "event_participation"
                and link["subject_ref"] == participation["participation_ref"]
            ],
            "policy_anchor_ids": self._policy_ids(participation_ref, bindings),
            "narrative_anchor": representation_items[
                participation_ref.key
            ].narrative_anchor,
        }

    def _evidence_link_manifest(
        self,
        link: dict[str, Any],
        plan: PublicationAssemblyPlan,
        bindings: dict[tuple[str, str, str, str], tuple[str, ...]],
        representation_items: dict[
            tuple[str, str, str, str], PublicationRepresentationItem
        ],
    ) -> dict[str, Any]:
        link_ref = _semantic_ref("evidence_link", link["evidence_link_ref"])
        evidence_ref = _semantic_ref(
            "evidence_address",
            link["evidence_address_ref"],
            authority_context="Source and Evidence",
        )
        return {
            "evidence_link_id": link["evidence_link_ref"],
            "subject_ref": _semantic_ref(
                link["subject_type"], link["subject_ref"]
            ).to_dict(),
            "evidence_address_ref": evidence_ref.to_dict(),
            "role": link["role"],
            "time_relevance": [],
            "interpretation_provenance": (
                plan.evidence_link_interpretation_provenance.to_dict()
            ),
            "policy_anchor_ids": self._policy_ids(link_ref, bindings),
            "narrative_anchor": representation_items[link_ref.key].narrative_anchor,
        }

    def _conflict_manifest(
        self,
        conflict: dict[str, Any],
        representation_items: dict[
            tuple[str, str, str, str], PublicationRepresentationItem
        ],
    ) -> dict[str, Any]:
        conflict_ref = _semantic_ref("conflict_set", conflict["conflict_set_ref"])
        return {
            "conflict_set_id": conflict["conflict_set_ref"],
            "claim_refs": [
                _semantic_ref("claim", ref).to_dict() for ref in conflict["claim_refs"]
            ],
            "conflict_dimensions": conflict["conflict_dimensions"],
            "preferred_claim_ref": (
                _semantic_ref("claim", conflict["preferred_claim_ref"]).to_dict()
                if conflict["preferred_claim_ref"] is not None
                else None
            ),
            "preference_context": conflict["preference_context"],
            "resolution_record_ref": None,
            "rationale": conflict["rationale"],
            "narrative_anchor": representation_items[conflict_ref.key].narrative_anchor,
        }

    def _representation_members(
        self,
        representation: PublicationRepresentation,
    ) -> Iterable[PublicationRepresentationSection | PublicationRepresentationItem]:
        for section in representation.sections():
            yield section
            yield from section.items

    def _cross_view_mappings(
        self,
        representation: PublicationRepresentation,
    ) -> list[dict[str, Any]]:
        return [
            {
                "mapping_id": member.mapping_id,
                "semantic_ref": member.semantic_ref.to_dict(),
                "narrative_anchor": member.narrative_anchor,
                "representation_role": member.representation_role,
                "material": True,
            }
            for member in self._representation_members(representation)
            if member.material
            and member.mapping_id is not None
            and member.semantic_ref is not None
            and member.representation_role is not None
        ]

    def _render_body(
        self,
        plan: PublicationAssemblyPlan,
        representation: PublicationRepresentation,
    ) -> str:
        lines = [f"# {plan.title}", ""]
        for section in representation.sections():
            lines.extend(
                [
                    f'<a id="{section.narrative_anchor}"></a>',
                    f"## {section.heading}",
                    "",
                ]
            )
            if section.rendered_text:
                lines.extend([section.rendered_text, ""])
            for item in section.items:
                lines.extend(
                    [
                        f'<a id="{item.narrative_anchor}"></a>',
                        f"### {item.heading}",
                        "",
                        item.rendered_text,
                        "",
                    ]
                )
        return "\n".join(lines)

    def _validate_cross_view(
        self,
        manifest: dict[str, Any],
        representation: PublicationRepresentation,
        body: str,
    ) -> None:
        representation_anchors = {
            member.narrative_anchor
            for member in self._representation_members(representation)
        }
        mapping_anchors = {
            mapping["narrative_anchor"] for mapping in manifest["cross_view_mappings"]
        }
        if not mapping_anchors.issubset(representation_anchors):
            raise PublicationAssemblyError(
                "PUB-XVIEW-001",
                "cross-view mappings contain an unrendered anchor",
            )
        invalid = sorted(
            anchor
            for anchor in representation_anchors
            if body.count(f'id="{anchor}"') != 1
        )
        if invalid:
            raise PublicationAssemblyError(
                "PUB-XVIEW-002",
                f"representation anchors must occur exactly once: {invalid}",
            )


def load_publication_manifest(path: Path) -> dict[str, Any]:
    return load_publication_unit(path).manifest
