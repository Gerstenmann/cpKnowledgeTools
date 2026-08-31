"""Finite local checks over explicit impact. No arbitrary shell command API."""

from __future__ import annotations

import json
import sys
import tempfile
import tomllib
from pathlib import Path

import yaml

from .execution import execute
from .report import Report
from .repository import bounded_path, git, repository_state


def run_check(report: Report, name: str, command: list[str], root: Path, timeout: int):
    """Run reviewed repository tooling; the host must supply OS isolation.

    Raw tool output can contain source/secrets and is deliberately not persisted.
    Processes are killed as a group on timeout. This is not an OS sandbox.
    """
    try:
        result = execute(command, root, timeout)
        report.check(
            name,
            "incomplete"
            if result.problem
            else ("passed" if result.code == 0 else "failed"),
            command=command,
            exit_code=result.code,
            reason=result.problem,
            duration_seconds=result.duration,
            output_policy="raw output not retained; rerun command for diagnosis",
        )
    except OSError as exc:
        report.check(name, "incomplete", reason=type(exc).__name__, command=command)


def _tests_for(root: Path, paths: list[str]) -> list[str]:
    selected = set()
    for name in paths:
        parts = Path(name).parts
        if (
            parts[0] == "tests"
            and name.endswith(".py")
            and bounded_path(root, name).is_file()
        ):
            selected.add(name)
        elif len(parts) > 2 and parts[:2] == ("src", "cp_knowledge_tools"):
            target = "tests/operations" if parts[2] == "cli" else f"tests/{parts[2]}"
            if bounded_path(root, target).is_dir():
                selected.add(target)
    return sorted(selected)


