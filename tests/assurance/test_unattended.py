"""Deterministic routine observations and fail-closed temporal evidence."""

import copy
import json
import os
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest
import yaml

from cp_knowledge_tools.assurance import unattended as module
from cp_knowledge_tools.assurance import unattended_evidence as evidence
from cp_knowledge_tools.assurance.repository import file_hash
from cp_knowledge_tools.platform.hashing import canonical_json_hash

REAL_RUN_CHECK = module._run_check
REAL_SUPPLY_SNAPSHOT = module.supply_snapshot


def git(root, *args):
    return subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args], check=True, capture_output=True
    ).stdout.decode()


@pytest.fixture
def context(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    for name, content in {
        ".gitignore": "artifacts/\n",
        "AGENTS.md": "foreign original\n",
        "pyproject.toml": "[project]\nname='fixture'\n",
        "uv.lock": "opaque lock\n",
        ".python-version": "3.14.6\n",
        ".codex/hooks.json": "{}\n",
        ".codex/hooks/guard.py": "# guard\n",
        ".codex/config.toml": "# config\n",
        "source.py": "value = 1\n",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(root, "init", "-b", "test")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "fixture",
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    project = "Projects/Fixture/Fixture.md"
    home = vault / project
    home.parent.mkdir(parents=True)
    home.write_text(
        "---\ntype: project\nproject_key: fixture\nversion: '1'\n---\nBody\n"
    )
    for state in ("Ready", "Doing"):
        (home.parent / "Work Items" / state).mkdir(parents=True)
    (home.parent / "Work Items/Doing/item.md").write_text(
        "---\nwork_item_id: WI-003\n---\nDoing work\n"
    )
    rule = vault / "Governance/RULE-ONE.md"
    rule.parent.mkdir()

    def write_rule(version="1", target=rule):
        target.write_text(
            "---\n"
            + yaml.safe_dump(
                {
                    "document_type": "specification",
                    "specification_id": "RULE-ONE",
                    "version": version,
                    "status": "active",
                    "canonical_path": str(target.relative_to(vault)),
                    "evidence_class": "active_constraint",
                }
            )
            + "---\nRule body\n"
        )

    write_rule()
    monkeypatch.setattr(module, "RULE_IDS", ("RULE-ONE",))
    uv = tmp_path / "uv"
    uv.write_bytes(b"admitted uv")
    uv.chmod(0o700)
    env = root / "artifacts/locking/environments/fixture"
    (env / "bin").mkdir(parents=True)
    (env / "bin/python").write_bytes(b"fixture interpreter")

    # The binding's real nofollow/hash verification is retained; only manifest
    # construction and host interpreter identity are synthetic in these tests.
    class Admitted:
        version = "0.12.7"

        def verify_executable(self, path):
            digest = file_hash(path)
            if digest != file_hash(uv) or path.read_bytes() != b"admitted uv":
                raise ValueError("admitted executable mismatch")
            return digest

    config = root / "config/assurance/development-tools.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    git(root, "add", str(config.relative_to(root)))
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "binding",
    )
    monkeypatch.setattr(module, "load_binding", lambda *_: Admitted())
    monkeypatch.setattr(
        module,
        "sys",
        SimpleNamespace(prefix=str(env), executable=str(env / "bin/python")),
    )
    monkeypatch.setattr(
        module,
        "supply_snapshot",
        lambda *_: {
            "inventory": {"installed": []},
            "scanner_bindings": {
                "fixture": {
                    "version": "1",
                    "executable_hash": "a" * 64,
                    "admission_hash": "b" * 64,
                }
            },
        },
    )
    calls = []
    mutation = []
    returncode = [0]

    def run_check(_root, budget, argv, maximum):
        budget.check()
        calls.append(argv)
        if mutation:
            mutation.pop(0)()
        payload = {
            "status": "passed",
            "scope": {"mode": "routine_check"},
            "checks": [{"name": "lock_freshness", "status": "passed"}],
        }
        return {
            "status": "passed" if returncode[0] == 0 else "failed",
            "exit_code": returncode[0],
        }, json.dumps(payload).encode()

    monkeypatch.setattr(module, "_run_check", run_check)
    return {
        "root": root,
        "vault_root": vault,
        "project_path": project,
        "uv": uv,
        "python": tmp_path / "base-python",
        "environment": env,
        "cache_dir": root / "artifacts/locking/cache",
        "calls": calls,
        "mutation": mutation,
        "returncode": returncode,
        "write_rule": write_rule,
    }


def run(context, **overrides):
    keys = (
        "root",
        "vault_root",
        "project_path",
        "uv",
        "python",
        "environment",
        "cache_dir",
    )
    return module.unattended(**({k: context[k] for k in keys} | overrides))


def save(context):
    result = run(context)
    return result, evidence.persist(result.payload(), context["root"])


def test_first_clean_run_is_baseline_not_failure(context):
    result, path = save(context)
    assert result.status == "passed" and result.exit_code == 0
    assert result.materiality == "no_material_change"
    payload = result.payload()
    assert payload["comparison"] == "baseline_created"
    assert payload["previous"] is None
    assert payload["input_stability"] == "stable"
    assert payload["observation"]["repository"]["working_tree"] == ""
    assert datetime.fromisoformat(payload["completed_at"]).tzinfo is not None
    assert path.stat().st_mode & 0o777 == 0o600
    assert git(context["root"], "status", "--porcelain") == ""
    evidence.validate(json.loads(path.read_text()), context["root"], path.name)


def test_unchanged_dirty_agents_is_stable_and_not_alarm(context):
    (context["root"] / "AGENTS.md").write_text("foreign unchanged dirty\n")
    first, _ = save(context)
    second, path = save(context)
    assert first.status == second.status == "passed"
    assert second.payload()["material_delta"] == []
    assert second.payload()["previous"]["run_id"] == first.payload()["run_id"]
    assert "AGENTS.md" in second.payload()["observation"]["repository"]["working_tree"]
    assert (
        evidence.discover(context["root"], module.Budget(10))["latest"]["run_id"]
        == path.stem
    )


@pytest.mark.parametrize(
    "change",
    ["tracked", "untracked", "staged", "project", "queue", "rule", "hook", "head"],
)
def test_material_delta_observes_each_protected_surface(context, change):
    save(context)
    root, vault = context["root"], context["vault_root"]
    if change in {"tracked", "staged", "head"}:
        (root / "source.py").write_text("value = 2\n")
        if change in {"staged", "head"}:
            git(root, "add", "source.py")
        if change == "head":
            git(
                root,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-m",
                "new head",
            )
    elif change == "untracked":
        (root / "new.txt").write_text("new untracked input")
    elif change == "project":
        path = vault / context["project_path"]
        path.write_text(path.read_text() + "Project update\n")
    elif change == "queue":
        parent = (vault / context["project_path"]).parent / "Work Items"
        (parent / "Doing/item.md").rename(parent / "Ready/item.md")
    elif change == "rule":
        context["write_rule"]("2")
    else:
        (root / ".codex/hooks/guard.py").write_text("# changed hook\n")
    result = run(context)
    assert result.status == "changed" and result.exit_code == 0
    assert result.materiality == "material_change"
    assert result.payload()["material_delta"]


@pytest.mark.parametrize(
    "target", ["tracked", "index", "vault", "work_item", "untracked"]
)
def test_mutation_during_run_fails_without_repair(context, target):
    root, vault = context["root"], context["vault_root"]
    path = {
        "tracked": root / "AGENTS.md",
        "vault": vault / context["project_path"],
        "work_item": (vault / context["project_path"]).parent
        / "Work Items/Doing/item.md",
        "untracked": root / "new.txt",
        "index": root / "source.py",
    }[target]

    def mutate():
        path.write_text(
            (path.read_text() if path.exists() else "") + "unexpected change\n"
        )
        if target == "index":
            git(root, "add", "source.py")

    context["mutation"].append(mutate)
    result = run(context)
    assert result.status == "failed" and result.materiality == "action_required"
    assert result.payload()["input_stability"] == "changed"
    assert path.read_text().endswith("unexpected change\n")


@pytest.mark.parametrize(
    "problem",
    ["lock_missing", "uv_hash", "stale_lock", "rule_missing", "rule_ambiguous"],
)
def test_hard_required_failures_are_visible(context, problem):
    if problem == "lock_missing":
        (context["root"] / "uv.lock").unlink()
    elif problem == "uv_hash":
        context["uv"].write_bytes(b"replacement executable")
    elif problem == "stale_lock":
        context["returncode"][0] = 1
    elif problem == "rule_missing":
        (context["vault_root"] / "Governance/RULE-ONE.md").unlink()
    else:
        context["write_rule"](target=context["vault_root"] / "Governance/duplicate.md")
    result = run(context)
    assert result.status == "failed"
    assert result.payload()["findings"]
    if problem in {"lock_missing", "uv_hash"}:
        assert context["calls"] == []


def test_corrupt_previous_keeps_current_observation_without_delta(context):
    _, path = save(context)
    path.write_text("broken JSON")
    result = run(context)
    assert result.status == "incomplete"
    assert result.payload()["comparison"] == "unavailable"
    assert result.payload()["material_delta"] == []
    assert result.payload()["input_stability"] == "stable"
    assert result.payload()["observation"]["project"]["queues"]["Doing"]


def test_corrupt_history_plus_current_failure_still_retains_evidence(context):
    _, path = save(context)
    path.write_text("broken JSON")
    context["returncode"][0] = 1
    result = run(context)
    assert result.status == "failed"
    current = evidence.persist(result.payload(), context["root"])
    assert current.is_file() and path.read_text() == "broken JSON"


def test_previous_successful_baseline_skips_failed_run(context):
    first, _ = save(context)
    context["returncode"][0] = 1
    failed, _ = save(context)
    context["returncode"][0] = 0
    current = run(context)
    assert current.payload()["previous"]["run_id"] == failed.payload()["run_id"]
    assert (
        current.payload()["comparison_baseline"]["run_id"] == first.payload()["run_id"]
    )
    assert current.status == "changed"
    assert current.payload()["material_delta"] == ["check_status"]


def test_mtime_does_not_select_prior(context):
    first, path = save(context)
    second, _ = save(context)
    os.utime(path, (9999999999, 9999999999))
    current = run(context)
    assert current.payload()["previous"]["run_id"] == second.payload()["run_id"]
    assert current.payload()["previous"]["run_id"] != first.payload()["run_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unknown"),
        ("started_at", "2026-08-31T00:00:00"),
        ("run_id", "../escape"),
        ("checks", ["bad"]),
        ("report_hash", "0" * 64),
        ("materiality", "action_required"),
        ("input_stability", "unobserved"),
    ],
)
def test_malformed_evidence_fails_safe(context, field, value):
    result = run(context)
    payload = copy.deepcopy(result.payload())
    payload[field] = value
    if field != "report_hash":
        payload["report_hash"] = canonical_json_hash(
            {k: v for k, v in payload.items() if k != "report_hash"}
        )
    with pytest.raises(ValueError):
        evidence.validate(
            payload, context["root"], f"{result.payload()['run_id']}.json"
        )


