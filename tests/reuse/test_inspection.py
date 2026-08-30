from __future__ import annotations

import json

import pytest

from cp_knowledge_tools.reuse import (
    CandidateSource,
    CapabilityNeed,
    ResearchWorkspace,
    inspect_candidate,
    inspect_internal,
    research_gate,
    to_json,
)
from cp_knowledge_tools.reuse.models import LicenseState, ReuseError


def test_internal_prior_art_precedes_research(candidate):
    need = CapabilityNeed("Normalize values", ("normalize",))
    result = inspect_internal(candidate, need)
    assert any(hit.symbol == "normalize" for hit in result.symbols)
    assert "pyproject.toml" in result.manifests
    assert "example>=1" in result.direct_dependencies
    gate = research_gate(
        result,
        internal_sufficient=True,
        rationale="Existing normalize implementation fits.",
    )
    assert gate.status == "not_required"
    assert json.loads(to_json(result))["repository"] == str(candidate)


def test_static_candidate_facts_and_isolated_lifecycle(candidate, target):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        path = snapshot.root
        facts = inspect_candidate(snapshot)
        assert len(snapshot.commit) == 40
        assert not snapshot.root.is_relative_to(target)
        assert facts.license_state is LicenseState.DECLARED
        assert set(facts.license_files) == {"LICENSE"}
        assert facts.notice_files == ("NOTICE",)
        assert facts.direct_dependencies == ("example>=1",)
        assert "tests/test_helper.py" in facts.test_files
        assert facts.build_system == ("setuptools", "setuptools.build_meta")
        assert facts.vulnerability_state == "not_checked"
        assert any(e.kind == "install_hook" for e in facts.evidence)
        assert not (snapshot.root / ".git").exists()
    assert not path.exists()


def test_no_code_or_candidate_hooks_execute(candidate, target, tmp_path):
    marker = tmp_path / "executed"
    evil = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    (candidate / "setup.py").write_text(evil)
    (candidate / "src/helper.py").write_text(evil)
    (candidate / ".git/hooks/post-checkout").write_text("#!/bin/sh\nexit 99\n")
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        assert snapshot.dirty
        inspect_candidate(snapshot)
    assert not marker.exists()


@pytest.mark.parametrize(
    "url",
    [
        "ssh://example.invalid/a",
        "file:///tmp/repo",
        "ext::sh bad",
        "https://name:secret@example.invalid/a",
        "https://example.invalid/a?token=x",
        "https://example.invalid/a#token",
        "https://example.invalid/a\n-b",
    ],
)
def test_reject_unsafe_sources(url):
    with pytest.raises(ReuseError):
        CandidateSource.https(url)


def test_unknown_and_conflicting_license(candidate, target):
    (candidate / "LICENSE").unlink()
    (candidate / "pyproject.toml").write_text('[project]\nname="unknown"\n')
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert facts.license_state is LicenseState.UNKNOWN
    (candidate / "LICENSE").write_text("SPDX-License-Identifier: MIT\n")
    (candidate / "COPYING").write_text("SPDX-License-Identifier: Apache-2.0\n")
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert facts.license_state is LicenseState.CONFLICTING


def test_symlinks_and_secrets_are_not_read(candidate, target, tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("do not disclose")
    (candidate / "linked.py").symlink_to(secret)
    (candidate / ".env").write_text("TOKEN=do not disclose")
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert "linked.py" not in facts.files
        assert ".env" not in facts.files
        assert "do not disclose" not in to_json(facts)
        assert facts.diagnostics


def test_python_lock_scripts_and_dynamic_metadata(candidate, target):
    (candidate / "uv.lock").write_text(
        'version = 1\n[[package]]\nname="transitive"\nversion="2.0"\n'
    )
    (candidate / "package.json").write_text(
        '{"name":"sample","scripts":{"postinstall":"do-not-execute"},'
        '"dependencies":{"library":"1.0"}}'
    )
    (candidate / "requirements-dev.txt").write_text("-r outside.txt\npytest==9.0\n")
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert "transitive==2.0" in facts.locked_dependencies
        assert "pytest==9.0" in facts.direct_dependencies
        assert "dependencies:library@1.0" in facts.direct_dependencies
        assert any(
            e.kind == "install_hook" and e.value == "postinstall"
            for e in facts.evidence
        )
        assert any("not followed" in d for d in facts.diagnostics)


def test_evidence_marks_heuristics(candidate, target):
    (candidate / "src/helper.py").write_text(
        "import socket\nimport os\n# Copyright Fixture\n"
        "def connect():\n    return socket.socket()\n"
    )
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert any(e.kind == "import" and not e.heuristic for e in facts.evidence)
        assert any(e.kind == "network_access" and e.heuristic for e in facts.evidence)
        assert facts.vulnerability_state == "not_checked"


def test_dependency_url_credentials_are_redacted(candidate, target):
    (candidate / "pyproject.toml").write_text(
        '[project]\nname="example"\ndependencies=['
        '"example @ git+ssh://user:synthetic-password@example.invalid/repo"]\n'
        "[build-system]\nrequires=["
        '"builder @ https://user:synthetic-password@example.invalid/a?token=synthetic-token"]\n'
    )
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        output = to_json(facts)
        assert "synthetic-password" not in output
        assert "synthetic-token" not in output


def test_spdx_string_in_source_is_not_a_license_declaration(candidate, target):
    (candidate / "src/example.py").write_text(
        'example = "SPDX-License-Identifier: GPL-3.0-only"\n'
    )
    with ResearchWorkspace(target) as research:
        facts = inspect_candidate(research.acquire(CandidateSource.local(candidate)))
        assert facts.declared_licenses == ("MIT",)
