"""Codex 0.147 lifecycle protocol, observation and narrow guardrail contracts.

These tests call hooks directly; they neither grant native hook trust nor claim
complete tool mediation. Dangerous command strings are never executed.
"""

import hashlib
import json
import os
import shlex
import subprocess
import uuid
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / ".codex/hooks/guard.py"
SYSTEM_PYTHON = Path("/usr/bin/python3")


def run_git(root, *arguments):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(
        ["/usr/bin/git", "-C", str(root), *arguments],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout


@pytest.fixture
def repo(tmp_path):
    root = (tmp_path / "repository").resolve()
    root.mkdir()
    (root / "tracked.txt").write_text("original\n")
    (root / ".gitignore").write_text("ignored/\n")
    run_git(root, "init", "-b", "fixture")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false",
        "commit", "-m", "fixture",
    )
    return root


@pytest.fixture
def guard(tmp_path, monkeypatch):
    # Compile without an import cache write in the control-plane directory.
    module = ModuleType("cpks_codex_hook_test")
    module.__file__ = str(SCRIPT)
    exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), module.__dict__)
    directory = tmp_path / "session-state"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(module, "state_directory", lambda: directory)
    return module


def event(repo, name, **fields):
    return {
        "hook_event_name": name,
        "session_id": "synthetic-session",
        "transcript_path": None,
        "cwd": str(repo),
        "model": "fixture",
        "permission_mode": "default",
        **({"turn_id": "synthetic-turn"} if name == "Stop" else {}),
        **fields,
    }


def tool_event(repo, name="PreToolUse", command="git status --short", **fields):
    return event(
        repo,
        name,
        turn_id="synthetic-turn",
        tool_use_id="synthetic-tool-use",
        tool_name="Bash",
        tool_input={"command": command},
        **fields,
    )


def saved_state(guard):
    paths = list(guard.state_directory().glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_bytes())


def additional_context(result):
    return result.get("hookSpecificOutput", {}).get("additionalContext", "")