def test_missing_chain_link_is_not_silently_a_new_baseline(context):
    _, first = save(context)
    save(context)
    first.unlink()
    assert run(context).status == "incomplete"


def test_evidence_must_be_ignored_and_never_tracked(context):
    result = run(context)
    (context["root"] / ".gitignore").write_text("")
    with pytest.raises(ValueError):
        evidence.persist(result.payload(), context["root"])
    (context["root"] / ".gitignore").write_text("artifacts/\n")
    path = evidence.persist(result.payload(), context["root"])
    git(context["root"], "add", "-f", str(path.relative_to(context["root"])))
    with pytest.raises(ValueError, match="tracked"):
        evidence.persist(run(context).payload(), context["root"])


def test_evidence_directory_symlink_is_rejected(context, tmp_path):
    result = run(context)
    target = context["root"] / evidence.DIRECTORY
    target.parent.mkdir(parents=True)
    other = tmp_path / "outside"
    other.mkdir()
    target.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        evidence.persist(result.payload(), context["root"])
    assert list(other.iterdir()) == []


def test_report_discovery_is_bounded(context, monkeypatch):
    save(context)
    monkeypatch.setattr(evidence, "MAX_REPORTS", 0)
    assert run(context).status == "incomplete"


def test_budget_expiry_cannot_claim_success(context, monkeypatch):
    monkeypatch.setattr(
        module.Budget, "check", lambda _: (_ for _ in ()).throw(module.BudgetExceeded())
    )
    result = run(context)
    assert result.status == "incomplete"
    assert result.payload()["input_stability"] == "unobserved"


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout": 0},
        {"timeout": 901},
        {"command_timeout": 0},
        {"command_timeout": 241},
    ],
)
def test_invalid_budgets_cannot_execute(context, overrides):
    with pytest.raises(ValueError):
        run(context, **overrides)
    assert context["calls"] == []