def verify(
    root: Path,
    *,
    profile: str = "fast",
    paths: tuple[str, ...] = (),
    tests: tuple[str, ...] = (),
    base: str | None = None,
    timeout: int = 300,
) -> Report:
    if profile not in {"fast", "regression", "extended"}:
        raise ValueError("unknown verification profile")
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be between 1 and 3600 seconds per check")
    state = repository_state(root, base=base)
    root = Path(state["root"])
    available = set(git(root, "ls-files", "-z").split("\0"))
    available.update(state["changed_paths"])
    available.discard("")
    selected_set = set()
    for name in paths or state["changed_paths"]:
        path = bounded_path(root, name)
        if path.is_dir():
            matches = {p for p in available if p.startswith(name.rstrip("/") + "/")}
        else:
            matches = {name} if name in available else set()
        if not matches:
            raise ValueError(f"scope is absent from repository inventory: {name}")
        selected_set.update(matches)
    selected = sorted(selected_set)
    for name in selected:
        bounded_path(root, name)
    report = Report(
        {"operation": "verify", "profile": profile, "paths": selected},
        state,
        changed_paths=state["changed_paths"],
    )
    report.warnings.append(
        "Check results are evidence, not engineering or human approval."
    )
    if not selected and profile == "fast":
        report.check(
            "impact_scope",
            "incomplete",
            reason="No changed paths; supply --path or --base.",
        )
        return report
    python_paths = [
        p for p in selected if p.endswith(".py") and bounded_path(root, p).is_file()
    ]
    if python_paths:
        run_check(
            report,
            "ruff",
            [sys.executable, "-m", "ruff", "check", "--no-cache", "--", *python_paths],
            root,
            timeout,
        )
    else:
        report.check(
            "ruff",
            "not_applicable",
            reason="No existing Python files in selected scope.",
        )
    for name in selected:
        path = bounded_path(root, name)
        if not path.is_file():
            continue
        try:
            if path.suffix == ".toml":
                tomllib.loads(path.read_text())
                report.check(f"toml:{name}", "passed")
            elif path.suffix == ".json":
                json.loads(path.read_text())
                report.check(f"json_syntax:{name}", "passed")
            elif path.suffix in {".yaml", ".yml"}:
                yaml.safe_load(path.read_text())
                report.check(f"yaml_syntax:{name}", "passed")
            elif path.name == "SKILL.md":
                text = path.read_text()
                metadata = (
                    yaml.safe_load(text.split("---", 2)[1])
                    if text.startswith("---\n")
                    else None
                )
                valid = isinstance(metadata, dict) and all(
                    isinstance(metadata.get(k), str) and metadata[k].strip()
                    for k in ("name", "description")
                )
                report.check(f"skill_metadata:{name}", "passed" if valid else "failed")
        except ValueError, IndexError, yaml.YAMLError:
            report.check(f"structured_input:{name}", "failed")
    chosen_tests = (
        list(tests)
        if tests
        else (["tests"] if profile != "fast" else _tests_for(root, selected))
    )
    if profile == "fast" and not tests:
        unmapped = [
            p for p in selected if p.endswith(".py") and not _tests_for(root, [p])
        ]
        if unmapped:
            report.check(
                "test_impact_mapping",
                "incomplete",
                paths=unmapped,
                reason="Unmapped Python paths: supply reviewed --test scope.",
            )
    for name in chosen_tests:
        if not bounded_path(root, name).exists() or not Path(name).parts[0] == "tests":
            raise ValueError("test scope must exist under repository tests/")
    if chosen_tests:
        pytest_args = [
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--",
            *chosen_tests,
        ]
        if profile != "fast" and state["tool_versions"]["coverage"]:
            with tempfile.TemporaryDirectory(prefix="cpks-coverage-") as directory:
                data = str(Path(directory) / ".coverage")
                output = str(Path(directory) / "coverage.json")
                run_check(
                    report,
                    "pytest",
                    [
                        sys.executable,
                        "-m",
                        "coverage",
                        "run",
                        "--branch",
                        f"--data-file={data}",
                        "--source=src",
                        *pytest_args,
                    ],
                    root,
                    timeout,
                )
                run_check(
                    report,
                    "coverage",
                    [
                        sys.executable,
                        "-m",
                        "coverage",
                        "json",
                        f"--data-file={data}",
                        "-o",
                        output,
                    ],
                    root,
                    timeout,
                )
                if report.checks[-1]["status"] == "passed":
                    report.checks[-1]["totals"] = json.loads(Path(output).read_text())[
                        "totals"
                    ]
                    report.checks[-1]["note"] = (
                        "Branch measurement; no acceptance threshold inferred."
                    )
        else:
            run_check(report, "pytest", [sys.executable, *pytest_args], root, timeout)
    elif any(p.endswith(".py") for p in selected):
        report.check(
            "pytest",
            "incomplete",
            reason="No mapped tests; supply --test after impact review.",
        )
    else:
        report.check(
            "pytest",
            "not_applicable",
            reason="No Python change; perform skill/config behavior review.",
        )
    if any(
        p.startswith((".agents/", ".codex/", "third_party/"))
        or Path(p).name in {"pyproject.toml", "uv.lock", "requirements.txt"}
        for p in selected
    ):
        report.warnings.append(
            "Supply-chain delta: run its applicable profile and review disposition."
        )
    if profile != "fast":
        if not state["tool_versions"]["coverage"]:
            report.check(
                "coverage",
                "incomplete",
                reason="Coverage is not installed in this interpreter.",
            )
        type_paths = [p for p in python_paths if p.startswith("src/")]
        if type_paths and state["tool_versions"]["mypy"]:
            with tempfile.TemporaryDirectory(prefix="cpks-mypy-") as directory:
                run_check(
                    report,
                    "mypy",
                    [
                        sys.executable,
                        "-m",
                        "mypy",
                        "--check-untyped-defs",
                        "--follow-imports=skip",
                        "--ignore-missing-imports",
                        "--cache-dir",
                        directory,
                        *type_paths,
                    ],
                    root,
                    timeout,
                )
        elif type_paths:
            report.check(
                "mypy",
                "incomplete",
                reason="Mypy is not installed in this interpreter.",
            )
        else:
            report.check(
                "mypy", "not_applicable", reason="No Python source in selected scope."
            )
        report.warnings.append(
            "Review applicable rebuild, idempotence and Golden regression coverage."
        )
    if profile == "extended":
        report.check(
            "independent_challenge",
            "incomplete",
            kind="independent_agent_challenge",
            reason="A separate reviewer must provide scoped challenge evidence.",
        )
        report.check(
            "human_review",
            "incomplete",
            kind="human_review_required",
            reason="Resolve human, recovery, performance and security checks.",
        )
    after = repository_state(root, base=base)
    report.check(
        "input_stability",
        "passed" if after["fingerprint"] == state["fingerprint"] else "incomplete",
        before=state["fingerprint"],
        after=after["fingerprint"],
    )
    return report
