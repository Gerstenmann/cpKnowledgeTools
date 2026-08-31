"""Finite uv checks and observed fresh rebuilds; uv owns lockfile semantics."""

from __future__ import annotations

import json
import os
import platform
import re
import tempfile
from pathlib import Path

from .development_tools import DevelopmentToolBinding, load_binding
from .execution import execute
from .report import Report
from .repository import bounded_path, file_hash, repository_state

_IDENTITY = (
    "import json,platform,sys,sysconfig; print(json.dumps({"
    "'implementation':platform.python_implementation(),"
    "'version':platform.python_version(),'executable':sys.executable,"
    "'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
    "'system':platform.system(),'machine':platform.machine(),"
    "'soabi':sysconfig.get_config_var('SOABI'),"
    "'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}))"
)


def _scoped_path(root: Path, path: Path, prefix: str, *, child: bool) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{prefix} path must be absolute")
    relative = path.relative_to(root)
    expected = Path(prefix)
    if (relative.parent if child else relative) != expected:
        raise ValueError(
            f"path must be {'a direct child of ' if child else ''}{prefix}"
        )
    return bounded_path(root, str(relative))


def _inputs(root: Path, binding_path: Path) -> dict[str, str]:
    names = ["pyproject.toml", "uv.lock", ".python-version"]
    names.append(str(binding_path.relative_to(root)))
    return {name: file_hash(bounded_path(root, name)) for name in names}


def _run(
    report: Report,
    name: str,
    argv: list[str],
    root: Path,
    timeout: int,
    environment: dict[str, str],
) -> bytes | None:
    result = execute(argv, root, timeout, max_bytes=1_000_000, environment=environment)
    report.check(
        name,
        "incomplete" if result.problem else "passed" if result.code == 0 else "failed",
        command=argv,
        exit_code=result.code,
        reason=result.problem,
        duration_seconds=result.duration,
        output_policy="raw subprocess output is not retained",
    )
    return result.output if result.code == 0 and result.problem is None else None


def _identity(
    report: Report,
    name: str,
    python: Path,
    pin: str,
    binding: DevelopmentToolBinding,
    root: Path,
    timeout: int,
    environment: dict[str, str],
) -> dict:
    output = _run(
        report,
        name,
        [str(python), "-I", "-B", "-c", _IDENTITY],
        root,
        timeout,
        environment,
    )
    if output is None:
        raise ValueError(f"{name}: interpreter identity could not be inspected")
    identity = json.loads(output)
    if (
        not isinstance(identity, dict)
        or identity.get("implementation") != "CPython"
        or identity.get("version") != pin
        or identity.get("system") != binding.system
        or identity.get("machine") != binding.machine
        or identity.get("executable") != str(python)
        or not isinstance(identity.get("prefix"), str)
        or not isinstance(identity.get("base_prefix"), str)
        or not isinstance(identity.get("soabi"), str)
        or type(identity.get("gil_disabled")) is not bool
        or identity["gil_disabled"]
    ):
        raise ValueError(f"{name}: interpreter does not match the pin/platform/path")
    report.check(f"{name}_identity", "passed", identity=identity)
    return identity