def test_routine_argv_has_no_installer_or_network_surface(context):
    assert run(context).status == "passed"
    command, lint, tests = context["calls"]
    assert "routine_check" in command and "--no-evidence" in command
    assert "--allow-network" not in command
    assert "--no-cache" in lint
    assert not any(
        word in {"install", "rebuild", "pip-audit"}
        for argv in context["calls"]
        for word in argv
    )
    assert tests[-1] == "tests/assurance/test_project_environment.py"


def test_sanitized_subprocess_environment_is_network_off(context, monkeypatch):
    captured = []
    monkeypatch.setenv("SECRET_SENTINEL", "not-for-subprocess")

    def execute(argv, root, timeout, **kwargs):
        captured.append(kwargs["environment"])
        return SimpleNamespace(problem=None, code=0, duration=0.1, output=b"")

    monkeypatch.setattr(module, "execute", execute)
    REAL_RUN_CHECK(context["root"], module.Budget(10), ["synthetic"], 5)
    assert len(captured) == 1
    assert "SECRET_SENTINEL" not in captured[0]
    assert captured[0]["UV_OFFLINE"] == "1"
    assert captured[0]["PIP_NO_INDEX"] == "1"
    assert captured[0]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_concurrent_append_is_rejected_without_fork(context):
    first = run(context)
    concurrent = run(context)
    evidence.persist(first.payload(), context["root"])
    with pytest.raises(ValueError, match="concurrent evidence append"):
        evidence.persist(concurrent.payload(), context["root"])
    assert len(list((context["root"] / evidence.DIRECTORY).iterdir())) == 1