def is_denied(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_session_start_resolves_subdirectory_and_reports_observations(guard, repo):
    nested = repo / "nested" / "directory"
    nested.mkdir(parents=True)
    result = guard.handle(event(nested, "SessionStart", source="startup"))
    state = saved_state(guard)
    assert state["root"] == str(repo)
    assert state["initial_branch"] == "fixture"
    assert state["initial_head"] == run_git(repo, "rev-parse", "HEAD").strip()
    assert state["initial_dirty"] == []
    assert state["generation"] == 0
    message = additional_context(result)
    assert str(repo) in message
    assert "resolve live rule homes" in message
    assert "authority before material work" in message
    assert not is_denied(result)


@pytest.mark.parametrize("source", ["resume", "compact", "clear"])
def test_session_resume_preserves_initial_dirty_baseline(guard, repo, source):
    (repo / "tracked.txt").write_text("pre-existing work\n")
    (repo / "new-before.txt").write_text("pre-existing untracked\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    before = saved_state(guard)
    (repo / "new-after.txt").write_text("later work\n")
    result = guard.handle(event(repo, "SessionStart", source=source))
    state = saved_state(guard)
    assert state["initial_dirty"] == ["new-before.txt", "tracked.txt"]
    assert state["started"] == before["started"]
    assert state["initial_head"] == before["initial_head"]
    assert state["generation"] == 1
    assert "baseline preserved" in additional_context(result)


@pytest.mark.parametrize("corrupt", ["{", "[]", '{"schema":999}', "null"])
def test_corrupt_state_reconstructs_unknown_without_stop(guard, repo, corrupt):
    guard.handle(event(repo, "SessionStart", source="startup"))
    path = next(guard.state_directory().glob("*.json"))
    path.write_text(corrupt)
    (repo / "tracked.txt").write_text("unknown earlier work\n")
    result = guard.handle(event(repo, "SessionStart", source="resume"))
    assert "prior evidence unknown" in additional_context(result)
    assert saved_state(guard)["initial_dirty"] == ["tracked.txt"]
    assert saved_state(guard)["generation"] == 0
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_missing_state_is_reconstructable_at_post_tool_use(guard, repo):
    (repo / "tracked.txt").write_text("already changed\n")
    guard.handle(tool_event(repo, "PostToolUse", tool_response="done"))
    assert saved_state(guard)["generation"] == 0
    assert saved_state(guard)["initial_dirty"] == ["tracked.txt"]
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


@pytest.mark.parametrize(
    "command",
    [
        "cpks artifact activate --owner-direct",
        "/usr/bin/python3 -m cp_knowledge_tools.cli.cpks activate --owner-direct",
        "cpks activate --owner-direct=true",
        "env EXAMPLE=value cpks activate --owner-direct",
        "command cpks activate --owner-direct",
        "sh -c 'cpks activate --owner-direct'",
        "echo inspect && cpks activate --owner-direct",
        "cpks activate --reason foo#bar --owner-direct",
        "cpks activate --reason foo\\ #bar --owner-direct",
        "find . -exec cpks activate --owner-direct '{}' ';'",
    ],
)
def test_explicit_owner_direct_is_denied_without_state_or_git(guard, command):
    result = guard.handle(tool_event(Path("/does-not-exist"), command=command))
    assert is_denied(result)
    assert list(guard.state_directory().iterdir()) == []


def test_explicit_owner_direct_runtime_mode_is_denied_for_local_function(guard, repo):
    result = guard.handle(event(
        repo,
        "PreToolUse",
        tool_name="mcp__cp_tools__execute",
        tool_input={"authority_mode": "human_owner_direct"},
    ))
    assert is_denied(result)


@pytest.mark.parametrize(
    "command",
    [
        "git status --short",
        "git diff -- .",
        "echo '--owner-direct'",
        "printf '%s\\n' '--owner-direct'",
        "rg -- '--owner-direct' .",
        "git log --grep=--owner-direct",
        "git grep -- '--owner-direct' .",
        "find . -name --owner-direct",
        "git add -- --owner-direct",
        "git reset HEAD -- --owner-direct",
        "python -m pytest tests/hooks",
        "python -m ruff check .codex/hooks/guard.py",
        "python -m mypy .codex/hooks/guard.py",
        "cpks assurance verify --profile fast",
        "cpks activate --authority-ref approved-reference",
        "git clean -nfd",
        "git clean --dry-run -fd",
        "git clean -fnepattern",
        "rm -- / -r",
        "printf '%s' ';' git reset --hard",
        "echo example # documentation; git reset --hard",
        "echo x;# git reset --hard",
        "echo x;# cpks activate --owner-direct; git reset --hard",
        "echo x;# git reset --hard\ngit status --short",
        "printf '%s' foo\\ #bar",
        "python -c \"print('--owner-direct')\"",
    ],
)
def test_safe_commands_and_literal_mentions_are_not_denied(guard, repo, command):
    assert not is_denied(guard.handle(tool_event(repo, command=command)))


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard",
        "git -C /some/repo reset --hard HEAD",
        "git -c advice.detachedHead=false reset --hard",
        "git clean -fdx",
        "git clean -f",
        "git clean -f -- -n",
        "git clean -f -e -n",
        "git clean -f -eimportant",
        "git clean -f -ehere",
        "git clean -fen",
        "rm -rf /",
        "rm --recursive --force {root}",
        "rm -r -- {root}/../repository",
    ],
)
def test_narrow_destructive_commands_are_denied_without_execution(
    guard, repo, command
):
    before = (repo / "tracked.txt").read_bytes()
    result = guard.handle(tool_event(repo, command=command.format(root=repo)))
    assert is_denied(result)
    assert (repo / "tracked.txt").read_bytes() == before


@pytest.mark.parametrize(
    "command,denied",
    [
        ("git clean -fd --dry-run --no-dry-run", True),
        ("git clean -fn --no-dry-run", True),
        ("git clean -fd --no-dry-run --dry-run", False),
        ("git clean -fd --no-dry-run -n", False),
        ("git clean -fn -e --no-dry-run", False),
    ],
)
def test_git_clean_last_effective_dry_run_option(guard, command, denied):
    blocked, _ = guard.command_guard(command, {"/"})
    assert bool(blocked) is denied


@pytest.mark.parametrize(
    "command,denied",
    [
        ("env -- cpks artifact activate --owner-direct", True),
        ("/usr/bin/env -- cpks artifact activate --owner-direct", True),
        ("env -i -- cpks artifact activate --owner-direct", True),
        ("command -p -- cpks artifact activate --owner-direct", True),
        ("env -- git diff -- --owner-direct", False),
        ("command -v cpks --owner-direct", False),
    ],
)
def test_wrapper_options_preserve_execution_and_lookup_semantics(
    guard, command, denied
):
    blocked, _ = guard.command_guard(command, {"/"})
    assert bool(blocked) is denied


