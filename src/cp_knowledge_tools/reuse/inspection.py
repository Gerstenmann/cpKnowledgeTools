"""Bounded static evidence extraction. Findings never imply acceptance."""

from __future__ import annotations

import ast
import configparser
import json
import re
import tomllib
from pathlib import Path

from cp_knowledge_tools.platform.hashing import canonical_json_hash, sha256_bytes

from .models import (
    CandidateEvidence,
    CandidateFacts,
    CandidateSnapshot,
    CapabilityNeed,
    InspectionLimits,
    InternalInspection,
    LicenseState,
    ReuseError,
    Symbol,
)
from .paths import collect_files


def _safe_text(value: object) -> str:
    text = str(value)
    scheme = r"[a-zA-Z][a-zA-Z0-9+.-]*://"
    text = re.sub(rf"({scheme})[^/\s]+@", r"\1[redacted]@", text)
    return re.sub(rf"({scheme}[^\s?#]+)[?#][^\s]*", r"\1[redacted]", text)[:2000]


def analyze(files: dict[str, bytes], limits: InspectionLimits):
    evidence = []
    symbols = []
    diagnostics = []
    manifests, licenses, notices, sources, tests, docs = [], [], [], [], [], []
    declared, dependencies, locked, build = set(), set(), set(), set()

    def add(kind, path, value, line=None, heuristic=False):
        if len(evidence) >= limits.max_hits:
            raise ReuseError("evidence hit limit exceeded; narrow inspection scope")
        evidence.append(
            CandidateEvidence(kind, path, _safe_text(value), line, heuristic)
        )

    def strings(value):
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError("expected a string list")
        return value

    for path, raw in sorted(files.items()):
        name = Path(path).name
        lower = name.lower()
        if Path(path).suffix in {".so", ".dll", ".dylib", ".pyd", ".c", ".cpp"}:
            add("native_extension", path, "native file suffix", heuristic=True)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            diagnostics.append(f"binary/non-UTF-8 content not parsed: {path}")
            continue
        if lower.startswith(("license", "copying")):
            licenses.append(path)
            add("license_file", path, "nonempty" if text.strip() else "empty")
        if lower.startswith("notice"):
            notices.append(path)
            add("notice_file", path, "present")
        if lower.startswith(("readme", "changelog")) or Path(path).suffix == ".md":
            docs.append(path)
        if (
            lower.startswith("test")
            or "/tests/" in f"/{path}"
            or lower.endswith(("_test.py", ".test.js", ".spec.ts"))
        ):
            tests.append(path)
        if Path(path).suffix in {".py", ".js", ".ts", ".rs", ".go", ".c", ".cpp"}:
            sources.append(path)
        for n, line in enumerate(text.splitlines(), 1):
            if "copyright" in line.lower():
                add("copyright", path, line.strip(), n)
            declaration = re.fullmatch(
                r"\s*(?:#|//|/\*|\*|<!--)?\s*SPDX-License-Identifier:\s*"
                r"([A-Za-z0-9().+:\- ]+?)\s*(?:\*/|-->)?",
                line,
            )
            if declaration:
                expression = declaration.group(1).strip()
                declared.add(expression)
                add("declared_license", path, expression, n)
        try:
            if lower == "pyproject.toml":
                manifests.append(path)
                data = tomllib.loads(text)
                project = data.get("project", {})
                for key in ("name", "version", "requires-python", "urls", "dynamic"):
                    if key in project:
                        add("package_metadata", path, f"{key}={project[key]}")
                license_value = project.get("license")
                if isinstance(license_value, str):
                    declared.add(license_value)
                    add("declared_license", path, license_value)
                elif license_value:
                    add("license_metadata", path, license_value)
                dependencies.update(strings(project.get("dependencies", [])))
                for group, values in project.get("optional-dependencies", {}).items():
                    for value in strings(values):
                        dependencies.add(f"optional:{group}:{value}")
                for group, values in data.get("dependency-groups", {}).items():
                    add("dependency_group", path, f"{group}={values}")
                backend = data.get("build-system", {})
                build.update(strings(backend.get("requires", [])))
                if backend.get("build-backend"):
                    build.add(backend["build-backend"])
                if "backend-path" in backend:
                    add("install_hook", path, f"backend-path={backend['backend-path']}")
                for key in ("scripts", "gui-scripts", "entry-points"):
                    if project.get(key):
                        add("extension_hook", path, f"{key}={project[key]}")
                poetry = data.get("tool", {}).get("poetry", {})
                if isinstance(poetry.get("license"), str):
                    declared.add(poetry["license"])
                    add("declared_license", path, poetry["license"])
                for package, spec in poetry.get("dependencies", {}).items():
                    dependencies.add(f"poetry:{package}:{spec}")
                if project.get("dynamic"):
                    diagnostics.append(f"dynamic metadata not executed: {path}")
            elif lower.startswith("requirements") and lower.endswith(".txt"):
                manifests.append(path)
                for line in text.splitlines():
                    value = line.strip()
                    if value and not value.startswith("#"):
                        if value.startswith("-"):
                            add("requirements_directive", path, value)
                            diagnostics.append(f"directive not followed: {path}")
                        else:
                            dependencies.add(value)
            elif lower in {
                "uv.lock",
                "poetry.lock",
                "pipfile.lock",
                "package-lock.json",
            }:
                manifests.append(path)
                data = (
                    json.loads(text)
                    if lower.endswith((".json", "file.lock"))
                    else (tomllib.loads(text))
                )
                if lower in {"uv.lock", "poetry.lock"}:
                    for package in data.get("package", []):
                        locked.add(f"{package['name']}=={package.get('version', '?')}")
                        add("lock_entry", path, package)
                elif lower == "pipfile.lock":
                    for group in ("default", "develop"):
                        for package, spec in data.get(group, {}).items():
                            locked.add(f"{package}{spec.get('version', '?')}")
                else:
                    for package, spec in data.get("packages", {}).items():
                        locked.add(f"{package}=={spec.get('version', '?')}")
            elif lower == "package.json":
                manifests.append(path)
                data = json.loads(text)
                for field in ("name", "version", "repository"):
                    if field in data:
                        add("package_metadata", path, f"{field}={data[field]}")
                if isinstance(data.get("license"), str):
                    declared.add(data["license"])
                    add("declared_license", path, data["license"])
                for group in (
                    "dependencies",
                    "devDependencies",
                    "optionalDependencies",
                ):
                    for package, spec in data.get(group, {}).items():
                        dependencies.add(f"{group}:{package}@{spec}")
                for script, body in data.get("scripts", {}).items():
                    add("package_script", path, f"{script}={body}")
                    if script in {"preinstall", "install", "postinstall", "prepare"}:
                        add("install_hook", path, script)
            elif lower == "setup.cfg":
                manifests.append(path)
                config = configparser.ConfigParser(interpolation=None)
                config.read_string(text)
                if config.has_option("metadata", "license"):
                    value = config.get("metadata", "license")
                    declared.add(value)
                    add("declared_license", path, value)
                if config.has_option("options", "install_requires"):
                    dependencies.update(
                        config.get("options", "install_requires").splitlines()
                    )
            elif lower in {"cargo.toml", "go.mod", "pipfile", "yarn.lock", "pdm.lock"}:
                manifests.append(path)
                diagnostics.append(f"manifest inventoried, not parsed: {path}")
            if lower == "setup.py":
                manifests.append(path)
                add("install_hook", path, "setup.py exists; never executed")
            if Path(path).suffix == ".py":
                tree = ast.parse(text, filename=path)
                for node in ast.walk(tree):
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):
                        if len(symbols) >= limits.max_hits:
                            raise ReuseError("symbol hit limit exceeded")
                        symbols.append(
                            Symbol(path, node.name, type(node).__name__, node.lineno)
                        )
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            add("import", path, alias.name, node.lineno)
                    if isinstance(node, ast.ImportFrom):
                        add("import", path, node.module or "relative", node.lineno)
                    if lower == "setup.py" and isinstance(node, ast.Call):
                        for keyword in node.keywords:
                            if keyword.arg == "install_requires":
                                try:
                                    dependencies.update(
                                        strings(ast.literal_eval(keyword.value))
                                    )
                                except ValueError, TypeError:
                                    diagnostics.append(
                                        f"dynamic setup dependencies: {path}"
                                    )
            for category, pattern in (
                ("filesystem_access", r"\b(open|pathlib|shutil|os\.remove)\b"),
                ("network_access", r"\b(requests|urllib|httpx|socket|fetch)\b"),
                ("credential_integration", r"\b(keyring|environ|getenv|credential)\b"),
                ("native_extension", r"\b(ctypes|cffi|Extension|maturin)\b"),
                ("process_execution", r"\b(subprocess|os\.system|exec|eval)\b"),
                ("extension_hook", r"\b(entry_points|pluggy|importlib)\b"),
                ("bootstrap", r"\b(curl|wget|postinstall)\b"),
            ):
                match = re.search(pattern, text)
                if match:
                    add(category, path, match.group(), heuristic=True)
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            SyntaxError,
            configparser.Error,
            RecursionError,
        ) as exc:
            if isinstance(exc, ReuseError):
                raise
            diagnostics.append(
                f"static parse incomplete ({type(exc).__name__}): {path}"
            )
    state = (
        LicenseState.CONFLICTING
        if len(declared) > 1
        else LicenseState.DECLARED
        if declared
        else LicenseState.UNKNOWN
    )
    return dict(
        files=tuple(files),
        source_files=tuple(sources),
        test_files=tuple(tests),
        documentation_files=tuple(docs),
        manifests=tuple(manifests),
        license_files=tuple(licenses),
        notice_files=tuple(notices),
        declared_licenses=tuple(sorted(declared)),
        license_state=state,
        direct_dependencies=tuple(sorted(_safe_text(d) for d in dependencies if d)),
        locked_dependencies=tuple(sorted(_safe_text(d) for d in locked)),
        build_system=tuple(sorted(_safe_text(d) for d in build)),
        evidence=tuple(evidence),
        symbols=tuple(symbols),
        diagnostics=tuple(diagnostics),
    )


