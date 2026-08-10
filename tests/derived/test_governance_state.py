from pathlib import Path

from cp_knowledge_tools.derived import build_governance_state


def write_md(root: Path, rel: str, fm: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}\n---\n# test\n", encoding="utf-8")


def test_active_and_reverse_dependencies(tmp_path: Path) -> None:
    write_md(
        tmp_path,
        "Systems/SEC.md",
        """document_type: specification
specification_id: CPKS-SPEC-SEC
title: SEC
version: "0.3"
status: active
evidence_class: active_constraint
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
evidence_class: active_constraint
depends_on: [CPKS-SPEC-SEC]
validated_against: [CPKS-SPEC-SEC@0.2]
canonical_path: Systems/MEM.md""",
    )
    state = build_governance_state(tmp_path, scan_roots=["Systems"])
    assert state.active_record("CPKS-SPEC-SEC").version == "0.3"
    edges = state.consumers_of("CPKS-SPEC-SEC")
    assert {(e.consumer_id, e.relation, e.target_version) for e in edges} == {
        ("CPKS-SPEC-MEM", "depends_on", None),
        ("CPKS-SPEC-MEM", "validated_against", "0.2"),
    }
