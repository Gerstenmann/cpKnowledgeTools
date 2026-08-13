from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cp_knowledge_tools.publication import (
    PublicationApplicability,
    PublicationAssemblyError,
    PublicationAssemblyPlan,
    PublicationInterpretationProvenance,
    PublicationPolicyAnchor,
    PublicationPolicyBinding,
    PublicationRepresentation,
    PublicationRepresentationItem,
    PublicationRepresentationSection,
    PublicationSemanticReference,
    PublicationUnitAssembler,
    load_publication_unit,
    parse_publication_unit,
    render_publication_unit,
)


def _ref(
    subject_type: str,
    stable_id: str,
    *,
    version: str = "0.1",
    authority_context: str = "Semantic Core",
) -> PublicationSemanticReference:
    return PublicationSemanticReference(
        subject_type=subject_type,
        stable_id=stable_id,
        version=version,
        authority_context=authority_context,
    )


def _semantic_state() -> dict:
    return {
        "entities": [
            {
                "entity_ref": "ENT-ROBOTICS-DEPLOYMENT",
                "label": "Robotics deployment",
                "class": "deployment",
            },
            {
                "entity_ref": "ENT-OPERATIONS-TEAM",
                "label": "Operations team",
                "class": "organization",
            },
        ],
        "claims": [
            {
                "claim_ref": "CLM-DEPLOYMENT-PLANNED",
                "subject_ref": "ENT-ROBOTICS-DEPLOYMENT",
                "predicate_ref": "example.deployment.state",
                "value": "scheduled",
                "object_ref": None,
                "epistemic_status": "reported",
                "time": [
                    {
                        "role": "source_time",
                        "value": "2026-07-01T09:30:00+02:00",
                        "precision": "minute",
                        "modality": "actual",
                    }
                ],
            },
            {
                "claim_ref": "CLM-DEPLOYMENT-CURRENT",
                "subject_ref": "ENT-ROBOTICS-DEPLOYMENT",
                "predicate_ref": "example.deployment.state",
                "value": "completed",
                "object_ref": None,
                "epistemic_status": "confirmed",
                "time": [],
            },
        ],
        "evidence_links": [
            {
                "evidence_link_ref": "EL-DEPLOYMENT-PLANNED",
                "subject_type": "claim",
                "subject_ref": "CLM-DEPLOYMENT-PLANNED",
                "claim_ref": "CLM-DEPLOYMENT-PLANNED",
                "evidence_address_ref": "EA-DEPLOYMENT-PLANNED",
                "role": "reports",
            },
            {
                "evidence_link_ref": "EL-DEPLOYMENT-CURRENT",
                "subject_type": "claim",
                "subject_ref": "CLM-DEPLOYMENT-CURRENT",
                "claim_ref": "CLM-DEPLOYMENT-CURRENT",
                "evidence_address_ref": "EA-DEPLOYMENT-CURRENT",
                "role": "supports",
            },
            {
                "evidence_link_ref": "EL-DEPLOYMENT-EVENT",
                "subject_type": "event",
                "subject_ref": "EVT-ROBOTICS-DEPLOYMENT",
                "claim_ref": None,
                "evidence_address_ref": "EA-DEPLOYMENT-EVENT",
                "role": "supports",
            },
            {
                "evidence_link_ref": "EL-DEPLOYMENT-PARTICIPATION",
                "subject_type": "event_participation",
                "subject_ref": "PART-OPERATIONS-DEPLOYMENT",
                "claim_ref": None,
                "evidence_address_ref": "EA-DEPLOYMENT-PARTICIPATION",
                "role": "supports",
            },
        ],
        "events": [
            {
                "event_ref": "EVT-ROBOTICS-DEPLOYMENT",
                "event_type_ref": "example.event.deployment",
                "label": "Robotics deployment completed",
                "event_time": "2026-07-15",
                "time_precision": "day",
                "time_modality": "actual",
            }
        ],
        "participations": [
            {
                "participation_ref": "PART-OPERATIONS-DEPLOYMENT",
                "event_ref": "EVT-ROBOTICS-DEPLOYMENT",
                "entity_ref": "ENT-OPERATIONS-TEAM",
                "role": "operator",
            }
        ],
        "conflict_sets": [
            {
                "conflict_set_ref": "CF-DEPLOYMENT-STATE",
                "claim_refs": [
                    "CLM-DEPLOYMENT-PLANNED",
                    "CLM-DEPLOYMENT-CURRENT",
                ],
                "conflict_dimensions": ["temporal"],
                "preferred_claim_ref": "CLM-DEPLOYMENT-CURRENT",
                "preference_context": "current_operational_state",
                "rationale": "The completed state supersedes the earlier schedule.",
            }
        ],
    }


