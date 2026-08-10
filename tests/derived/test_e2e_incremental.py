from pathlib import Path

from test_governance_state import write_md

from cp_knowledge_tools.derived import (
    BaselineImpact,
    ImpactDisposition,
    assess_baseline_impact,
    assess_impact,
    build_governance_state,
)


def test_dec032_reference_case(tmp_path: Path) -> None:
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
        "Systems/MEM.md",
        """document_type: specification
specification_id: CPKS-SPEC-MEM
title: MEM
version: "0.3"
status: active
depends_on: [CPKS-SPEC-SEC]
validated_against: [CPKS-SPEC-SEC@0.3]
canonical_path: Systems/MEM.md""",
    )
    write_md(
        tmp_path,
        "Systems/KPR.md",
        """document_type: specification
specification_id: CPKS-SPEC-KPR
title: KPR
version: "0.2"
status: active
depends_on: [CPKS-SPEC-SEC]
validated_against: [CPKS-SPEC-SEC@0.2]
canonical_path: Systems/KPR.md""",
    )
    write_md(
        tmp_path,
        "Systems/BL.md",
        """document_type: baseline
baseline_id: CPKS-BL
title: BL
version: "0.46"
status: active
references: [CPKS-SPEC-SEC@0.2]
canonical_path: Systems/BL.md""",
    )
    state = build_governance_state(tmp_path, scan_roots=["Systems"])
    assert state.active_record("CPKS-SPEC-SEC").version == "0.3"
    impact = assess_impact(state, "CPKS-SPEC-SEC", material_change=True)
    assert impact["CPKS-SPEC-MEM"] is ImpactDisposition.REVIEW_REQUIRED
    assert impact["CPKS-SPEC-KPR"] is ImpactDisposition.REVIEW_REQUIRED
    assert impact["CPKS-BL"] is ImpactDisposition.NO_ACTION
    assert (
        assess_baseline_impact({"active_version"}) is BaselineImpact.DERIVED_STATE_ONLY
    )
