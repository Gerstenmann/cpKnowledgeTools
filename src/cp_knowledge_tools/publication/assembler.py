# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _ref(subject_type: str, stable_id: str, authority_context: str = "Semantic Core") -> dict[str, Any]:
    return {
        "subject_type": subject_type,
        "stable_id": stable_id,
        "version": "0.1",
        "authority_context": authority_context,
    }


def _time_value(role: str, value: str | None, precision: str, modality: str) -> dict[str, Any]:
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
    return {
        "role": role,
        "value_kind": "instant",
        "precision": precision,
        "modality": modality,
        "start": value,
        "end": None,
        "timezone": None,
        "approximate": False,
        "uncertainty": None,
        "source_ref": None,
    }


class PublicationUnitAssembler:
    def assemble(
        self,
        semantic: dict[str, Any],
        evidence: dict[str, Any],
        *,
        knowledge_object_id: str,
        title: str,
        output_path: Path,
        pilot_entity_rule_keys: list[str],
        restricted_evidence_rule_key: str,
        policy_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        policy_refs = list(policy_refs or [])
        entity_by_key = {item["rule_key"]: item for item in semantic["entities"]}
        evidence_rule_by_ref = {
            item.evidence_address_ref: rule_key for rule_key, item in evidence.items()
        }

        claim_manifest = []
        for claim in semantic["claims"]:
            if claim["object_ref"]:
                object_payload = {
                    "kind": "reference",
                    "reference": _ref("entity", claim["object_ref"]),
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
                    "language": "en" if isinstance(claim["value"], str) else None,
                }
            claim_manifest.append(
                {
                    "claim_ref": _ref("claim", claim["claim_ref"]),
                    "statement": {
                        "subject_ref": _ref("entity", claim["subject_ref"]),
                        "predicate_ref": claim["predicate_ref"],
                        "object": object_payload,
                    },
                    "epistemic_status": claim["epistemic_status"],
                    "time": [],
                    "evidence_link_ids": [
                        link["evidence_link_ref"]
                        for link in semantic["evidence_links"]
                        if link["claim_ref"] == claim["claim_ref"]
                    ],
                    "authority_basis_refs": [],
                    "policy_anchor_ids": ["PA-KO"],
                    "conflict_set_ids": [
                        conflict["conflict_set_ref"]
                        for conflict in semantic["conflict_sets"]
                        if claim["claim_ref"] in conflict["claim_refs"]
                    ],
                    "narrative_anchor": f"claim-{claim['rule_key']}",
                }
            )

        event_manifest = []
        for event in semantic["events"]:
            event_manifest.append(
                {
                    "event_ref": _ref("event", event["event_ref"]),
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
                    "evidence_link_ids": [],
                    "policy_anchor_ids": ["PA-KO"],
                    "narrative_anchor": f"event-{event['rule_key']}",
                }
            )

        participation_manifest = []
        for participation in semantic["participations"]:
            participation_manifest.append(
                {
                    "participation_ref": _ref(
                        "event_participation", participation["participation_ref"]
                    ),
                    "event_ref": _ref("event", participation["event_ref"]),
                    "entity_ref": _ref("entity", participation["entity_ref"]),
                    "role": participation["role"],
                    "time": [],
                    "claim_refs": [],
                    "evidence_link_ids": [],
                    "policy_anchor_ids": ["PA-KO"],
                    "narrative_anchor": f"participation-{participation['rule_key']}",
                }
            )

        evidence_link_manifest = []
        for link in semantic["evidence_links"]:
            evidence_rule_key = evidence_rule_by_ref[link["evidence_address_ref"]]
            evidence_link_manifest.append(
                {
                    "evidence_link_id": link["evidence_link_ref"],
                    "subject_ref": _ref("claim", link["claim_ref"]),
                    "evidence_address_ref": _ref(
                        "evidence_address",
                        link["evidence_address_ref"],
                        "Source and Evidence",
                    ),
                    "role": link["role"],
                    "time_relevance": [],
                    "interpretation_provenance": {
                        "producer_ref": _ref(
                            "producer", "CPKT-RULE-INTERPRETER", "Platform and Integration"
                        ),
                        "method": "deterministic_reference_rules",
                        "produced_at": "2026-08-08T00:00:00+02:00",
                    },
                    "policy_anchor_ids": [
                        "PA-RESTRICTED-EVIDENCE"
                        if evidence_rule_key == restricted_evidence_rule_key
                        else "PA-KO"
                    ],
                    "narrative_anchor": f"evidence-{link['rule_key']}",
                }
            )

        conflict_manifest = []
        for conflict in semantic["conflict_sets"]:
            conflict_manifest.append(
                {
                    "conflict_set_id": conflict["conflict_set_ref"],
                    "claim_refs": [_ref("claim", ref) for ref in conflict["claim_refs"]],
                    "conflict_dimensions": conflict["conflict_dimensions"],
                    "preferred_claim_ref": _ref("claim", conflict["preferred_claim_ref"]),
                    "preference_context": conflict["preference_context"],
                    "resolution_record_ref": None,
                    "rationale": conflict["rationale"],
                    "narrative_anchor": f"conflict-{conflict['rule_key']}",
                }
            )

        ko_ref = _ref("knowledge_object", knowledge_object_id)
        policy_anchors = [
            {
                "policy_anchor_id": "PA-KO",
                "subject_refs": [ko_ref],
                "policy_refs": policy_refs,
                "policy_decision_refs": [],
                "dimensions": [
                    "discoverability",
                    "read_access",
                    "evidence_resolution",
                    "quotation",
                    "transformation",
                    "external_processing",
                    "indexing",
                    "memory_eligibility",
                    "export",
                    "retention",
                ],
                "narrative_anchor": "ko-policy",
            },
            {
                "policy_anchor_id": "PA-RESTRICTED-EVIDENCE",
                "subject_refs": [
                    _ref(
                        "evidence_address",
                        evidence[restricted_evidence_rule_key].evidence_address_ref,
                        "Source and Evidence",
                    )
                ],
                "policy_refs": policy_refs,
                "policy_decision_refs": [],
                "dimensions": ["evidence_resolution", "quotation", "export"],
                "narrative_anchor": "restricted-evidence-policy",
            },
        ]

        cross_view = [
            {
                "mapping_id": "CVM-SUMMARY",
                "semantic_ref": ko_ref,
                "narrative_anchor": "ko-summary",
                "representation_role": "summary",
                "material": True,
            },
            {
                "mapping_id": "CVM-APPLICABILITY",
                "semantic_ref": ko_ref,
                "narrative_anchor": "ko-applicability",
                "representation_role": "applicability_note",
                "material": True,
            },
            {
                "mapping_id": "CVM-POLICY",
                "semantic_ref": ko_ref,
                "narrative_anchor": "ko-policy",
                "representation_role": "policy_note",
                "material": True,
            },
        ]
        for claim in semantic["claims"]:
            cross_view.append(
                {
                    "mapping_id": f"CVM-CLAIM-{claim['rule_key']}",
                    "semantic_ref": _ref("claim", claim["claim_ref"]),
                    "narrative_anchor": f"claim-{claim['rule_key']}",
                    "representation_role": "primary_statement",
                    "material": True,
                }
            )
        for event in semantic["events"]:
            cross_view.append(
                {
                    "mapping_id": f"CVM-EVENT-{event['rule_key']}",
                    "semantic_ref": _ref("event", event["event_ref"]),
                    "narrative_anchor": f"event-{event['rule_key']}",
                    "representation_role": "event_note",
                    "material": True,
                }
            )
        for participation in semantic["participations"]:
            cross_view.append(
                {
                    "mapping_id": f"CVM-PART-{participation['rule_key']}",
                    "semantic_ref": _ref(
                        "event_participation", participation["participation_ref"]
                    ),
                    "narrative_anchor": f"participation-{participation['rule_key']}",
                    "representation_role": "event_note",
                    "material": True,
                }
            )
        for conflict in semantic["conflict_sets"]:
            cross_view.append(
                {
                    "mapping_id": f"CVM-CONFLICT-{conflict['rule_key']}",
                    "semantic_ref": _ref("conflict_set", conflict["conflict_set_ref"]),
                    "narrative_anchor": f"conflict-{conflict['rule_key']}",
                    "representation_role": "conflict_note",
                    "material": True,
                }
            )

        applicability_entities = [
            _ref("entity", entity_by_key[key]["entity_ref"])
            for key in pilot_entity_rule_keys
        ]

        manifest = {
            "document_type": "knowledge_object_publication_unit",
            "schema_ref": "CPKS-SPEC-KM-PU@0.1",
            "template_ref": "CPKS-TPL-KM-PU@0.1",
            "semantic_model_ref": "CPKS-SPEC-KM@0.20",
            "vocabulary_set_ref": "CPKS-SPEC-KM-VOC@0.1",
            "knowledge_object_id": knowledge_object_id,
            "knowledge_object_version": "0.1",
            "title": title,
            "language": "en",
            "canonical_path": None,
            "primary_kind": "event_summary",
            "knowledge_functions": ["descriptive", "explanatory"],
            "applicability": {
                "domain_refs": [],
                "entity_refs": applicability_entities,
                "organization_refs": [],
                "product_refs": [],
                "purposes": ["source_to_knowledge_core_mvp_test"],
                "valid_time": [],
            },
            "profile_refs": [],
            "claims": claim_manifest,
            "events": event_manifest,
            "event_participations": participation_manifest,
            "evidence_links": evidence_link_manifest,
            "structural_relationships": [],
            "conflict_sets": conflict_manifest,
            "policy_anchors": policy_anchors,
            "cross_view_mappings": cross_view,
            "human_readable": {
                "body_language": "en",
                "summary_anchor": "ko-summary",
                "details_anchor": "ko-details",
                "claims_anchor": "ko-claims",
                "events_anchor": "ko-events",
                "evidence_anchor": "ko-evidence",
                "conflicts_anchor": "ko-conflicts",
                "applicability_anchor": "ko-applicability",
                "policy_anchor": "ko-policy",
                "publication_anchor": "ko-publication",
            },
            "review_record_refs": [],
            "policy_decision_refs": [],
            "publication": {
                "publication_state": "unpublished",
                "publication_record_ref": None,
                "published_at": None,
                "publisher_ref": None,
                "predecessor_publication_ref": None,
            },
            "integrity": {
                "content_hash": None,
                "cross_view_validation": {
                    "status": "pending",
                    "report_ref": None,
                },
            },
        }

        body = self._body(semantic)
        status = self._validate_cross_view(manifest, body)
        manifest["integrity"]["cross_view_validation"] = {
            "status": status,
            "report_ref": "CPKT-MVP-XVIEW-001" if status == "pass" else None,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_text = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        output_path.write_text(f"---\n{yaml_text}---\n\n{body}", encoding="utf-8")
        return manifest

    def _body(self, semantic: dict[str, Any]) -> str:
        lines = [
            "# Minecraft Education esports pilot – synthetic golden case",
            "",
            '<a id="ko-summary"></a>',
            "## Summary",
            "",
            "The school confirmed a limited after-school Minecraft Education esports pilot. Earlier proposal and open states remain evidentially traceable.",
            "",
            '<a id="ko-applicability"></a>',
            "## Applicability",
            "",
            "Synthetic, non-sensitive Source-to-Knowledge MVP reference case.",
            "",
            '<a id="ko-details"></a>',
            "## Context",
            "",
            "The dossier preserves proposal, response, confirmed pilot status, temporal progression, uncertainty, and policy boundaries.",
            "",
            '<a id="ko-claims"></a>',
            "## Claims",
            "",
        ]
        for claim in semantic["claims"]:
            lines += [
                f'<a id="claim-{claim["rule_key"]}"></a>',
                f'### {claim["rule_key"]}',
                "",
                self._claim_sentence(claim),
                "",
            ]

        lines += ['<a id="ko-events"></a>', "## Events and participations", ""]
        for event in semantic["events"]:
            lines += [
                f'<a id="event-{event["rule_key"]}"></a>',
                f'### {event["label"]}',
                "",
                f"Event state: {event['time_modality']}; time: {event['event_time'] or 'unknown'}.",
                "",
            ]
        for participation in semantic["participations"]:
            lines += [
                f'<a id="participation-{participation["rule_key"]}"></a>',
                f'### Participation {participation["rule_key"]}',
                "",
                f"Role: {participation['role']}.",
                "",
            ]

        lines += ['<a id="ko-evidence"></a>', "## Evidence and provenance", ""]
        for link in semantic["evidence_links"]:
            lines += [
                f'<a id="evidence-{link["rule_key"]}"></a>',
                f'### {link["rule_key"]}',
                "",
                f"Evidence role: `{link['role']}`; address remains version-bound and resolvable.",
                "",
            ]

        lines += ['<a id="ko-conflicts"></a>', "## Conflicts and uncertainty", ""]
        for conflict in semantic["conflict_sets"]:
            lines += [
                f'<a id="conflict-{conflict["rule_key"]}"></a>',
                f'### {conflict["rule_key"]}',
                "",
                f"Preferred current state is context-bound; prior alternatives remain addressable. {conflict['rationale']}",
                "",
            ]

        lines += [
            '<a id="ko-policy"></a>',
            "## Policy and use",
            "",
            "The abstract budget claim is readable for the test consumer. Resolution of the restricted exact-budget evidence remains denied.",
            "",
            '<a id="restricted-evidence-policy"></a>',
            "### Restricted evidence policy",
            "",
            "Restricted source evidence is referenced but its exact monetary amount is intentionally not reproduced here.",
            "",
            '<a id="ko-publication"></a>',
            "## Review and publication",
            "",
            "Publication state: `unpublished`. This MVP does not perform canonical Vault publication.",
            "",
        ]
        return "\n".join(lines)

    def _claim_sentence(self, claim: dict[str, Any]) -> str:
        key = claim["rule_key"]
        value = claim["value"]
        sentences = {
            "workshop_12sep": "The concept workshop is planned for 12 September 2024 and is confirmed as the current plan.",
            "training_19sep": "The initial proposal planned team training for 19 September 2024; this historical plan remains preserved.",
            "training_26sep": "The confirmed pilot plan schedules team training for 26 September 2024.",
            "capacity_about20": "The initial proposal estimated approximately 20 interested students.",
            "capacity_max16": "The confirmed pilot capacity is limited to 16 students.",
            "adviser_not_selected": "At the school-response stage, the adviser had not yet been selected.",
            "adviser_james": "James Stone is the confirmed school adviser for the pilot.",
            "scope_open": "The initial academic versus extracurricular scope remained open in the school response.",
            "scope_afterschool": "The confirmed current pilot scope is after-school only.",
            "academic_deferred": "Classroom integration is deferred until after pilot evaluation.",
            "competition_later_possible": "External competition remains a possible later phase.",
            "competition_not_approved": "External competition is not approved at the current pilot stage.",
            "previous_success_reported": "The school reported previous Minecraft use as successful; this remains a reported statement rather than independent confirmation.",
            "budget_approved": "The pilot has an approved internal budget.",
        }
        return sentences.get(key, f"{claim['predicate_ref']}: {value!r}")

    def _validate_cross_view(self, manifest: dict[str, Any], body: str) -> str:
        anchors = {mapping["narrative_anchor"] for mapping in manifest["cross_view_mappings"]}
        anchors.add("restricted-evidence-policy")
        for anchor in anchors:
            if body.count(f'id="{anchor}"') != 1:
                return "fail"
        return "pass"


def load_publication_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("Publication Unit does not start with YAML frontmatter")
    _, remainder = text.split("---\n", 1)
    yaml_text, _body = remainder.split("---\n", 1)
    return yaml.safe_load(yaml_text)