def inspect_candidate(snapshot: CandidateSnapshot) -> CandidateFacts:
    files, notes = collect_files(snapshot.root, snapshot.limits)
    fingerprints = tuple((p, sha256_bytes(data)) for p, data in files.items())
    if (
        fingerprints != snapshot.file_fingerprints
        or canonical_json_hash(fingerprints) != snapshot.fingerprint
        or snapshot.candidate_id
        != canonical_json_hash(
            {
                "source": snapshot.source.location,
                "snapshot": snapshot.fingerprint,
                "commit": snapshot.commit,
            }
        )[:24]
    ):
        raise ReuseError("snapshot fingerprint drift")
    facts = analyze(files, snapshot.limits)
    facts["diagnostics"] += snapshot.diagnostics + notes
    return CandidateFacts(snapshot=snapshot, **facts)


def inspect_internal(
    repository: Path,
    need: CapabilityNeed,
    *,
    limits: InspectionLimits = InspectionLimits(),
) -> InternalInspection:
    from .acquisition import repository_commit
    from .paths import verified_root

    repository = verified_root(repository)
    repository_commit(repository)
    files, notes = collect_files(repository, limits)
    facts = analyze(files, limits)
    matches = []
    for path, data in files.items():
        for n, line in enumerate(
            data.decode("utf-8", errors="replace").splitlines(), 1
        ):
            for term in need.search_terms:
                if (
                    term.casefold() in line.casefold()
                    or term.casefold() in path.casefold()
                ):
                    matches.append(CandidateEvidence("literal_match", path, term, n))
                    if len(matches) >= limits.max_hits:
                        break
            if len(matches) >= limits.max_hits:
                break
        if len(matches) >= limits.max_hits:
            notes += ("search hit limit reached; results partial",)
            break
    return InternalInspection(
        repository=str(repository),
        need=need,
        fingerprint=canonical_json_hash({p: sha256_bytes(d) for p, d in files.items()}),
        files=tuple(files),
        matches=tuple(matches),
        symbols=facts["symbols"],
        manifests=facts["manifests"],
        direct_dependencies=facts["direct_dependencies"],
        tests=facts["test_files"],
        diagnostics=notes + facts["diagnostics"],
    )