def test_readonly_git_does_not_execute_configured_fsmonitor(context):
    from cp_knowledge_tools.assurance.repository import repository_state

    marker = context["root"] / "fsmonitor-ran"
    hook = context["root"] / "artifacts/fsmonitor"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o700)
    git(context["root"], "config", "core.fsmonitor", str(hook))
    repository_state(context["root"])
    module.repository_snapshot(context["root"], module.Budget(10))
    assert not marker.exists()


def test_established_queue_gitkeep_is_hashed_not_treated_as_work(context):
    project = (context["vault_root"] / context["project_path"]).parent
    for state in ("Doing", "Ready"):
        (project / "Work Items" / state / ".gitkeep").write_text("")
    result = run(context)
    assert result.status == "passed"
    observed = result.payload()["observation"]["project"]
    assert len(observed["queue_placeholders"]) == 2
    assert len(observed["queues"]["Doing"]) == 1
    assert observed["queues"]["Ready"] == []


@pytest.mark.parametrize(
    "change",
    ["empty_checks", "empty_observation", "extra_dimension", "bad_hash", "bad_queue"],
)
def test_self_hashed_malformed_prior_cannot_crash_comparison(context, change):
    _, path = save(context)
    payload = json.loads(path.read_text())
    if change == "empty_checks":
        payload["checks"] = []
    elif change == "empty_observation":
        payload["observation"]["governance"] = {}
    elif change == "extra_dimension":
        payload["observation"]["unexpected"] = 1
    elif change == "bad_hash":
        payload["observation"]["repository"]["files"]["AGENTS.md"]["sha256"] = "bad"
    else:
        payload["observation"]["project"]["queues"]["Ready"] = 1
    payload["report_hash"] = canonical_json_hash(
        {k: v for k, v in payload.items() if k != "report_hash"}
    )
    path.write_text(json.dumps(payload))
    result = run(context)
    assert result.status == "incomplete"
    assert result.payload()["material_delta"] == []


def test_supply_projection_never_retains_requirement_url_credentials(
    context, monkeypatch
):
    manifest = context["root"] / "config/assurance/scanner-admission.json"
    manifest.write_text("{}")
    monkeypatch.setattr(
        module,
        "load_manifest",
        lambda _: {
            name: {"version": "1"}
            for name in ("cyclonedx", "pip-audit", "gitleaks", "grant")
        },
    )
    monkeypatch.setattr(
        module,
        "binding",
        lambda *_: ([], {"executable_hash": "a" * 64, "admission_hash": "b" * 64}),
    )
    monkeypatch.setattr(
        module,
        "inventory",
        lambda _: {
            "installed": [{"name": "fixture", "version": "1.0"}],
            "manifest_hash": "a" * 64,
            "lock_hashes": {"uv.lock": "b" * 64},
            "runtime_dependencies": [
                "package @ https://SECRET_SENTINEL@example.invalid/pkg"
            ],
            "optional_dependencies": {},
            "build_dependencies": [],
        },
    )
    result = REAL_SUPPLY_SNAPSHOT(context["root"], module.Budget(10))
    assert "SECRET_SENTINEL" not in json.dumps(result)
    assert result["inventory"]["installed"] == [{"name": "fixture", "version": "1.0"}]
