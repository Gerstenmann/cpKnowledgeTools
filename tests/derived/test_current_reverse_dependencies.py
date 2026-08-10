from pathlib import Path

from cp_knowledge_tools.derived import build_governance_state


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_historical_stable_dependency_is_not_current_impact(tmp_path):
    _write(
        tmp_path / "Systems/TARGET.md",
        """---
document_type: specification
specification_id: TARGET-SPEC
title: Target
version: "1.0"
status: active
canonical_path: Systems/TARGET.md
---
""",
    )
    _write(
        tmp_path / "Systems/CURRENT.md",
        """---
document_type: specification
specification_id: CURRENT-SPEC
title: Current
version: "1.0"
status: active
depends_on:
  - TARGET-SPEC
canonical_path: Systems/CURRENT.md
---
""",
    )
    _write(
        tmp_path / "Systems/Archive/HIST.md",
        """---
document_type: specification
specification_id: HIST-SPEC
title: Historic
version: "1.0"
status: superseded
depends_on:
  - TARGET-SPEC
canonical_path: Systems/Archive/HIST.md
---
""",
    )

    state = build_governance_state(
        tmp_path,
        scan_roots=("Systems",),
    )
    consumers = {edge.consumer_id for edge in state.consumers_of("TARGET-SPEC")}
    assert consumers == {"CURRENT-SPEC"}
