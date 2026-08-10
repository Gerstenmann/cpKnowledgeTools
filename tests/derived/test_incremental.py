from cp_knowledge_tools.derived.governance_state import (
    ArtifactRecord,
    DerivedGovernanceState,
    ReferenceEdge,
)
from cp_knowledge_tools.derived.incremental import plan_incremental_validation


def _record(artifact_id: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=artifact_id,
        document_type="specification",
        version="1.0",
        status="active",
        evidence_class="active_constraint",
        title=artifact_id,
        path=f"{artifact_id}.md",
        canonical_path=f"{artifact_id}.md",
    )


def test_incremental_plan_validates_only_stable_material_dependencies():
    target = "TARGET-SPEC"
    state = DerivedGovernanceState(
        active={
            target: _record(target),
            "CONSUMER": _record("CONSUMER"),
            "EVIDENCE": _record("EVIDENCE"),
        },
        all_records=[],
        aliases={},
        reverse_dependencies={
            target: [
                ReferenceEdge("CONSUMER", "1.0", "depends_on", target, target, None),
                ReferenceEdge(
                    "EVIDENCE",
                    "1.0",
                    "validated_against",
                    f"{target}@1.0",
                    target,
                    "1.0",
                ),
            ]
        },
    )
    plan = plan_incremental_validation(state, target)
    assert plan.validate_artifact_ids == ("CONSUMER",)
    assert plan.no_action_artifact_ids == ("EVIDENCE",)
