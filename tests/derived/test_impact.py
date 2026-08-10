from pathlib import Path

from test_governance_state import write_md

from cp_knowledge_tools.derived import (
    BaselineImpact,
    ImpactDisposition,
    assess_baseline_impact,
    assess_impact,
    build_governance_state,
)


def test_validated_against_does_not_force_revalidation(tmp_path: Path) -> None:
    write_md(
        tmp_path,
        "Systems/SEC.md",
        """document_type: specification
specification_id: CPKS-SPEC-SEC
title: SEC
version: "0.3"
status: active
canonical_path: Systems/SEC.md""",
    )
    write_md(
        tmp_path,
        "Systems/A.md",
        """document_type: specification
specification_id: CPKS-SPEC-A
title: A
version: "1.0"
status: active
validated_against: [CPKS-SPEC-SEC@0.2]
canonical_path: Systems/A.md""",
    )
    write_md(
        tmp_path,
        "Systems/B.md",
        """document_type: specification
specification_id: CPKS-SPEC-B
title: B
version: "1.0"
status: active
depends_on: [CPKS-SPEC-SEC]
canonical_path: Systems/B.md""",
    )
    state = build_governance_state(tmp_path, scan_roots=["Systems"])
    impact = assess_impact(state, "CPKS-SPEC-SEC", material_change=True)
    assert impact["CPKS-SPEC-A"] is ImpactDisposition.NO_ACTION
    assert impact["CPKS-SPEC-B"] is ImpactDisposition.REVIEW_REQUIRED


def test_baseline_materiality() -> None:
    assert assess_baseline_impact({"file_count"}) is BaselineImpact.DERIVED_STATE_ONLY
    assert (
        assess_baseline_impact({"active_version"}) is BaselineImpact.DERIVED_STATE_ONLY
    )
    assert assess_baseline_impact({"system_boundary"}) is BaselineImpact.MATERIAL
    assert assess_baseline_impact({"editorial"}) is BaselineImpact.NONE
