from __future__ import annotations

from dataclasses import replace

import pytest

from cp_knowledge_tools.reuse import (
    CandidateSource,
    ResearchWorkspace,
    inspect_candidate,
)
from cp_knowledge_tools.reuse import acquisition as acquisition_module
from cp_knowledge_tools.reuse import adoption as adoption_module
from cp_knowledge_tools.reuse.models import InspectionLimits, ReuseError

from .test_adoption import apply, preview


def test_limits_fail_explicitly(candidate, target):
    with ResearchWorkspace(target, limits=InspectionLimits(max_files=1)) as research:
        with pytest.raises(ReuseError, match="limit"):
            research.acquire(CandidateSource.local(candidate))


def test_https_needs_explicit_host_scope(target):
    with ResearchWorkspace(target) as research:
        with pytest.raises(ReuseError, match="scope"):
            research.acquire(CandidateSource.https("https://example.invalid/project"))


def test_https_path_uses_bare_objects_without_execution(candidate, target, monkeypatch):
    real = acquisition_module.git_read
    seen = []

    def simulated(root, args, **kwargs):
        seen.append(args)
        if root == target:
            return real(root, args, **kwargs)
        if args[0] == "clone":
            assert "--bare" in args and "--no-recurse-submodules" in args
            return b""
        return real(candidate, args, **kwargs)

    monkeypatch.setattr(acquisition_module, "git_read", simulated)
    with ResearchWorkspace(
        target, allowed_https_hosts=("example.invalid",)
    ) as research:
        snapshot = research.acquire(
            CandidateSource.https("https://example.invalid/project")
        )
        facts = inspect_candidate(snapshot)
        assert "src/helper.py" in facts.files
        assert snapshot.source.kind == "https"
    assert all(
        args[0] in {"clone", "rev-parse", "ls-tree", "cat-file"} for args in seen
    )


def test_git_scrubs_secret_config_and_hook_environment(
    candidate, monkeypatch, tmp_path
):
    marker = tmp_path / "executed"
    hook = tmp_path / "evil.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o700)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hook))
    monkeypatch.setenv("GIT_ASKPASS", str(hook))
    monkeypatch.setenv("SECRET_TOKEN", "must not be forwarded")
    real = acquisition_module.subprocess.Popen

    def guarded(*args, **kwargs):
        assert "SECRET_TOKEN" not in kwargs["env"]
        assert "GIT_CONFIG_COUNT" not in kwargs["env"]
        assert kwargs["env"]["GIT_ASKPASS"] != str(hook)
        return real(*args, **kwargs)

    monkeypatch.setattr(acquisition_module.subprocess, "Popen", guarded)
    acquisition_module.repository_commit(candidate)
    assert not marker.exists()


def test_symlink_target_swap_fails(candidate, target, decisions, authority, tmp_path):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        outside = tmp_path / "outside"
        outside.write_text("preserve")
        (target / "adopted.py").symlink_to(outside)
        with pytest.raises(ReuseError):
            apply(plan, store, authority(plan))
        assert outside.read_text() == "preserve"


def test_new_license_after_preview_blocks(candidate, target, decisions, authority):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        (candidate / "COPYING").write_text("New incompatible terms")
        with pytest.raises(ReuseError, match="source"):
            apply(plan, store, authority(plan))


def test_failed_second_write_compensates(
    candidate, target, decisions, authority, monkeypatch
):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        real = adoption_module._put

        def fail(target_handle, path, data, before):
            if path == "adopted.py":
                raise OSError("synthetic write failure")
            return real(target_handle, path, data, before)

        monkeypatch.setattr(adoption_module, "_put", fail)
        result = apply(plan, store, authority(plan))
        assert result.status == "compensated_failure"
        assert not (target / "provenance.json").exists()
        assert not (target / "adopted.py").exists()


def test_authority_wrong_environment_blocks(candidate, target, decisions, authority):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        resolver = authority(
            plan,
            environment={"kind": "local_repository", "identity": "/wrong/repository"},
        )
        with pytest.raises(ReuseError, match="authority"):
            apply(plan, store, resolver)


def test_failed_compensation_reports_partial_state(
    candidate, target, decisions, authority, monkeypatch
):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = preview(snapshot, target, store)
        real = adoption_module._put

        def fail(target_handle, path, data, before):
            if path == "adopted.py":
                (target / "provenance.json").write_text("concurrent edit; preserve")
                raise OSError("second write failed")
            return real(target_handle, path, data, before)

        monkeypatch.setattr(adoption_module, "_put", fail)
        result = apply(plan, store, authority(plan))
        assert result.status == "recovery_required"
        assert result.changed_paths == ("provenance.json",)
        assert (target / "provenance.json").read_text() == "concurrent edit; preserve"


def test_candidate_commit_pin_mismatch(candidate, target):
    with ResearchWorkspace(target) as research:
        with pytest.raises(ReuseError, match="commit"):
            research.acquire(CandidateSource.local(candidate, "0" * 40))


def test_target_parent_symlink_blocked(candidate, target, decisions, tmp_path):
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (target / "linked").symlink_to(outside, target_is_directory=True)
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        with pytest.raises(ReuseError):
            adoption_module.preview_adoption(
                inspect_candidate(snapshot),
                decisions(snapshot),
                assessment_id="assessment-test",
                source_file="src/helper.py",
                target_repository=target,
                target_repository_id="FIXTURE-REPOSITORY",
                target_path="linked/code.py",
                provenance_output="provenance.json",
                planned_modification="copy",
            )
    assert not list(outside.iterdir())


def test_modified_code_retains_origin_and_notices(
    candidate, target, decisions, authority
):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        with pytest.raises(ReuseError, match="copyright"):
            preview(snapshot, target, store, replacement_text="# erased origin\n")
        replacement = (
            (candidate / "src/helper.py").read_text().replace("strip()", "lower()")
        )
        plan = preview(snapshot, target, store, replacement_text=replacement)
        result = apply(plan, store, authority(plan))
        assert result.status == "succeeded"
        assert (
            result.provenance.source_fingerprint != result.provenance.target_fingerprint
        )


def test_tampered_attribution_rejected_even_with_rehashed_plan(
    candidate, target, decisions, authority
):
    with ResearchWorkspace(target) as research:
        snapshot = research.acquire(CandidateSource.local(candidate))
        store = decisions(snapshot)
        plan = replace(
            preview(snapshot, target, store), notice_or_attribution_requirements=()
        )
        plan = replace(plan, plan_fingerprint=adoption_module._plan_hash(plan))
        with pytest.raises(ReuseError, match="plan"):
            apply(plan, store, authority(plan))
