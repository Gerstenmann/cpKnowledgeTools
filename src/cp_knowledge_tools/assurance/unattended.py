"""Runtime-neutral, finite, observation-only routine assurance.

No scheduler, installer, repair, project transition or canonical writer lives here.
The caller supplies OS isolation; offline tool options are not an OS sandbox.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cp_knowledge_tools.mcp.cp_wiki.errors import VaultError
from cp_knowledge_tools.mcp.cp_wiki.vault import Vault
from cp_knowledge_tools.operations.governance.resolution import resolve_governance
from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .admission import binding, load_manifest
from .development_tools import load_binding
from .execution import execute
from .repository import bounded_path, file_hash
from .supply import inventory
from .unattended_evidence import SCHEMA, discover, reference

RULE_IDS = (
    "CPKS-FWK-AIW",
    "CPKS-FWK-ARCH",
    "CPKS-FWK-BC",
    "CPKS-BL",
    "DEV-P05",
    "DEV-P06",
    "CPKS-POL-SW-SUPPLY",
    "CPKS-SPEC-OPS",
    "CPKS-SPEC-SEC",
    "CPKS-SPEC-TST",
    "CPKT-SPEC-ARCH",
    "CPKS-FWK-PM",
    "CPKS-SPEC-PRJ",
    "CPKS-SPEC-PWI",
    "CPKS-SPEC-WP",
    "DEV-P04",
)
HOOK_PATHS = (".codex/hooks.json", ".codex/hooks/guard.py", ".codex/config.toml")
FAST_PATHS = ("src/cp_knowledge_tools/assurance",)
FAST_TESTS = ("tests/assurance/test_project_environment.py",)
MAX_FILES = 10_000
MAX_BYTES = 256_000_000


class BudgetExceeded(ValueError):
    """The cooperative total deadline or a finite resource budget was reached."""


class Budget:
    def __init__(self, seconds: int):
        if type(seconds) is not int or not 1 <= seconds <= 900:
            raise ValueError("total timeout must be between 1 and 900 seconds")
        self.deadline = time.monotonic() + seconds

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded("total run deadline exceeded")

    def remaining(self, maximum: int) -> int:
        self.check()
        return max(1, min(maximum, math.ceil(self.deadline - time.monotonic())))


def _read(path: Path, *, limit: int = 2_000_000) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("input exceeds bounded regular-file policy")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("input exceeds byte budget")
    return content


def _git(root: Path, budget: Budget, *args: str) -> str:
    result = execute(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "--literal-pathspecs",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *args,
        ],
        root,
        budget.remaining(20),
        max_bytes=4_000_000,
        environment={
            "PATH": "/usr/bin:/bin",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        },
    )
    if result.problem:
        raise BudgetExceeded("bounded Git observation did not finish")
    if result.code != 0:
        raise ValueError("Git observation failed")
    return result.output.decode("utf-8")


def repository_snapshot(root: Path, budget: Budget) -> dict:
    """Observe all protected bytes, including clean tracked files and file modes."""
    if (
        root
        != Path(_git(root, budget, "rev-parse", "--show-toplevel").strip()).resolve()
    ):
        raise ValueError("--repo-root must be the actual repository root")
    names = set(_git(root, budget, "ls-files", "-z").split("\0"))
    untracked = set(
        _git(root, budget, "ls-files", "--others", "--exclude-standard", "-z").split(
            "\0"
        )
    )
    names.update(untracked)
    names.discard("")
    untracked.discard("")
    if len(names) > MAX_FILES:
        raise BudgetExceeded("repository file count exceeds budget")
    files: dict = {}
    total = 0
    for name in sorted(names):
        budget.check()
        path = bounded_path(root, name)
        if not path.exists():
            files[name] = {"state": "absent"}
            continue
        info = path.stat(follow_symlinks=False)
        total += info.st_size
        if total > MAX_BYTES:
            raise BudgetExceeded("repository fingerprint bytes exceed budget")
        files[name] = {"sha256": file_hash(path), "mode": stat.S_IMODE(info.st_mode)}
    index_path = Path(_git(root, budget, "rev-parse", "--git-path", "index").strip())
    if not index_path.is_absolute():
        index_path = root / index_path
    return {
        "root": str(root),
        "branch": _git(root, budget, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "head": _git(root, budget, "rev-parse", "--verify", "HEAD").strip(),
        "working_tree": _git(root, budget, "status", "--porcelain=v1", "-z"),
        "index_sha256": file_hash(index_path) if index_path.exists() else "absent",
        "staged_entries_sha256": sha256_bytes(
            _git(root, budget, "ls-files", "--stage", "-z").encode()
        ),
        "untracked_paths": sorted(untracked),
        "files": files,
        "protected_content_sha256": canonical_json_hash(files),
    }


class ObservationVault(Vault):
    """Bound the shared resolver's reads and cache one coherent observation pass."""

    def __init__(self, root: Path, budget: Budget):
        super().__init__(root)
        self.budget = budget
        self.raw: dict[str, str] = {}
        self.documents: dict = {}
        self.bytes_read = 0

    def iter_markdown_files(self):
        count = 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            self.budget.check()
            # Repository internals are not Vault documents.
            dirs[:] = [name for name in dirs if name != ".git"]
            for name in dirs:
                if (Path(directory) / name).is_symlink():
                    raise ValueError("symlink directory in observed Vault")
            for name in names:
                count += 1
                if count > MAX_FILES:
                    raise BudgetExceeded("Vault discovery exceeds file budget")
                if Path(name).suffix.lower() not in {".md", ".markdown"}:
                    continue
                path = Path(directory) / name
                bounded_path(self.root, str(path.relative_to(self.root)))
                yield path

    def read_markdown(self, relative_path):
        self.budget.check()
        relative = str(relative_path)
        if relative not in self.raw:
            content = _read(bounded_path(self.root, relative))
            self.bytes_read += len(content)
            if self.bytes_read > MAX_BYTES:
                raise BudgetExceeded("Vault observation exceeds byte budget")
            self.raw[relative] = content.decode("utf-8")
        return self.raw[relative]

    def read_document(self, relative_path):
        relative = str(relative_path)
        if relative not in self.documents:
            self.documents[relative] = super().read_document(relative)
        return self.documents[relative]


