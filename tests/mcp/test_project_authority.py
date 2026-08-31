from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.cli.cpks import main
from cp_knowledge_tools.mcp.cp_wiki.projects import (
    ProjectAuthorityError,
    resolve_project_authority,
)
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault

HOME = "Projects/Internal/Pilot/Pilot.md"
TODAY = dt.date(2026, 8, 31)


def write_home(root: Path, path: str = HOME, **changes: object) -> Path:
    frontmatter = {
        "type": "project",
        "project_key": "pilot",
        "title": "Pilot",
        "version": "0.5",
        "project_status": "active",
        "project_type": "system_development",
        "owner": "Synthetic Owner",
        "governance_profile": "lean",
        "risk_level": "medium",
        "created": "2026-08-01",
        "revised": "2026-08-31",
        "canonical_path": path,
        "ai_autonomy_level": "bounded_execute",
        "tolerances": {
            "engineering": "DEV-P05 execution within confirmed scope.",
            "scope": {"expansion_allowed": False},
            "remote_effects": "forbidden_without_separate_authority",
        },
        "human_gate_required_for": ["new_normative_decision", "scope_expansion"],
    }
    frontmatter.update(changes)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n"
        "# Pilot\n\n## Scope\nLocal synthetic adapter conformance.\n",
        encoding="utf-8",
    )
    return target


def resolve(root: Path, **kwargs: object):
    return resolve_project_authority(Vault(root), "pilot", today=TODAY, **kwargs)


@pytest.mark.parametrize("kind", ["project_home", "project"])
def test_existing_project_controls_are_source_evidence_not_runtime_grants(
    tmp_path: Path, kind: str
) -> None:
    source = write_home(tmp_path)
    before = source.read_bytes()
    result = resolve(tmp_path, kind=kind)

    assert result.kind == "project_home"
    assert result.reference == "pilot"
    assert result.source_path == HOME
    assert result.source_fingerprint == hashlib.sha256(before).hexdigest()
    assert result.source_version == "0.5"
    assert result.frontmatter["risk_level"] == "medium"
    assert result.frontmatter["governance_profile"] == "lean"
    assert result.project_status == "active"
    assert result.ai_autonomy_level == "bounded_execute"
    assert result.tolerances["scope"] == {"expansion_allowed": False}
    assert result.human_gate_required_for == (
        "new_normative_decision",
        "scope_expansion",
    )
    assert "Local synthetic adapter conformance." in result.body
    assert result.execution_eligibility == "not_evaluated"
    assert result.execution_authorized is False
    assert result.read_only is True
    assert "authority_scope_for_action" in result.pending_checks
    assert "human_gates_and_hard_constraints" in result.pending_checks
    payload = asdict(result)
    assert not {"grants", "runtime_authority", "authority_valid"} & payload.keys()
    json.dumps(payload)
    assert source.read_bytes() == before


def test_current_identity_not_highest_version_or_first_active_hit(
    tmp_path: Path,
) -> None:
    write_home(tmp_path)
    write_home(tmp_path, "Projects/Internal/Pilot/Archive/old.md", version="99.0")
    write_home(
        tmp_path,
        "Projects/Internal/Other/Note.md",
        type="project_document",
        document_key="pilot",
        version="88.0",
    )
    assert resolve(tmp_path).source_version == "0.5"
    write_home(tmp_path, "Projects/Internal/Second/Pilot.md", project_status="on_hold")
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve(tmp_path)
    assert failure.value.code == "project_authority_ambiguous"


@pytest.mark.parametrize("reference", ["pil", "PILOT", "pilot@0.5", "../pilot", ""])
def test_no_fuzzy_versioned_or_path_reference(tmp_path: Path, reference: str) -> None:
    write_home(tmp_path)
    with pytest.raises(ProjectAuthorityError):
        resolve_project_authority(Vault(tmp_path), reference, today=TODAY)