def project_environment(
    root: Path,
    *,
    uv: Path,
    python: Path,
    environment: Path,
    cache_dir: Path,
    mode: str = "check",
    binding_path: Path | None = None,
    allow_network: bool = False,
    offline_frozen: bool = False,
    timeout: int = 300,
) -> Report:
    """Check consistency or rebuild an absent, narrowly scoped environment.

    Check mode cannot establish fresh-build provenance. Rebuild mode observes
    absence itself; no caller-supplied receipt can manufacture freshness evidence.
    The wrapper is not an OS sandbox and does not make a hermetic-build claim.
    """
    if (
        mode not in {"check", "rebuild"}
        or type(timeout) is not int
        or not 1 <= timeout <= 3600
        or type(allow_network) is not bool
        or type(offline_frozen) is not bool
    ):
        raise ValueError("unsupported environment mode or execution timeout")
    if offline_frozen and (mode != "rebuild" or allow_network):
        raise ValueError("--offline-frozen requires offline rebuild mode")
    state = repository_state(root)
    root = Path(state["root"])
    report = Report(
        {
            "operation": "environment",
            "mode": mode,
            "offline_frozen": offline_frozen,
            "network_allowed": allow_network,
            "fresh_rebuild": "unobserved",
        },
        state,
        changed_paths=state["changed_paths"],
    )
    report.warnings.extend(
        [
            "Evidence only; development-tool binding and successful checks "
            "are not approval.",
            "Offline is a uv option, not an OS-enforced network or "
            "hermetic-build guarantee.",
            "--no-build still permits the reviewed editable project "
            "and its build backend.",
        ]
    )
    before: dict[str, str] | None = None
    binding_path = binding_path or root / "config/assurance/development-tools.json"
    try:
        before = _inputs(root, binding_path)
        report.check("environment_inputs", "passed", input_hashes=before)
        pin = bounded_path(root, ".python-version").read_text().strip()
        if not re.fullmatch(r"3\.14\.\d+", pin):
            raise ValueError(
                ".python-version must contain one exact CPython 3.14 patch"
            )
        binding = load_binding(root, binding_path)
        binding.verify_executable(uv)
        if (platform.system(), platform.machine()) != (binding.system, binding.machine):
            raise ValueError("host platform differs from the reviewed uv binding")
        if not python.is_absolute() or not os.access(python, os.X_OK):
            raise ValueError("--python requires an explicit absolute executable")
        base_hash = file_hash(python.resolve(strict=True), max_bytes=100_000_000)
        environment = _scoped_path(
            root,
            environment,
            "artifacts/locking/environments",
            child=True,
        )
        cache_dir = _scoped_path(
            root, cache_dir, "artifacts/locking/cache", child=False
        )
        if mode == "rebuild" and environment.exists():
            raise ValueError(
                "rebuild target must be absent; existing environments are preserved"
            )
        if mode == "check" and not environment.is_dir():
            raise ValueError("check target must be an existing environment")
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="cpks-uv-home-") as home:
            env = {
                "PATH": "/usr/bin:/bin",
                "HOME": home,
                "TMPDIR": home,
                "XDG_CONFIG_HOME": home,
                "XDG_CACHE_HOME": home,
                "XDG_DATA_HOME": home,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "UV_PROJECT_ENVIRONMENT": str(environment),
            }
            base = _identity(
                report, "base_python", python, pin, binding, root, timeout, env
            )
            if base["prefix"] != base["base_prefix"]:
                raise ValueError(
                    "--python must select a base interpreter, not a virtual environment"
                )
            binding.verify_executable(uv)
            version = _run(
                report, "uv_version", [str(uv), "--version"], root, timeout, env
            )
            if version is None or not re.fullmatch(
                rf"uv {re.escape(binding.version)}(?: \([^\r\n]+\))?\s*",
                version.decode("utf-8"),
            ):
                raise ValueError("uv version differs from reviewed binding")
            report.check("development_tool_binding", "passed", binding=binding.manifest)
            common = [
                str(uv),
                "--no-config",
                "--no-python-downloads",
                "--no-managed-python",
                "--no-progress",
                "--cache-dir",
                str(cache_dir),
            ]
            if not allow_network:
                common.append("--offline")

            def uv_check(name: str, arguments: list[str]) -> bool:
                binding.verify_executable(uv)
                if _inputs(root, binding_path) != before:
                    raise ValueError("environment inputs changed before uv execution")
                if (
                    file_hash(python.resolve(strict=True), max_bytes=100_000_000)
                    != base_hash
                ):
                    raise ValueError("base interpreter changed before uv execution")
                result = _run(
                    report,
                    name,
                    common
                    + arguments
                    + [
                        "--python",
                        str(python),
                        "--default-index",
                        "https://pypi.org/simple",
                        "--keyring-provider",
                        "disabled",
                    ],
                    root,
                    timeout,
                    env,
                )
                if _inputs(root, binding_path) != before:
                    raise ValueError("environment inputs changed during uv execution")
                binding.verify_executable(uv)
                return result is not None

            if not uv_check("lock_freshness", ["lock", "--check"]):
                return report
            sync = [
                "sync",
                "--frozen" if offline_frozen else "--locked",
                "--extra",
                "dev",
                "--no-build",
            ]
            if mode == "check":
                sync.append("--check")
            else:
                # Recheck immediately before the only environment-creating command.
                _scoped_path(
                    root, environment, "artifacts/locking/environments", child=True
                )
                if environment.exists():
                    raise ValueError(
                        "rebuild target appeared before sync; refusing mutation"
                    )
                environment.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not uv_check("environment_sync", sync):
                return report
            _scoped_path(
                root, environment, "artifacts/locking/environments", child=True
            )
            if not environment.is_dir():
                raise ValueError(
                    "uv did not produce the expected environment directory"
                )
            target = _identity(
                report,
                "environment_python",
                environment / "bin/python",
                pin,
                binding,
                root,
                timeout,
                env,
            )
            if (
                Path(target["prefix"]) != environment
                or target["base_prefix"] != base["base_prefix"]
                or target["soabi"] != base["soabi"]
                or target["gil_disabled"] != base["gil_disabled"]
            ):
                raise ValueError(
                    "target interpreter prefix/base/ABI differs from "
                    "selected environment"
                )
            if (
                file_hash(python.resolve(strict=True), max_bytes=100_000_000)
                != base_hash
            ):
                raise ValueError(
                    "base interpreter changed during environment operation"
                )
            binding.verify_executable(uv)
            report.check(
                "interpreter_binding", "passed", base_executable_sha256=base_hash
            )
            if mode == "rebuild":
                report.scope["fresh_rebuild"] = "observed_absent_then_created"
                report.check("fresh_rebuild", "passed", environment=str(environment))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report.check("project_environment", "failed", reason=str(exc))
    finally:
        if before is not None:
            try:
                after = _inputs(root, binding_path)
                report.check(
                    "environment_inputs_unchanged",
                    "passed" if after == before else "failed",
                    input_hashes=after,
                )
            except (OSError, ValueError) as exc:
                report.check("environment_inputs_unchanged", "failed", reason=str(exc))
        if report.scope["fresh_rebuild"] == "unobserved":
            report.check(
                "fresh_rebuild",
                "incomplete",
                reason="Fresh target creation was not observed.",
            )
    return report
