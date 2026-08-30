from __future__ import annotations

import base64
import json
from dataclasses import replace

import pytest

from cp_knowledge_tools.platform.hashing import sha256_bytes
from cp_knowledge_tools.reuse import (
    CandidateSource,
    ResearchWorkspace,
    apply_adoption,
    inspect_candidate,
    preview_adoption,
)
from cp_knowledge_tools.reuse.models import (
    DependencyAcceptanceState,
    Phase,
    ReuseDisposition,
    ReuseError,
)


def preview(snapshot, target, decisions, **kwargs):
    return preview_adoption(
        inspect_candidate(snapshot),
        decisions,
        assessment_id="assessment-test",
        source_file="src/helper.py",
        target_repository=target,
        target_repository_id="FIXTURE-REPOSITORY",
        target_path="adopted.py",
        provenance_output="provenance.json",
        planned_modification="Copy selected helper; retain attribution.",
        **kwargs,
    )


def apply(plan, decisions, authority, **kwargs):
    return apply_adoption(
        plan,
        decisions=decisions,
        authority=authority,
        authority_ref="fixture-owner",
        phase=Phase.IMPLEMENT,
        **kwargs,
    )


def test_preview_apply_and_provenance(candidate, target, decisions, authority):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        assert plan == preview(snapshot, target, store)
        assert not (target / "adopted.py").exists()
        result = apply(plan, store, authority(plan))
        assert result.status == "succeeded"
        assert (target / "adopted.py").read_bytes() == (
            candidate / "src/helper.py"
        ).read_bytes()
        provenance = json.loads((target / "provenance.json").read_text())
        assert provenance["upstream_repository"] == str(candidate)
        assert provenance["upstream_commit_or_snapshot"] == snapshot.commit
        assert provenance["source_file_or_unit"] == "src/helper.py"
        assert provenance["source_fingerprint"] == plan.source_fingerprint
        assert sha256_bytes(base64.b64decode(provenance["original_source_base64"])) == (
            plan.source_fingerprint
        )
        assert provenance["reuse_disposition"] == "ADAPT"
        assert provenance["local_modifications"] == plan.planned_modification
        assert "Fixture authors must be attributed" in str(provenance)
        assert "Copyright 2026 Fixture authors" in str(provenance)


@pytest.mark.parametrize(
    "disposition",
    [ReuseDisposition.LEARN, ReuseDisposition.REJECT, ReuseDisposition.USE],
)
def test_non_adapt_never_copies(candidate, target, decisions, disposition):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        store.decision = replace(store.decision, disposition=disposition)
        with pytest.raises(ReuseError):
            preview(snapshot, target, store)
        assert not (target / "adopted.py").exists()


def test_unknown_license_even_with_claimed_acceptance(candidate, target, decisions):
    (candidate / "LICENSE").unlink()
    (candidate / "pyproject.toml").write_text('[project]\nname="unknown"\n')
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        with pytest.raises(ReuseError, match="license"):
            preview(snapshot, target, decisions(snapshot))


@pytest.mark.parametrize("which", ["source", "snapshot", "license", "target"])
def test_drift_fails_closed(candidate, target, decisions, authority, which):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        changed = {
            "source": candidate / "src/helper.py",
            "snapshot": snapshot.root / "src/helper.py",
            "license": snapshot.root / "LICENSE",
            "target": target / "adopted.py",
        }[which]
        changed.chmod(0o600) if changed.exists() else None
        changed.write_text("unexpected change")
        with pytest.raises(ReuseError):
            apply(plan, store, authority(plan))
        assert not (target / "provenance.json").exists()
        if which == "target":
            assert changed.read_text() == "unexpected change"


@pytest.mark.parametrize(
    "path", ["../../outside.py", "/outside.py", ".git/config", "x/../y.py", "x\\y.py"]
)
def test_path_traversal(candidate, target, decisions, path):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        with pytest.raises(ReuseError):
            preview_adoption(
                inspect_candidate(snapshot),
                decisions(snapshot),
                assessment_id="assessment-test",
                source_file="src/helper.py",
                target_repository=target,
                target_repository_id="FIXTURE-REPOSITORY",
                target_path=path,
                provenance_output="p.json",
                planned_modification="copy",
            )


def test_existing_target_requires_expected_hash(
    candidate, target, decisions, authority
):
    old = target / "adopted.py"
    old.write_text("old")
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        with pytest.raises(ReuseError, match="conflict"):
            preview(snapshot, target, store)
        plan = preview(
            snapshot, target, store, expected_target_fingerprint=sha256_bytes(b"old")
        )
        assert "old" in plan.diff
        result = apply(plan, store, authority(plan))
        assert result.status == "succeeded"


def test_phase_authority_and_revoked_acceptance(
    candidate, target, decisions, authority
):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        for phase in (Phase.RESEARCH, Phase.EVALUATE, Phase.DESIGN):
            with pytest.raises(ReuseError, match="IMPLEMENT"):
                apply_adoption(
                    plan,
                    decisions=store,
                    authority=authority(plan),
                    authority_ref="fixture-owner",
                    phase=phase,
                )
        with pytest.raises(ReuseError, match="authority"):
            apply_adoption(
                plan,
                decisions=store,
                authority=None,
                authority_ref="fixture-owner",
                phase=Phase.IMPLEMENT,
            )
        store.decision = replace(
            store.decision, acceptance=DependencyAcceptanceState.REJECTED
        )
        with pytest.raises(ReuseError):
            apply(plan, store, authority(plan))
        assert not (target / "adopted.py").exists()


def test_existing_target_changed_after_preview(candidate, target, decisions, authority):
    existing = target / "adopted.py"
    existing.write_text("original")
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(
            snapshot,
            target,
            store,
            expected_target_fingerprint=sha256_bytes(b"original"),
        )
        existing.write_text("concurrent change")
        with pytest.raises(ReuseError, match="conflict"):
            apply(plan, store, authority(plan))
        assert existing.read_text() == "concurrent change"
        assert not (target / "provenance.json").exists()