def test_unknown_kind_fails_before_reading(tmp_path: Path, monkeypatch) -> None:
    vault = Vault(tmp_path)
    monkeypatch.setattr(
        vault, "read_markdown", lambda *a: pytest.fail("unexpected read")
    )
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve_project_authority(vault, "pilot", kind="owner_instruction", today=TODAY)
    assert failure.value.code == "project_authority_kind_unsupported"


@pytest.mark.parametrize(
    "status", ["proposed", "on_hold", "completed", "cancelled", "draft"]
)
def test_inactive_home_is_not_an_effective_authority_source(
    tmp_path: Path, status: str
) -> None:
    write_home(tmp_path, project_status=status)
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve(tmp_path)
    assert failure.value.code == "project_authority_not_active"


@pytest.mark.parametrize(
    "changes",
    [
        {"canonical_path": "Projects/Elsewhere/Pilot.md"},
        {"owner": ""},
        {"version": 0.5},
        {"version": "latest"},
        {"revised": "2026-07-01"},
        {"created": "2026-09-01", "revised": "2026-09-02"},
        {"revised": "2026-09-01"},
        {"revised": "2026-08-31T00:00:00Z"},
        {"ai_autonomy_level": "autonomous"},
        {"ai_autonomy_level": True},
        {"tolerances": {}},
        {"tolerances": ["unlimited"]},
        {"tolerances": {"scope": {"expansion_allowed": True}}},
        {"tolerances": {"authority": {"self_extension_allowed": True}}},
        {"tolerances": {"quality": {"acceptance_criteria_may_be_weakened": True}}},
        {"human_gate_required_for": "scope_expansion"},
        {"human_gate_required_for": ["Scope Expansion"]},
        {"human_gate_required_for": [42]},
        {"governance_profile": "anything"},
        {"risk_level": "negligible"},
        {"risk_level": []},
        {"governance_profile": {}},
        {"ai_autonomy_level": ["bounded_execute"]},
        {"project_type": "Undefined Project Type"},
        {"delivery_profile": {}},
        {"delivery_profile": "Invalid Profile"},
        {"tolerances": {"risk": {"escalate_at": "negligible"}}},
    ],
)
def test_invalid_authority_relevant_metadata_fails_closed(
    tmp_path: Path, changes: dict
) -> None:
    write_home(tmp_path, **changes)
    with pytest.raises(ProjectAuthorityError):
        resolve(tmp_path)


@pytest.mark.parametrize("autonomy", [None, "observe", "recommend", "coordinate"])
def test_no_implicit_bounded_execute(tmp_path: Path, autonomy: str | None) -> None:
    path = write_home(tmp_path, ai_autonomy_level=autonomy)
    if autonomy is None:
        path.write_text(path.read_text().replace("ai_autonomy_level: null\n", ""))
    result = resolve(tmp_path)
    assert result.ai_autonomy_level == autonomy
    assert result.execution_authorized is False
    assert result.execution_eligibility == "not_evaluated"


@pytest.mark.parametrize(
    "suffix",
    [
        "project_key: something-else\nproject_key: pilot\n",
        "type: project_document\ntype: project\n",
        "tolerances:\n  scope:\n    expansion_allowed: true\n"
        "    expansion_allowed: false\n",
        "broken: [\n",
        "recursive: &loop [*loop]\n",
    ],
)
def test_ambiguous_or_malformed_frontmatter_is_not_certified(
    tmp_path: Path, suffix: str
) -> None:
    path = write_home(tmp_path)
    raw = path.read_text()
    path.write_text(raw.replace("---\n# Pilot", suffix + "---\n# Pilot"))
    with pytest.raises(ProjectAuthorityError):
        resolve(tmp_path)


def test_missing_current_home_does_not_fall_back_to_archive(tmp_path: Path) -> None:
    write_home(tmp_path, "Projects/Internal/Pilot/Archive/Pilot.md")
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve(tmp_path)
    assert failure.value.code == "project_authority_not_found"