def test_configured_vault_root_deletion_is_denied(guard, repo, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (repo / ".codex").mkdir()
    (repo / ".codex/config.toml").write_text(
        "[sandbox_workspace_write]\n"
        f"writable_roots = {json.dumps([str(vault)])}\n"
    )
    assert is_denied(guard.handle(tool_event(repo, command=f"rm -rf '{vault}'")))
    assert vault.is_dir()


@pytest.mark.parametrize(
    "command",
    [
        "git push origin fixture",
        "gh pr merge 123",
        "gh release create v1.0",
        "gh release upload v1.0 dist.whl",
        "npm publish",
        "uv publish",
        "twine upload dist.whl",
        "docker push example.invalid/image",
        "kubectl apply -f deployment.yaml",
        "vercel deploy",
    ],
)
def test_remote_writes_are_advisory_and_cannot_supply_authority(guard, repo, command):
    result = guard.handle(tool_event(repo, command=command))
    output = result["hookSpecificOutput"]
    assert "permissionDecision" not in output
    assert "Owner authority" in output["additionalContext"]
    assert "approval" in output["additionalContext"]


@pytest.mark.parametrize("command", ["rm -rf .", 'rm -rf "$TARGET"', "(git status)"])
def test_unclassifiable_shell_and_relative_deletion_are_advisory(guard, repo, command):
    result = guard.handle(tool_event(repo, command=command))
    assert not is_denied(result)
    assert additional_context(result)


@pytest.mark.parametrize("tool_name", ["apply_patch", "Edit", "Write"])
@pytest.mark.parametrize("absolute", [False, True])
def test_initially_dirty_edit_only_warns(guard, repo, tool_name, absolute):
    (repo / "tracked.txt").write_text("pre-existing work\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    path = str(repo / "tracked.txt") if absolute else "tracked.txt"
    tool_input = (
        {"command": f"*** Begin Patch\n*** Update File: {path}\n"
                    "+Mention --owner-direct only in documentation.\n*** End Patch"}
        if tool_name == "apply_patch" else {"file_path": path}
    )
    result = guard.handle(event(
        repo, "PreToolUse", tool_name=tool_name, tool_input=tool_input,
    ))
    assert not is_denied(result)
    message = additional_context(result)
    assert "initially dirty" in message
    assert "Ownership is not inferred" in message


def test_patch_mentions_and_clean_target_have_no_unnecessary_denial(guard, repo):
    result = guard.handle(event(
        repo, "PreToolUse", tool_name="apply_patch",
        tool_input={"command": "*** Begin Patch\n*** Add File: guidance.md\n"
                               "+Never execute --owner-direct.\n*** End Patch"},
    ))
    assert not is_denied(result)
    assert "initially dirty" not in additional_context(result)


@pytest.mark.parametrize("tool_name", ["write_stdin", "web_search", "mcp__other__run"])
def test_uncovered_tool_paths_do_not_claim_shell_mediation(guard, repo, tool_name):
    result = guard.handle(event(
        repo, "PreToolUse", tool_name=tool_name,
        tool_input={"command": "cpks activate --owner-direct"},
    ))
    assert result == {}
    assert list(guard.state_directory().iterdir()) == []


@pytest.mark.parametrize("tool_input", [None, [], "malformed", {"command": []}])
def test_malformed_tool_input_is_not_an_authority_or_pass(guard, repo, tool_input):
    result = guard.handle(event(
        repo, "PreToolUse", tool_name="Bash", tool_input=tool_input,
    ))
    assert not is_denied(result)
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") != "allow"


@pytest.mark.parametrize("field", ["hook_event_name", "tool_name"])
def test_malformed_event_and_tool_names_return_neutral_protocol_json(
    protocol, repo, field
):
    payload = tool_event(repo)
    payload[field] = []
    result = protocol(payload)
    assert isinstance(result, dict)
    assert not is_denied(result)
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") != "allow"


def test_post_detects_changed_bytes_of_an_already_dirty_file(guard, repo):
    (repo / "tracked.txt").write_text("pre-existing work\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    initial_status = run_git(repo, "status", "--porcelain=v1")
    (repo / "tracked.txt").write_text("new work with same Git status\n")
    assert run_git(repo, "status", "--porcelain=v1") == initial_status
    result = guard.handle(tool_event(repo, "PostToolUse", tool_response="done"))
    state = saved_state(guard)
    assert state["initial_dirty"] == ["tracked.txt"]
    assert state["generation"] == 1
    assert "1 overlap initial dirty paths" in additional_context(result)
    assert "Attribution/ownership is unknown" in additional_context(result)


def test_post_keeps_prior_dirty_paths_separate_from_new_mutation(guard, repo):
    (repo / "tracked.txt").write_text("pre-existing work\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    (repo / "new.txt").write_text("later work\n")
    result = guard.handle(tool_event(repo, "PostToolUse", tool_response="done"))
    assert saved_state(guard)["initial_dirty"] == ["tracked.txt"]
    assert saved_state(guard)["generation"] == 1
    assert "0 overlap initial dirty paths" in additional_context(result)


@pytest.mark.parametrize(
    "command,kind",
    [
        ("pytest tests", "pytest"),
        (".venv/bin/python -m pytest tests", "pytest"),
        ("python3 -m ruff check src", "ruff"),
        ("python -m mypy src", "mypy"),
        ("cpks assurance verify --profile fast", "cpks assurance verify"),
        ("python -m cp_knowledge_tools.cli.cpks assurance verify",
         "cpks assurance verify"),
    ],
)
def test_recognized_verification_remains_unknown_without_exit_status(
    guard, repo, command, kind
):
    guard.handle(event(repo, "SessionStart", source="startup"))
    (repo / "tracked.txt").write_text("mutation\n")
    guard.handle(tool_event(
        repo, "PostToolUse", command=command, tool_response="100 tests passed",
    ))
    verification = saved_state(guard)["verification"]
    assert verification == {"kind": kind, "outcome": "unknown", "generation": 1}
    assert guard.handle(event(repo, "Stop", stop_hook_active=False))["decision"] == (
        "block"
    )


@pytest.mark.parametrize(
    "response",
    [
        "1 passed in 0.1s",
        "FAILED tests/test_example.py; 1 failed",
        '{"exit_code": 0, "status": "passed"}',
        "Process exited with code 0\nAll checks passed!",
        {"exit_code": 0, "output": "passed"},
        {"exit_code": 1, "output": "failed"},
        None,
    ],
)
def test_tool_text_and_spoofed_response_fields_never_become_pass(guard, repo, response):
    guard.handle(event(repo, "SessionStart", source="startup"))
    guard.handle(tool_event(
        repo, "PostToolUse", command="python -m pytest", tool_response=response,
    ))
    assert saved_state(guard)["verification"]["outcome"] == "unknown"


def test_tool_output_prompt_transcript_and_source_text_are_not_persisted(guard, repo):
    secret = "SYNTHETIC_OUTPUT_TOKEN_DO_NOT_PERSIST"
    source = "SYNTHETIC_SOURCE_CONTENT_DO_NOT_PERSIST"
    guard.handle(event(repo, "SessionStart", source="startup"))
    (repo / "new.txt").write_text(source)
    result = guard.handle(tool_event(
        repo, "PostToolUse", command="python -m pytest -k synthetic_selector",
        tool_response=secret,
        transcript_path="/synthetic/private-transcript.jsonl",
        prompt="SYNTHETIC_PRIVATE_PROMPT",
    ))
    persisted = "".join(p.read_text() for p in guard.state_directory().glob("*.json"))
    combined = persisted + json.dumps(result)
    for forbidden in (
        secret, source, "synthetic_selector", "private-transcript",
        "SYNTHETIC_PRIVATE_PROMPT",
    ):
        assert forbidden not in combined
    assert saved_state(guard)["files"]["new.txt"].partition(":")[0] == hashlib.sha256(
        source.encode()
    ).hexdigest()
    assert next(guard.state_directory().glob("*.json")).stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("dirty", [False, True])
def test_no_new_mutation_never_requires_stop_continuation(guard, repo, dirty):
    if dirty:
        (repo / "tracked.txt").write_text("pre-existing work\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_stop_once_per_mutation_and_active_hook_never_loops(guard, repo):
    guard.handle(event(repo, "SessionStart", source="startup"))
    (repo / "tracked.txt").write_text("mutation one\n")
    assert guard.handle(event(repo, "Stop", stop_hook_active=True)) == {}
    first = guard.handle(event(repo, "Stop", stop_hook_active=False))
    assert first["decision"] == "block"
    assert "narrowest relevant verification" in first["reason"]
    assert guard.handle(event(repo, "Stop", stop_hook_active=True)) == {}
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}
    (repo / "tracked.txt").write_text("mutation two\n")
    assert guard.handle(event(repo, "Stop", stop_hook_active=False))["decision"] == (
        "block"
    )
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_staging_and_commit_alone_do_not_create_new_content_mutation(guard, repo):
    (repo / "tracked.txt").write_text("pre-existing work\n")
    guard.handle(event(repo, "SessionStart", source="startup"))
    run_git(repo, "add", "tracked.txt")
    run_git(
        repo,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false",
        "commit", "-m", "pre-existing fixture work",
    )
    guard.handle(tool_event(repo, "PostToolUse", tool_response="committed"))
    assert saved_state(guard)["generation"] == 0
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_staging_preexisting_deletion_does_not_create_new_mutation(guard, repo):
    (repo / "tracked.txt").unlink()
    guard.handle(event(repo, "SessionStart", source="startup"))
    assert saved_state(guard)["initial_dirty"] == ["tracked.txt"]
    run_git(repo, "add", "--", "tracked.txt")
    guard.handle(tool_event(repo, "PostToolUse", tool_response="staged"))
    assert saved_state(guard)["generation"] == 0
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_new_deletion_is_counted_once_across_staging_and_commit(guard, repo):
    guard.handle(event(repo, "SessionStart", source="startup"))
    (repo / "tracked.txt").unlink()
    guard.handle(tool_event(repo, "PostToolUse", tool_response="deleted"))
    assert saved_state(guard)["generation"] == 1
    assert guard.handle(event(repo, "Stop", stop_hook_active=False))["decision"] == (
        "block"
    )
    run_git(repo, "add", "--", "tracked.txt")
    guard.handle(tool_event(repo, "PostToolUse", tool_response="staged"))
    assert saved_state(guard)["generation"] == 1
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}
    run_git(
        repo,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false",
        "commit", "-m", "fixture deletion",
    )
    guard.handle(tool_event(repo, "PostToolUse", tool_response="committed"))
    assert saved_state(guard)["generation"] == 1
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


def test_executable_bit_change_is_a_mutation_without_changed_bytes(guard, repo):
    target = repo / "tracked.txt"
    target.chmod(0o644)
    before = target.read_bytes()
    guard.handle(event(repo, "SessionStart", source="startup"))
    target.chmod(0o755)
    guard.handle(tool_event(repo, "PostToolUse", tool_response="mode changed"))
    assert target.read_bytes() == before
    assert saved_state(guard)["generation"] == 1
    assert guard.handle(event(repo, "Stop", stop_hook_active=False))["decision"] == (
        "block"
    )


def test_symlinked_file_is_unknown_and_never_read_as_repository_content(
    guard, repo, tmp_path
):
    secret = tmp_path / "outside.txt"
    secret.write_text("SYNTHETIC_OUTSIDE_SECRET")
    (repo / "link.txt").symlink_to(secret)
    result = guard.handle(event(repo, "SessionStart", source="startup"))
    assert "unavailable/unknown" in additional_context(result)
    assert "SYNTHETIC_OUTSIDE_SECRET" not in json.dumps(result)
    assert guard.handle(event(repo, "Stop", stop_hook_active=False)) == {}


@pytest.fixture
def protocol(repo):
    """Use real Python 3.9, deleting only this fixture's UUID-keyed state files."""
    if not SYSTEM_PYTHON.is_file():
        pytest.skip("The explicitly supported system Python is unavailable")
    session_id = str(uuid.uuid4())
    key = hashlib.sha256((session_id + "\0" + str(repo)).encode()).hexdigest()
    directory = Path("/tmp").resolve() / f"cpks-codex-hooks-{os.getuid()}"

    def invoke(payload, *, raw=None, command=None, cwd=None, success=True):
        if raw is None:
            raw = json.dumps(dict(payload, session_id=session_id))
        completed = subprocess.run(
            command or [str(SYSTEM_PYTHON), "-I", "-S", str(SCRIPT)],
            input=raw,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd or repo,
        )
        if not success:
            return completed
        assert completed.returncode == 0, completed.stderr
        assert not completed.stderr
        return json.loads(completed.stdout)

    yield invoke
    for suffix in (".json", ".lock"):
        (directory / (key + suffix)).unlink(missing_ok=True)


def test_system_python_stdin_stdout_contract(protocol, repo):
    start = protocol(event(repo, "SessionStart", source="startup"))
    assert start["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    denied = protocol(tool_event(repo, command="cpks activate --owner-direct"))
    assert denied["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert isinstance(denied["hookSpecificOutput"]["permissionDecisionReason"], str)
    (repo / "tracked.txt").write_text("protocol mutation\n")
    post = protocol(tool_event(
        repo, "PostToolUse", command="python -m pytest", tool_response="1 passed",
    ))
    assert post["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    stop = protocol(event(
        repo, "Stop", stop_hook_active=False, last_assistant_message=None,
    ))
    assert set(stop) == {"decision", "reason"}
    assert stop["decision"] == "block"
    assert protocol(event(repo, "Stop", stop_hook_active=True)) == {}
    assert protocol(event(repo, "Stop", stop_hook_active=False)) == {}


def test_unclassified_wrapper_cannot_hide_owner_direct_after_its_separator(guard, repo):
    result = guard.handle(tool_event(
        repo, command="env -u EXAMPLE -- cpks artifact activate --owner-direct",
    ))
    assert is_denied(result)


@pytest.mark.parametrize("command,denied", [
    ("git clean -fqe --dry-run", True),
    ("git clean -fe -n", True),
    ("git clean -ne --no-dry-run", False),
    ("git clean -fne -- --no-dry-run", True),
    ("git clean -fe -- --dry-run", False),
])
def test_clean_cluster_exclude_consumes_next_operand(guard, repo, command, denied):
    assert is_denied(guard.handle(tool_event(repo, command=command))) is denied


@pytest.mark.parametrize("raw", ["{", "[]", "null", '"text"', '{"unknown":true}'])
def test_malformed_protocol_stdin_is_bounded_neutral_json(protocol, raw):
    assert protocol({}, raw=raw) == {}


def test_oversized_protocol_input_is_bounded_neutral_json(protocol):
    assert protocol({}, raw=" " * (2 * 1024 * 1024 + 1)) == {}


def test_session_start_with_malformed_extra_tool_name_returns_json(protocol, repo):
    result = protocol(event(repo, "SessionStart", source="startup", tool_name=[]))
    assert isinstance(result, dict)
    assert not is_denied(result)


def test_deeply_nested_protocol_json_returns_neutral_json(protocol):
    raw = '{"nested":' + "[" * 2000 + "0" + "]" * 2000 + "}"
    assert protocol({}, raw=raw) == {}


def hook_definitions():
    return json.loads((REPOSITORY / ".codex/hooks.json").read_bytes())["hooks"]


def test_hook_definitions_use_supported_sync_commands_and_bind_script_bytes():
    definitions = hook_definitions()
    assert set(definitions) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
    digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    commands = set()
    for groups in definitions.values():
        assert len(groups) == 1
        hooks = groups[0]["hooks"]
        assert len(hooks) == 1
        hook = hooks[0]
        assert hook["type"] == "command"
        assert "async" not in hook
        assert 1 <= hook["timeout"] <= 10
        command = hook["command"]
        assert shlex.split(command)[:4] == [str(SYSTEM_PYTHON), "-I", "-S", "-c"]
        assert digest in command
        assert str(REPOSITORY) not in command
        commands.add(command)
    assert len(commands) == 1


def test_definition_launcher_runs_from_subdirectory_without_project_venv(
    protocol, repo
):
    target = repo / ".codex/hooks/guard.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(SCRIPT.read_bytes())
    nested = repo / "nested"
    nested.mkdir()
    command = hook_definitions()["SessionStart"][0]["hooks"][0]["command"]
    result = protocol(
        event(nested, "SessionStart", source="startup"),
        command=shlex.split(command),
        cwd=nested,
    )
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert str(repo) in additional_context(result)


def test_definition_launcher_rejects_modified_script_before_execution(protocol, repo):
    target = repo / ".codex/hooks/guard.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('UNREVIEWED_SCRIPT_EXECUTED')\n")
    command = hook_definitions()["PreToolUse"][0]["hooks"][0]["command"]
    completed = protocol(
        tool_event(repo), command=shlex.split(command), success=False,
    )
    assert completed.returncode != 0
    assert "hash changed" in completed.stderr
    assert "UNREVIEWED_SCRIPT_EXECUTED" not in completed.stdout
    # A launcher error cannot self-grant native trust or change repo configuration.
    assert not (repo / ".codex/config.toml").exists()