def vault_snapshot(root: Path, project_path: str, budget: Budget) -> dict:
    vault = ObservationVault(root, budget)
    rules = {}
    for stable_id in RULE_IDS:
        budget.check()
        resolved = resolve_governance(vault, stable_id)
        if (
            resolved.get("integrity_ok") is not True
            or resolved.get("status") != "active"
        ):
            raise ValueError("active governance integrity not established")
        rules[stable_id] = {
            key: resolved[key]
            for key in (
                "stable_id",
                "version",
                "relative_path",
                "canonical_path",
                "integrity_ok",
                "current_state_fingerprint",
            )
        }
    home = vault.read_document(project_path)
    if home.frontmatter.get("type") != "project" or not isinstance(
        home.frontmatter.get("project_key"), str
    ):
        raise ValueError("project path must identify an actual Project Home")
    project: dict = {
        "path": project_path,
        "project_key": home.frontmatter["project_key"],
        "version": str(home.frontmatter.get("version", "")),
        "sha256": sha256_bytes(vault.read_markdown(project_path).encode()),
        "execution_eligibility": "not_evaluated",
        "queues": {},
        "queue_placeholders": {},
    }
    for state in ("Doing", "Ready"):
        relative = str(Path(project_path).parent / "Work Items" / state)
        directory = bounded_path(vault.root, relative)
        items: list[dict] = []
        if directory.exists():
            with os.scandir(directory) as entries:
                for entry in entries:
                    budget.check()
                    if len(items) >= 1000:
                        raise BudgetExceeded("project queue exceeds item budget")
                    path = bounded_path(vault.root, f"{relative}/{entry.name}")
                    if entry.name == ".gitkeep":
                        project["queue_placeholders"][
                            str(path.relative_to(vault.root))
                        ] = sha256_bytes(_read(path))
                        continue
                    if not path.is_file() or path.suffix != ".md":
                        raise ValueError("unexpected non-Markdown project queue entry")
                    content = _read(path)
                    items.append(
                        {
                            "path": str(path.relative_to(vault.root)),
                            "sha256": sha256_bytes(content),
                        }
                    )
        project["queues"][state] = sorted(items, key=lambda item: item["path"])
    # Cached parsing is efficient but must not conceal replacement during resolution.
    targets = {
        r["relative_path"]: r["current_state_fingerprint"] for r in rules.values()
    }
    targets[project_path] = project["sha256"]
    for name, digest in targets.items():
        budget.check()
        if file_hash(bounded_path(vault.root, name)) != digest:
            raise ValueError("Vault target changed during observation")
    return {"governance": rules, "project": project}