def test_source_is_reresolved_after_revocation_or_content_change(
    tmp_path: Path,
) -> None:
    path = write_home(tmp_path)
    first = resolve(tmp_path)
    path.write_text(path.read_text().replace("Local synthetic", "Restricted synthetic"))
    second = resolve(tmp_path)
    assert second.source_fingerprint != first.source_fingerprint
    assert first.body != second.body
    write_home(tmp_path, project_status="on_hold")
    with pytest.raises(ProjectAuthorityError):
        resolve(tmp_path)


def test_symlink_home_cannot_hide_an_authority_candidate(tmp_path: Path) -> None:
    source = write_home(tmp_path)
    link = source.parent / "Alias.md"
    link.symlink_to(source)
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve(tmp_path)
    assert failure.value.code == "project_authority_unsafe_path"


def test_cli_and_mcp_share_read_only_source_resolution(tmp_path: Path, capsys) -> None:
    source = write_home(tmp_path, created="2020-01-01", revised="2020-01-02")
    before = source.read_bytes()
    assert (
        main(
            ["project", "authority", "resolve", "pilot", "--vault-root", str(tmp_path)]
        )
        == 0
    )
    cli = json.loads(capsys.readouterr().out)
    # tests/mcp shadows the installed top-level mcp package in pytest's legacy
    # prepend mode. A fresh interpreter exercises the actual SDK and wrapper.
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            """
import asyncio, json, sys
from pathlib import Path
from cp_knowledge_tools.mcp.cp_wiki import server
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
server.get_vault = lambda: Vault(Path(sys.argv[1]))
tool = next(t for t in asyncio.run(server.mcp.list_tools())
            if t.name == 'resolve_project_authority')
print(json.dumps({'result': server.resolve_project_authority('pilot'),
                  'annotations': tool.annotations.model_dump()}))
""",
            str(tmp_path),
        ],
        text=True,
        timeout=15,
    )
    envelope = json.loads(output)
    mcp = envelope["result"]
    assert envelope["annotations"]["readOnlyHint"] is True
    assert envelope["annotations"]["destructiveHint"] is False
    assert cli["source_fingerprint"] == mcp["source_fingerprint"]
    assert cli["execution_authorized"] is mcp["execution_authorized"] is False
    assert source.read_bytes() == before
    assert (
        main(
            [
                "project",
                "authority",
                "resolve",
                "missing",
                "--vault-root",
                str(tmp_path),
            ]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "project_authority_not_found"


def test_non_project_work_item_metadata_is_not_authority(tmp_path: Path) -> None:
    write_home(tmp_path)
    other = write_home(
        tmp_path,
        "Projects/Internal/Pilot/Work Items/Done/Old.md",
        type="project_work_item",
    )
    other.write_text(
        other.read_text().replace("---\n# Pilot", "revised: 2020-01-01\n---\n# Pilot")
    )
    assert resolve(tmp_path).reference == "pilot"


def test_repeated_yaml_aliases_cannot_expand_without_a_limit(tmp_path: Path) -> None:
    path = write_home(tmp_path)
    aliases = 'a0: &a0 ["value", "value"]\n'
    for i in range(1, 20):
        aliases += f"a{i}: &a{i} [*a{i - 1}, *a{i - 1}]\n"
    path.write_text(path.read_text().replace("---\n# Pilot", aliases + "---\n# Pilot"))
    with pytest.raises(ProjectAuthorityError) as failure:
        resolve(tmp_path)
    assert failure.value.code == "project_authority_source_limit"


def test_special_file_does_not_block_reading(tmp_path: Path) -> None:
    import os

    write_home(tmp_path)
    os.mkfifo(tmp_path / "Projects/Internal/Pilot/not-a-file.md")
    with pytest.raises(ProjectAuthorityError):
        resolve(tmp_path)


def test_project_kind_does_not_mint_a_k1_mutation_grant(tmp_path: Path) -> None:
    from cp_knowledge_tools.operations.governance.authority import (
        AuthoritySourceError,
        CanonicalManagedAuthoritySource,
    )

    write_home(tmp_path)
    assert resolve(tmp_path).kind == "project_home"
    with pytest.raises(AuthoritySourceError):
        CanonicalManagedAuthoritySource(tmp_path).resolve("pilot")