def _inputs(
    *,
    version: str = "0.1",
    summary_text: str = "The robotics deployment is operational.",
) -> tuple[PublicationAssemblyPlan, PublicationRepresentation]:
    ko_ref = _ref("knowledge_object", "KO-ROBOTICS-DEPLOYMENT", version=version)
    current_evidence_ref = _ref(
        "evidence_address",
        "EA-DEPLOYMENT-CURRENT",
        authority_context="Source and Evidence",
    )
    policy_anchors = (
        PublicationPolicyAnchor(
            policy_anchor_id="PA-DELIVERY",
            subject_refs=(ko_ref,),
            policy_refs=("POLICY-DELIVERY@1.0",),
            dimensions=("read_access", "evidence_resolution"),
            narrative_anchor="delivery-policy",
        ),
        PublicationPolicyAnchor(
            policy_anchor_id="PA-AUDIT-EVIDENCE",
            subject_refs=(current_evidence_ref,),
            policy_refs=("POLICY-DELIVERY@1.0",),
            dimensions=("evidence_resolution",),
            narrative_anchor="audit-evidence-policy",
        ),
    )
    policy_bindings = tuple(
        [
            PublicationPolicyBinding(
                semantic_ref=_ref("claim", "CLM-DEPLOYMENT-PLANNED"),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref("claim", "CLM-DEPLOYMENT-CURRENT"),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref("event", "EVT-ROBOTICS-DEPLOYMENT"),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref(
                    "event_participation", "PART-OPERATIONS-DEPLOYMENT"
                ),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref("evidence_link", "EL-DEPLOYMENT-PLANNED"),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref("evidence_link", "EL-DEPLOYMENT-CURRENT"),
                policy_anchor_ids=("PA-AUDIT-EVIDENCE",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref("evidence_link", "EL-DEPLOYMENT-EVENT"),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
            PublicationPolicyBinding(
                semantic_ref=_ref(
                    "evidence_link", "EL-DEPLOYMENT-PARTICIPATION"
                ),
                policy_anchor_ids=("PA-DELIVERY",),
            ),
        ]
    )
    plan = PublicationAssemblyPlan(
        knowledge_object_id=ko_ref.stable_id,
        knowledge_object_version=version,
        title="Robotics deployment readiness",
        language="en",
        primary_kind="operational_summary",
        knowledge_functions=("descriptive",),
        applicability=PublicationApplicability(
            entity_refs=(_ref("entity", "ENT-ROBOTICS-DEPLOYMENT"),),
            purposes=("operational_readiness",),
        ),
        profile_refs=("cpks.profile.core-knowledge@1.1",),
        policy_anchors=policy_anchors,
        policy_bindings=policy_bindings,
        evidence_link_interpretation_provenance=(
            PublicationInterpretationProvenance(
                producer_ref=_ref(
                    "producer",
                    "RULE-INTERPRETER",
                    authority_context="Platform and Integration",
                ),
                method="deterministic_rules",
                produced_at="2026-07-16T08:00:00Z",
            )
        ),
    )
    representation = PublicationRepresentation(
        summary=PublicationRepresentationSection(
            narrative_anchor="deployment-summary",
            heading="Summary",
            rendered_text=summary_text,
            semantic_ref=ko_ref,
            representation_role="summary",
            mapping_id="CVM-DEPLOYMENT-SUMMARY",
            material=True,
        ),
        applicability=PublicationRepresentationSection(
            narrative_anchor="deployment-applicability",
            heading="Applicability",
            rendered_text="Applies to the operational deployment.",
            semantic_ref=ko_ref,
            representation_role="applicability_note",
            mapping_id="CVM-DEPLOYMENT-APPLICABILITY",
            material=True,
        ),
        details=PublicationRepresentationSection(
            narrative_anchor="deployment-details",
            heading="Context",
            rendered_text="The earlier schedule remains traceable.",
        ),
        claims=PublicationRepresentationSection(
            narrative_anchor="deployment-claims",
            heading="Claims",
            items=(
                PublicationRepresentationItem(
                    semantic_ref=_ref("claim", "CLM-DEPLOYMENT-PLANNED"),
                    narrative_anchor="claim-deployment-planned",
                    representation_role="historical_statement",
                    rendered_text="The deployment was scheduled.",
                    heading="Earlier state",
                    mapping_id="CVM-CLAIM-DEPLOYMENT-PLANNED",
                    material=True,
                ),
                PublicationRepresentationItem(
                    semantic_ref=_ref("claim", "CLM-DEPLOYMENT-CURRENT"),
                    narrative_anchor="claim-deployment-current",
                    representation_role="primary_statement",
                    rendered_text="The deployment is complete.",
                    heading="Current state",
                    mapping_id="CVM-CLAIM-DEPLOYMENT-CURRENT",
                    material=True,
                ),
            ),
        ),
        events=PublicationRepresentationSection(
            narrative_anchor="deployment-events",
            heading="Events and participations",
            items=(
                PublicationRepresentationItem(
                    semantic_ref=_ref("event", "EVT-ROBOTICS-DEPLOYMENT"),
                    narrative_anchor="event-deployment",
                    representation_role="event_note",
                    rendered_text="The deployment completed on 15 July 2026.",
                    heading="Deployment event",
                    mapping_id="CVM-EVENT-DEPLOYMENT",
                    material=True,
                ),
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "event_participation", "PART-OPERATIONS-DEPLOYMENT"
                    ),
                    narrative_anchor="participation-operations",
                    representation_role="event_note",
                    rendered_text="The operations team served as operator.",
                    heading="Operations participation",
                    mapping_id="CVM-PART-OPERATIONS",
                    material=True,
                ),
            ),
        ),
        evidence=PublicationRepresentationSection(
            narrative_anchor="deployment-evidence",
            heading="Evidence and provenance",
            items=(
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "evidence_link", "EL-DEPLOYMENT-PLANNED"
                    ),
                    narrative_anchor="evidence-deployment-planned",
                    representation_role="evidence_note",
                    rendered_text="The scheduling record remains addressable.",
                    heading="Scheduling evidence",
                ),
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "evidence_link", "EL-DEPLOYMENT-CURRENT"
                    ),
                    narrative_anchor="evidence-deployment-current",
                    representation_role="evidence_note",
                    rendered_text="The completion record remains addressable.",
                    heading="Completion evidence",
                ),
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "evidence_link", "EL-DEPLOYMENT-EVENT"
                    ),
                    narrative_anchor="evidence-deployment-event",
                    representation_role="evidence_note",
                    rendered_text="The event record remains addressable.",
                    heading="Event evidence",
                ),
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "evidence_link", "EL-DEPLOYMENT-PARTICIPATION"
                    ),
                    narrative_anchor="evidence-deployment-participation",
                    representation_role="evidence_note",
                    rendered_text="The participation record remains addressable.",
                    heading="Participation evidence",
                ),
            ),
        ),
        conflicts=PublicationRepresentationSection(
            narrative_anchor="deployment-conflicts",
            heading="Conflicts and uncertainty",
            items=(
                PublicationRepresentationItem(
                    semantic_ref=_ref(
                        "conflict_set", "CF-DEPLOYMENT-STATE"
                    ),
                    narrative_anchor="conflict-deployment-state",
                    representation_role="conflict_note",
                    rendered_text="The completed state is preferred for current use.",
                    heading="Deployment state progression",
                    mapping_id="CVM-CONFLICT-DEPLOYMENT",
                    material=True,
                ),
            ),
        ),
        policy=PublicationRepresentationSection(
            narrative_anchor="delivery-policy",
            heading="Policy and use",
            rendered_text="Knowledge delivery and evidence resolution are separate.",
            semantic_ref=ko_ref,
            representation_role="policy_note",
            mapping_id="CVM-DELIVERY-POLICY",
            material=True,
            items=(
                PublicationRepresentationItem(
                    semantic_ref=current_evidence_ref,
                    narrative_anchor="audit-evidence-policy",
                    representation_role="policy_note",
                    rendered_text="Completion evidence follows its own policy anchor.",
                    heading="Evidence policy",
                ),
            ),
        ),
        publication=PublicationRepresentationSection(
            narrative_anchor="deployment-publication",
            heading="Review and publication",
            rendered_text="Publication state: `unpublished`.",
        ),
        body_language="en",
    )
    return plan, representation


