from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts.cp_tools import revise_cpks_bl_0_45_to_0_46 as revision
from scripts.cp_wiki.governance import activate_cpks_bl_0_46 as activation

CALLERS = [
    pytest.param(
        activation,
        "artifact.activate",
        [activation.ACTIVE_REL, activation.ARCHIVE_044_REL],
        id="activation",
    ),
    pytest.param(
        revision,
        "artifact.revise",
        [revision.TARGET_046_REL, revision.ARCHIVE_045_REL],
        id="revision",
    ),
]


def _stub_repository(
    tmp_path: Path,
    caller: ModuleType,
    *,
    publish_report: bool = False,
    exit_code: int = 0,
) -> Path:
    repo = tmp_path / "repo"
    interpreter = repo / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    validator = repo / caller.VALIDATOR_REL
    validator.parent.mkdir(parents=True)
    validator.write_text(
        "import json, sys\n"
        + ("# --publish-report\n" if publish_report else "")
        + "print(json.dumps(sys.argv[1:]))\n"
        + "print('gate diagnostic', file=sys.stderr)\n"
        + f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return repo


@pytest.mark.parametrize("caller, operation, targets", CALLERS)
@pytest.mark.parametrize("publish_report", [False, True])
def test_validator_command_scopes_gate_to_changed_destinations(
    tmp_path: Path,
    caller: ModuleType,
    operation: str,
    targets: list[Path],
    publish_report: bool,
) -> None:
    repo = _stub_repository(tmp_path, caller, publish_report=publish_report)
    vault = tmp_path / "vault with spaces"

    command = caller.validator_command(repo, vault)

    expected = [
        str(repo / ".venv/bin/python"),
        str(repo / caller.VALIDATOR_REL),
        "--vault",
        str(vault),
        "--gate-operation",
        operation,
    ]
    for target in targets:
        expected.extend(["--target", target.as_posix()])
    if publish_report:
        expected.append("--publish-report")
    assert command == expected
    assert "--strict-exit" not in command


def _write(vault: Path, relative: Path, content: str) -> None:
    destination = vault / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


@pytest.mark.parametrize("caller, operation, targets", CALLERS)
@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_apply_preserves_scoped_gate_exit_and_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caller: ModuleType,
    operation: str,
    targets: list[Path],
    exit_code: int,
) -> None:
    """Exercise the actual write/validator/rollback flow on a synthetic Vault."""
    repo = _stub_repository(tmp_path, caller, exit_code=exit_code)
    vault = tmp_path / "vault"
    vault.mkdir()
    run_root = tmp_path / "runs"
    unchanged = Path("Systems/Unrelated.md")
    _write(vault, unchanged, "unrelated content")

    if caller is activation:
        source = caller.DRAFT_REL
        originals = {source: "original draft", caller.ACTIVE_REL: "original active"}
        outputs = ["activated baseline", "superseded baseline"]
        monkeypatch.setattr(
            caller,
            "assert_preconditions",
            lambda _: (originals[source], originals[caller.ACTIVE_REL]),
        )
        monkeypatch.setattr(caller, "build_active_046", lambda _: (outputs[0], 5))
        monkeypatch.setattr(caller, "build_superseded_044", lambda _: outputs[1])
        monkeypatch.setattr(caller, "validate_generated", lambda *_: None)
        run_option = "--run-root"
        expected_error = caller.ActivationError
    else:
        source = caller.SOURCE_REL
        originals = {source: "original draft", caller.ACTIVE_REL: "preserved active"}
        outputs = [
            "---\nversion: '0.46'\nstatus: draft\n"
            "evidence_class: verified_current_state\n"
            "source_artifact: CPKS-BL@0.45\n---\nnew draft\n",
            "---\nstatus: withdrawn\nevidence_class: historical_evidence\n"
            "---\narchived draft\n",
        ]
        monkeypatch.setattr(caller, "assert_source_preconditions", lambda _: None)
        monkeypatch.setattr(caller, "build_new_046", lambda _: outputs[0])
        monkeypatch.setattr(caller, "build_withdrawn_045", lambda _: outputs[1])
        run_option = "--backup-root"
        expected_error = caller.RevisionError

    for relative, content in originals.items():
        _write(vault, relative, content)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "baseline-tool",
            "--apply",
            "--repo",
            str(repo),
            "--vault",
            str(vault),
            run_option,
            str(run_root),
        ],
    )

    if exit_code:
        with pytest.raises(expected_error, match=f"exit code {exit_code}"):
            caller.main()
        for relative, content in originals.items():
            assert (vault / relative).read_text(encoding="utf-8") == content
        for target in targets:
            if target not in originals:
                assert not (vault / target).exists()
    else:
        assert caller.main() == 0
        assert not (vault / source).exists()
        for target, content in zip(targets, outputs, strict=True):
            assert (vault / target).read_text(encoding="utf-8") == content

    assert (vault / unchanged).read_text(encoding="utf-8") == "unrelated content"
    logs = list(run_root.glob("*/validator-output.txt"))
    assert len(logs) == 1
    log = logs[0].read_text(encoding="utf-8")
    assert "gate diagnostic" in log
    invocation = next(
        json.loads(line) for line in log.splitlines() if line.startswith("[")
    )
    assert invocation[invocation.index("--gate-operation") + 1] == operation
    assert "--strict-exit" not in invocation