def supply_snapshot(root: Path, budget: Budget) -> dict:
    budget.check()
    manifest_path = bounded_path(root, "config/assurance/scanner-admission.json")
    entries = load_manifest(manifest_path)
    paths = {
        "cyclonedx": "python/bin/python",
        "pip-audit": "python/bin/python",
        "gitleaks": "gitleaks/gitleaks",
        "grant": "grant/grant",
    }
    tools = {}
    for name, relative in paths.items():
        budget.check()
        _, observed = binding(
            root / "artifacts/assurance/scanner-tools" / relative, entries[name], name
        )
        tools[name] = {"version": entries[name]["version"], **observed}
    current = inventory(root)
    budget.check()
    installed = []
    for package in current["installed"]:
        name, version = package["name"], package["version"]
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name
        ):
            raise ValueError("installed package name is not safe metadata")
        if not isinstance(version, str) or not re.fullmatch(
            r"[A-Za-z0-9.!+_-]{1,128}", version
        ):
            raise ValueError("installed package version is not safe metadata")
        installed.append({"name": name, "version": version})
    # Declarations can contain direct URLs with credentials. Retain only hashes,
    # never raw requirements, license prose, package locations or environment data.
    safe_inventory = {
        "manifest_hash": current["manifest_hash"],
        "lock_hashes": current["lock_hashes"],
        "declared_dependencies_sha256": canonical_json_hash(
            {
                key: current[key]
                for key in (
                    "runtime_dependencies",
                    "optional_dependencies",
                    "build_dependencies",
                )
            }
        ),
        "installed": installed,
        "inventory_scope": "current explicitly selected locked interpreter",
    }
    return {
        "inventory": safe_inventory,
        "scanner_bindings": tools,
        "manifest_sha256": file_hash(manifest_path),
        "network_scans": "not_performed",
    }


def environment_snapshot(root: Path, uv: Path, environment: Path) -> dict:
    if str(Path(sys.prefix)) != str(environment) or str(Path(sys.executable)) != str(
        environment / "bin/python"
    ):
        raise ValueError(
            "unattended must run from the explicitly selected locked environment"
        )
    admitted = load_binding(root, root / "config/assurance/development-tools.json")
    pin = _read(bounded_path(root, ".python-version")).decode().strip()
    if not re.fullmatch(r"3\.14\.\d+", pin):
        raise ValueError("Python pin is not an exact admitted-series patch")
    return {
        "python_pin": pin,
        "python_pin_sha256": file_hash(root / ".python-version"),
        "pyproject_sha256": file_hash(root / "pyproject.toml"),
        "lock_sha256": file_hash(root / "uv.lock"),
        "uv_sha256": admitted.verify_executable(uv),
        "uv_version": admitted.version,
        "binding_sha256": file_hash(root / "config/assurance/development-tools.json"),
        "environment": str(environment),
        "interpreter": sys.executable,
    }


def hook_snapshot(root: Path) -> dict:
    return {
        "fingerprints": {
            name: file_hash(bounded_path(root, name)) for name in HOOK_PATHS
        },
        "trust_enablement": "unknown",
        "trust_observation_scope": (
            "Native host observation is separate; no supplied receipt is trusted."
        ),
    }


@dataclass
class UnattendedReport:
    data: dict

    @property
    def status(self):
        return self.data["status"]

    @property
    def materiality(self):
        return self.data["materiality"]

    @property
    def exit_code(self):
        return {"passed": 0, "changed": 0, "failed": 1, "incomplete": 2}[self.status]

    def payload(self):
        return self.data


def _run_check(
    root: Path, budget: Budget, argv: list[str], maximum: int
) -> tuple[dict, bytes]:
    with tempfile.TemporaryDirectory(prefix="cpks-unattended-") as temporary:
        result = execute(
            argv,
            root,
            budget.remaining(maximum),
            max_bytes=2_000_000,
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": temporary,
                "TMPDIR": temporary,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "UV_OFFLINE": "1",
                "PIP_NO_INDEX": "1",
            },
        )
    return {
        "status": "incomplete"
        if result.problem
        else "passed"
        if result.code == 0
        else "failed",
        "exit_code": result.code,
        "reason": result.problem,
        "duration_seconds": result.duration,
        "output_policy": "raw output discarded",
    }, result.output