def test_generic_assembly_uses_explicit_unrelated_domain_inputs(
    tmp_path: Path,
) -> None:
    plan, representation = _inputs()
    path = tmp_path / "robotics-deployment.md"

    manifest = PublicationUnitAssembler().assemble(
        _semantic_state(),
        plan=plan,
        representation=representation,
        output_path=path,
    )
    document = load_publication_unit(path)

    assert document.manifest == manifest
    assert manifest["title"] == "Robotics deployment readiness"
    assert manifest["applicability"] == plan.applicability.to_dict()
    assert manifest["publication"]["publication_state"] == "unpublished"
    assert manifest["profile_refs"] == ["cpks.profile.core-knowledge@1.1"]
    assert manifest["evidence_links"][1]["policy_anchor_ids"] == [
        "PA-AUDIT-EVIDENCE"
    ]
    assert manifest["claims"][0]["time"][0]["start"].endswith("+02:00")
    assert manifest["claims"][0]["time"][0]["timezone"] == "+02:00"
    assert manifest["events"][0]["evidence_link_ids"] == [
        "EL-DEPLOYMENT-EVENT"
    ]
    assert manifest["event_participations"][0]["evidence_link_ids"] == [
        "EL-DEPLOYMENT-PARTICIPATION"
    ]
    assert {
        item["subject_ref"]["subject_type"] for item in manifest["evidence_links"]
    } == {"claim", "event", "event_participation"}
    assert manifest["integrity"]["cross_view_validation"]["status"] == "pass"
    assert "The robotics deployment is operational." in document.markdown_body
    assert "CLM-DEPLOYMENT-CURRENT" in {
        item["semantic_ref"]["stable_id"]
        for item in manifest["cross_view_mappings"]
    }
    assert parse_publication_unit(render_publication_unit(document)) == document


