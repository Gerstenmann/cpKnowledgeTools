"""Finite repository command sequence shared by hosted CI and local verification.

No live governance, scanner, provider or remote-write client is invoked here.
The caller supplies an admitted uv; this is orchestration, not a sandbox.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

BASELINE = "artifacts/tests/source_to_knowledge/experience-v1-2-final-validated"
FIXTURE_RUNNER = "scripts/cp_tools/run_minecraft_esports_mvp.py"

IDENTITY = (
    "import json,platform,sys,sysconfig; print(json.dumps({"
    "'version':platform.python_version(),'sys_version':sys.version,"
    "'implementation':platform.python_implementation(),"
    "'machine':platform.machine(),'system':platform.system(),"
    "'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
    "'soabi':sysconfig.get_config_var('SOABI'),"
    "'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}))"
)

BUILD_EVIDENCE = (
    "import json,tomllib; from email.parser import Parser; "
    "from importlib.metadata import distribution; from pathlib import Path; "
    "data=tomllib.loads(Path('pyproject.toml').read_text()); "
    "build=data['build-system']; project=data['project']; "
    "wheel=distribution(project['name']).read_text('WHEEL') or ''; "
    "generator=Parser().parsestr(wheel).get('Generator'); "
    "print(json.dumps({"
    "'declared_build_backend':build['build-backend'],"
    "'declared_build_requires':build['requires'],"
    "'installed_distribution':project['name'],"
    "'installed_wheel_generator':generator,"
    "'generator_observation':"
    "'installed_distribution_metadata' if generator else 'unknown_not_recorded',"
    "'wheel_build_dependency_version':None,"
    "'wheel_build_dependency_observation':'unknown_not_directly_observed'}))"
)


def commands(uv: str, base: str, python: str, *, existing: bool) -> list[list[str]]:
    common = [
        uv,
        "--no-config",
        "--no-progress",
        "--no-python-downloads",
        "--no-managed-python",
    ]
    selection = [
        "--python",
        base,
        "--default-index",
        "https://pypi.org/simple",
        "--keyring-provider",
        "disabled",
    ]
    sync = ["sync", "--locked", "--extra", "dev", "--no-build"]
    if existing:
        sync += ["--check", "--offline"]
    return [
        common + ["lock", "--check", "--offline"] + selection,
        common + sync + selection,
        common + ["pip", "check", "--python", python, "--offline"],
        [python, "-I", "-B", "-c", BUILD_EVIDENCE],
        [python, "-I", "-B", "-c", IDENTITY],
        [python, "-B", "scripts/ci/check_workflow.py"],
        [python, "-B", FIXTURE_RUNNER, "--output-root", BASELINE],
        [python, "-B", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
        [
            python,
            "-B",
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "tests/frontier",
            "src/cp_knowledge_tools/assurance",
            "tests/assurance",
            "tests/hooks",
            "scripts/ci",
            "tests/ci",
        ],
        [
            python,
            "-B",
            "-m",
            "mypy",
            "--follow-imports=skip",
            "--cache-dir=/dev/null",
            "tests/frontier",
        ],
        [
            python,
            "-B",
            "-m",
            "mypy",
            "--follow-imports=skip",
            "--ignore-missing-imports",
            "--cache-dir=/dev/null",
            "src/cp_knowledge_tools/assurance",
            "scripts/ci",
        ],
        ["git", "diff", "--check"],
    ]


def snapshot(root: Path, env: dict[str, str]) -> dict:
    def git(*args: str) -> bytes:
        return subprocess.check_output(
            ["git", "--no-optional-locks", *args], cwd=root, env=env, timeout=30
        )

    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    hashes = {}
    for name in filter(None, paths.decode().split("\0")):
        path = root / name
        if path.is_symlink():
            kind, data = "symlink", os.fsencode(os.readlink(path))
        elif path.is_file():
            kind, data = "file", path.read_bytes()
        else:
            kind, data = "missing", b""
        hashes[name] = {
            "kind": kind,
            "mode": path.lstat().st_mode if kind != "missing" else None,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "index": hashlib.sha256(git("ls-files", "--stage", "-z")).hexdigest(),
        "status": git("status", "--porcelain", "--untracked-files=no").decode(),
        "files": hashes,
    }


def verify_identity(identity: dict, pin: str, host: str) -> None:
    if (
        identity["version"] != pin
        or identity["implementation"] != "CPython"
        or identity["gil_disabled"]
        or not identity["soabi"].startswith("cpython-314-")
        or (
            host == "linux"
            and (
                identity["system"] != "Linux"
                or identity["machine"] != "x86_64"
                or identity["soabi"] != "cpython-314-x86_64-linux-gnu"
            )
        )
    ):
        raise ValueError("Python patch/implementation/architecture/ABI mismatch")


def verify_build_evidence(evidence: dict) -> None:
    expected = {
        "declared_build_backend",
        "declared_build_requires",
        "installed_distribution",
        "installed_wheel_generator",
        "generator_observation",
        "wheel_build_dependency_version",
        "wheel_build_dependency_observation",
    }
    strings = [
        evidence.get("declared_build_backend"),
        evidence.get("installed_distribution"),
    ]
    requirements = evidence.get("declared_build_requires")
    generator = evidence.get("installed_wheel_generator")
    generator_observation = evidence.get("generator_observation")
    if (
        set(evidence) != expected
        or not all(
            isinstance(value, str) and 0 < len(value) <= 200 for value in strings
        )
        or not isinstance(requirements, list)
        or not requirements
        or len(requirements) > 20
        or not all(
            isinstance(value, str) and 0 < len(value) <= 200
            for value in requirements
        )
        or generator is not None
        and (not isinstance(generator, str) or not 0 < len(generator) <= 200)
        or generator_observation
        != (
            "installed_distribution_metadata"
            if generator is not None
            else "unknown_not_recorded"
        )
        or evidence.get("wheel_build_dependency_version") is not None
        or evidence.get("wheel_build_dependency_observation")
        != "unknown_not_directly_observed"
    ):
        raise ValueError("Build evidence is incomplete or unbounded")


def run(args: argparse.Namespace, root: Path) -> None:
    pin = (root / ".python-version").read_text().strip()
    if not re.fullmatch(r"3\.14\.\d+", pin):
        raise ValueError("Exact CPython patch required")
    identity = {
        "version": platform.python_version(),
        "sys_version": sys.version,
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "system": platform.system(),
        "soabi": sysconfig.get_config_var("SOABI"),
        "gil_disabled": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    }
    verify_identity(identity, pin, args.host)
    print(json.dumps({"bootstrap_python": identity}), flush=True)
    uv = args.uv or shutil.which("uv")
    if not uv or not Path(uv).is_absolute():
        raise ValueError("An explicitly installed admitted uv is required")
    environment = Path(args.environment or root / ".venv").absolute()
    environment.relative_to(root)
    if any(p.is_symlink() for p in [environment, *environment.parents]):
        raise ValueError("Environment path must not contain symlinks")
    environment = environment.resolve()
    environment.relative_to(root)
    if args.existing and args.host != "local":
        raise ValueError("Existing-environment checks are local only")
    if args.offline and args.host != "local":
        raise ValueError("Offline cache reproduction is local only")
    if environment.exists() != args.existing:
        raise ValueError("Fresh target must be absent; existing target must exist")
    python = str(environment / "bin/python")
    # Do not forward Owner root configuration, scanner paths, tokens, Git/uv
    # overrides or Python startup settings to repository subprocesses.
    env = {
        k: os.environ[k]
        for k in ["PATH", "HOME", "TMPDIR", "LD_LIBRARY_PATH"]
        if k in os.environ
    }
    env.update(
        {
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(root / "src"),
            "MYPYPATH": str(root / "src"),
            "UV_PROJECT_ENVIRONMENT": str(environment),
            "UV_CACHE_DIR": str(root / "artifacts/ci/cache"),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    if args.offline:
        env["UV_OFFLINE"] = "1"
    before = snapshot(root, env)
    if args.host == "linux" and before["status"]:
        raise ValueError("Hosted checkout must start with no tracked changes")
    try:
        version = subprocess.check_output(
            [uv, "--version"], cwd=root, env=env, text=True, timeout=30
        ).strip()
        if not re.fullmatch(r"uv 0\.12\.7(?: \([^\r\n]+\))?", version):
            raise ValueError("Expected admitted uv 0.12.7")
        print(version, flush=True)
        for argv in commands(uv, sys.executable, python, existing=args.existing):
            print("+ " + shlex.join(argv), flush=True)
            if argv[1:5] == ["-I", "-B", "-c", BUILD_EVIDENCE]:
                output = subprocess.check_output(
                    argv, cwd=root, env=env, text=True, timeout=30
                )
                evidence = json.loads(output)
                verify_build_evidence(evidence)
                print(json.dumps({"build_evidence": evidence}), flush=True)
            elif (
                len(argv) > 2
                and argv[2] == FIXTURE_RUNNER
                and (root / BASELINE).exists()
            ):
                if not args.existing or not all(
                    (root / BASELINE / name).is_file()
                    for name in [
                        "derived/experience_projection.json",
                        "publication/KO-GT-ME-ESPORTS-PILOT@0.1.md",
                    ]
                ):
                    raise ValueError("Synthetic baseline target must be absent")
                print(
                    "Existing local synthetic baseline preserved; no rebuild claim",
                    flush=True,
                )
            elif argv[1:5] == ["-I", "-B", "-c", IDENTITY]:
                output = subprocess.check_output(
                    argv, cwd=root, env=env, text=True, timeout=30
                )
                actual = json.loads(output)
                verify_identity(actual, pin, args.host)
                if Path(actual["prefix"]) != environment:
                    raise ValueError(
                        "Verification interpreter is not the selected venv"
                    )
                print(output, end="", flush=True)
            else:
                subprocess.run(argv, cwd=root, env=env, check=True, timeout=1500)
    finally:
        after = snapshot(root, env)
        if after != before:
            raise ValueError("Repository inputs changed; no reset attempted")
        print("Repository inputs, HEAD and index unchanged", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["linux", "local"], required=True)
    parser.add_argument(
        "--uv", help="Absolute admitted executable; CI uses setup-uv PATH"
    )
    parser.add_argument(
        "--environment", help="Repository-local venv; CI defaults to .venv"
    )
    parser.add_argument(
        "--existing",
        action="store_true",
        help="Local nonmutating sync --check; never a fresh-build claim",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Local fresh replay from a separately prepared cache only",
    )
    run(parser.parse_args(), Path(__file__).resolve().parents[2])