def unattended(
    root: Path,
    *,
    vault_root: Path,
    project_path: str,
    uv: Path,
    python: Path,
    environment: Path,
    cache_dir: Path,
    timeout: int = 240,
    command_timeout: int = 45,
    task_id: str | None = None,
    automation_id: str | None = None,
    codex_version: str | None = None,
) -> UnattendedReport:
    """Observe, check, compare and return evidence; persistence is a thin adapter."""
    budget = Budget(timeout)
    if type(command_timeout) is not int or not 1 <= command_timeout <= timeout:
        raise ValueError("command timeout must fit the finite total timeout")
    for label in (task_id, automation_id, codex_version):
        if label is not None and (
            not isinstance(label, str)
            or len(label) > 128
            or any(ord(c) < 32 for c in label)
        ):
            raise ValueError("identity labels must be bounded printable strings")
    if not root.is_absolute() or not vault_root.is_absolute():
        raise ValueError("repository and Vault roots must be explicit absolute paths")
    root = root.resolve(strict=True)
    started = datetime.now(UTC)
    data: dict = {
        "schema_version": SCHEMA,
        "run_id": started.strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex,
        "started_at": started.isoformat(),
        "completed_at": None,
        "identity": {
            "task_id": task_id,
            "automation_id": automation_id,
            "codex_version": codex_version,
            "source": "caller_labels_not_authority",
        },
        "profile": "routine_check",
        "network_mode": "offline_tools_host_sandbox_required",
        "budget": {"total_seconds": timeout, "command_seconds": command_timeout},
        "observation": {"repository": {"root": str(root)}},
        "checks": [],
        "findings": [],
        "previous": None,
        "comparison_baseline": None,
        "material_delta": [],
        "comparison": "unavailable",
        "input_stability": "unobserved",
        "mutation_observation": "unobserved",
        "status": "passed",
        "materiality": "no_material_change",
        "decision": "not_evaluated",
    }

    def check(name: str, status: str = "passed", *, required: bool = True, **details):
        data["checks"].append(
            {"name": name, "status": status, "required": required, **details}
        )
        if required and status in {"failed", "incomplete"}:
            data["findings"].append(
                {
                    "code": name,
                    "status": status,
                    "recommended_disposition": (
                        "Review evidence; a separate authorized task decides "
                        "any action."
                    ),
                }
            )

    before: dict = {}
    chain: dict | None = None
    try:
        try:
            chain = discover(root, budget)
            data["previous"] = reference(chain["latest"], chain)
            data["comparison_baseline"] = reference(chain["successful"], chain)
            check("previous_evidence")
        except OSError, ValueError, TypeError, KeyError, RecursionError:
            check(
                "previous_evidence",
                "incomplete",
                reason=(
                    "Prior evidence is corrupt, unreadable, incomplete or exceeds "
                    "budget; no temporal claim."
                ),
            )
        before["repository"] = repository_snapshot(root, budget)
        data["observation"].update(before)
        check("repository_observation")
        for name, observe in (
            ("vault", lambda: vault_snapshot(vault_root, project_path, budget)),
            ("environment", lambda: environment_snapshot(root, uv, environment)),
            ("supply", lambda: supply_snapshot(root, budget)),
            ("hooks", lambda: hook_snapshot(root)),
        ):
            try:
                budget.check()
                value = observe()
                if name == "vault":
                    before.update(value)
                else:
                    before[name] = value
                data["observation"].update(before)
                check(f"{name}_observation")
            except BudgetExceeded:
                raise
            except (OSError, ValueError, TypeError, KeyError, VaultError) as exc:
                check(f"{name}_observation", "failed", reason=type(exc).__name__)
        check(
            "native_hook_trust",
            "incomplete",
            required=False,
            reason=(
                "No reliable native trust surface in this runtime-neutral core; "
                "observe separately in the host."
            ),
        )
        if "environment" in before:
            command = [
                str(environment / "bin/python"),
                "-B",
                "-m",
                "cp_knowledge_tools.cli.cpks",
                "assurance",
                "environment",
                "--repo-root",
                str(root),
                "--mode",
                "routine_check",
                "--uv",
                str(uv),
                "--python",
                str(python),
                "--environment",
                str(environment),
                "--cache-dir",
                str(cache_dir),
                "--timeout",
                str(command_timeout),
                "--no-evidence",
            ]
            result, output = _run_check(root, budget, command, command_timeout)
            check("locked_environment", **result)
            if output:
                payload = json.loads(output)
                data["environment_checks"] = [
                    {key: c[key] for key in ("name", "status", "exit_code") if key in c}
                    for c in payload["checks"]
                ]
                if payload.get("scope", {}).get("mode") != "routine_check":
                    raise ValueError("unexpected environment report profile")
                if result["status"] == "passed" and payload.get("status") != "passed":
                    raise ValueError(
                        "environment report does not prove routine consistency"
                    )
            elif result["status"] == "passed":
                raise ValueError("environment report is missing")
            if result["status"] == "passed":
                # Fixed reviewed baseline; no arbitrary changed-path test selection.
                argv = [
                    str(environment / "bin/python"),
                    "-B",
                    "-m",
                    "ruff",
                    "check",
                    "--no-cache",
                    "--",
                    *FAST_PATHS,
                ]
                result, _ = _run_check(root, budget, argv, command_timeout)
                check("fast_assurance_lint", **result, paths=list(FAST_PATHS))
                argv = [
                    str(environment / "bin/python"),
                    "-B",
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--",
                    *FAST_TESTS,
                ]
                result, _ = _run_check(root, budget, argv, command_timeout)
                check(
                    "fast_environment_contract_tests", **result, tests=list(FAST_TESTS)
                )
        else:
            check(
                "locked_execution",
                "incomplete",
                reason="No verified locked interpreter; no execution fallback.",
            )
    except BudgetExceeded:
        check(
            "run_budget",
            "incomplete",
            reason="Finite total run deadline/resource budget reached.",
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        VaultError,
        RecursionError,
    ) as exc:
        check("run_observation", "failed", reason=type(exc).__name__)
    finally:
        # Final observation shares the total budget; exhaustion cannot pass.
        try:
            after = {"repository": repository_snapshot(root, budget)}
            after.update(vault_snapshot(vault_root, project_path, budget))
            if "environment" in before:
                after["environment"] = environment_snapshot(root, uv, environment)
            if "supply" in before:
                after["supply"] = supply_snapshot(root, budget)
            if "hooks" in before:
                after["hooks"] = hook_snapshot(root)
            differences = [key for key in before if before[key] != after.get(key)]
            if "repository" not in before:
                raise ValueError("initial repository observation unavailable")
            data["input_stability"] = "changed" if differences else "stable"
            data["mutation_observation"] = (
                "unexpected_change_observed"
                if differences
                else "no_protected_change_observed"
            )
            data["final_observation_sha256"] = canonical_json_hash(after)
            check(
                "protected_inputs_unchanged",
                "failed" if differences else "passed",
                changed_dimensions=differences,
                attribution=(
                    "Observed changes may be concurrent; "
                    "no repair or attribution claim."
                ),
            )
            if chain is not None and discover(root, budget)["files"] != chain["files"]:
                check(
                    "evidence_chain_stability",
                    "incomplete",
                    reason=(
                        "Concurrent evidence writer observed; "
                        "no reliable temporal comparison."
                    ),
                )
                chain = None
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            VaultError,
            RecursionError,
        ) as exc:
            check("final_input_observation", "incomplete", reason=type(exc).__name__)
    if chain is not None:
        previous_success = chain["successful"]
        if previous_success is None:
            data["comparison"] = (
                "baseline_created"
                if chain["latest"] is None
                else "no_successful_prior_evidence"
            )
        else:
            data["comparison"] = "compared_with_previous_successful_run"
            current = data["observation"]
            old = previous_success["observation"]
            data["material_delta"] = [
                key
                for key in sorted(set(current) | set(old))
                if current.get(key) != old.get(key)
            ]
            data["material_delta_details"] = {
                key: [
                    name
                    for name in sorted(
                        set(current.get(key, {})) | set(old.get(key, {}))
                    )
                    if current.get(key, {}).get(name) != old.get(key, {}).get(name)
                ]
                for key in data["material_delta"]
            }
        if chain["latest"] is not None:
            # Recovery is itself a material check transition. State comparisons
            # continue to use the last successful run as requested.
            old_checks = {
                c["name"]: c["status"]
                for c in chain["latest"]["checks"]
                if c["required"]
            }
            new_checks = {
                c["name"]: c["status"] for c in data["checks"] if c["required"]
            }
            if old_checks != new_checks:
                data["material_delta"].append("check_status")
    statuses = {c["status"] for c in data["checks"] if c["required"]}
    data["status"] = (
        "failed"
        if "failed" in statuses
        else "incomplete"
        if "incomplete" in statuses
        else "changed"
        if data["material_delta"]
        else "passed"
    )
    data["materiality"] = {
        "passed": "no_material_change",
        "changed": "material_change",
        "failed": "action_required",
        "incomplete": "action_required",
    }[data["status"]]
    data["completed_at"] = datetime.now(UTC).isoformat()
    data["report_hash"] = canonical_json_hash(data)
    return UnattendedReport(data)