def test_representation_change_requires_separate_knowledge_object_version(
    tmp_path: Path,
) -> None:
    assembler = PublicationUnitAssembler()
    plan_a, representation_a = _inputs(version="0.1", summary_text="Release A")
    plan_b, representation_b = _inputs(version="0.2", summary_text="Release B")

    manifest_a = assembler.assemble(
        _semantic_state(),
        plan=plan_a,
        representation=representation_a,
        output_path=tmp_path / "release-a.md",
    )
    manifest_b = assembler.assemble(
        _semantic_state(),
        plan=plan_b,
        representation=representation_b,
        output_path=tmp_path / "release-b.md",
    )

    assert manifest_a["knowledge_object_id"] == manifest_b["knowledge_object_id"]
    assert manifest_a["knowledge_object_version"] == "0.1"
    assert manifest_b["knowledge_object_version"] == "0.2"
    assert manifest_a["claims"][0]["claim_ref"] == manifest_b["claims"][0][
        "claim_ref"
    ]
    assert (tmp_path / "release-a.md").read_text() != (
        tmp_path / "release-b.md"
    ).read_text()


def test_missing_policy_binding_fails_with_generic_diagnostic(
    tmp_path: Path,
) -> None:
    plan, representation = _inputs()
    plan = replace(plan, policy_bindings=plan.policy_bindings[:-1])

    with pytest.raises(PublicationAssemblyError, match="PUB-POL-007") as error:
        PublicationUnitAssembler().assemble(
            _semantic_state(),
            plan=plan,
            representation=representation,
            output_path=tmp_path / "invalid.md",
        )

    assert "EL-DEPLOYMENT-PARTICIPATION" in error.value.detail


def test_generic_core_sources_contain_no_reference_scenario_vocabulary() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    production_roots = (
        repository_root / "src/cp_knowledge_tools/publication",
        repository_root / "src/cp_knowledge_tools/validation/core",
        repository_root / "src/cp_knowledge_tools/derived",
    )
    forbidden = (
        "Minecraft",
        "minecraft",
        "esports",
        "workshop_12sep",
        "training_19sep",
        "training_26sep",
        "capacity_about20",
        "capacity_max16",
        "adviser_not_selected",
        "adviser_james",
        "scope_open",
        "scope_afterschool",
        "academic_deferred",
        "competition_later_possible",
        "competition_not_approved",
        "previous_success_reported",
        "budget_approved",
        "budget_exact",
        "pilot_entity_rule_keys",
        "restricted_evidence_rule_key",
    )

    offenders = []
    for root in production_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.relative_to(repository_root)}: {literal}"
                for literal in forbidden
                if literal in text
            )

    assert offenders == []
