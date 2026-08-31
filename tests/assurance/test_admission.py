"""Admission evidence binds tool bytes before any external scanner execution."""

import json
import platform
import sys
from pathlib import Path

import pytest

from cp_knowledge_tools.assurance import scanners
from cp_knowledge_tools.assurance.admission import binding, load_manifest, tree_hash
from cp_knowledge_tools.assurance.execution import ProcessResult
from cp_knowledge_tools.assurance.report import Report
from cp_knowledge_tools.assurance.repository import file_hash


def _entry(executable, *, name="gitleaks", execution=None):
    return {
        "tool_id": name,
        "version": "1.2.3",
        "executable_sha256": file_hash(executable),
        "platform": f"{platform.system().lower()}-{platform.machine()}",
        "license": "MIT",
        "upstream": "https://example.invalid/scanner",
        "accepted_use_context": "Synthetic nonexecuting admission fixture.",
        "verified_at": "2026-08-31T10:00:00+00:00",
        "assessment_ref": "fixture-assessment",
        "disposition": "WRAP",
        "acceptance": "accepted_with_conditions",
        "conditions": ["Fixture only; never a real scanner admission."],
        "execution": execution or {"kind": "binary"},
    }


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / "candidate"
    path.write_text("This fixture is not executable code.\n")
    return path


def test_manifest_load_binds_source_hash_and_missing_manifest_is_not_evidence(
    tmp_path, executable
):
    manifest = tmp_path / "admission.json"
    with pytest.raises(FileNotFoundError):
        load_manifest(manifest)
    document = {
        "schema_version": "cpks.scanner-admission/1",
        "tools": [_entry(executable)],
    }
    manifest.write_text(json.dumps(document))
    entries = load_manifest(manifest)
    assert set(entries) == {"gitleaks"}
    assert entries["gitleaks"]["_manifest_hash"] == file_hash(manifest)
    assert entries["gitleaks"]["acceptance"] == "accepted_with_conditions"


@pytest.mark.parametrize(
    "change",
    [
        {"tool_id": "unknown"},
        {"executable_sha256": "unbound"},
        {"version": ""},
        {"verified_at": "2026-08-31T10:00:00"},
        {"acceptance": "review_required"},
        {"disposition": "ADAPT"},
        {"conditions": "not a list"},
        {"execution": None},
    ],
)
def test_incomplete_or_unreviewed_manifest_entry_is_rejected(
    tmp_path, executable, change
):
    manifest = tmp_path / "admission.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "cpks.scanner-admission/1",
                "tools": [{**_entry(executable), **change}],
            }
        )
    )
    with pytest.raises(ValueError):
        load_manifest(manifest)


@pytest.mark.parametrize("content", ["{broken", "[]", '{"tools": []}'])
def test_malformed_manifest_cannot_be_loaded(tmp_path, content):
    path = tmp_path / "admission.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_manifest(path)


def test_duplicate_tool_admission_is_ambiguous(tmp_path, executable):
    path = tmp_path / "admission.json"
    entry = _entry(executable)
    path.write_text(
        json.dumps(
            {
                "schema_version": "cpks.scanner-admission/1",
                "tools": [entry, entry],
            }
        )
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(path)


@pytest.mark.parametrize("problem", ["missing", "hash", "identity", "path", "platform"])
def test_unbound_candidate_never_reaches_process_execution(
    executable, tmp_path, monkeypatch, problem
):
    def forbidden(*args, **kwargs):
        pytest.fail("unbound candidate reached subprocess transport")

    monkeypatch.setattr(scanners, "execute", forbidden)
    entry = _entry(executable)
    if problem == "missing":
        entry = None
    elif problem == "hash":
        executable.write_text("changed after admission\n")
    elif problem == "identity":
        entry["tool_id"] = "grant"
    elif problem == "path":
        executable = Path("relative-candidate")
    else:
        entry["platform"] = "unsupported-platform"
    report = Report({}, {})
    assert (
        scanners.scan(
            report,
            tmp_path,
            name="gitleaks",
            executable=executable,
            admission=entry,
        )
        is None
    )
    assert report.status == "incomplete"
    assert report.decision == "not_evaluated"


def test_version_mismatch_stops_after_probe_without_running_scan(
    executable, tmp_path, monkeypatch
):
    calls = []

    def mismatching_probe(command, *args, **kwargs):
        calls.append(command)
        assert command == [str(executable), "--version"]
        return ProcessResult(0, b"gitleaks version 9.8.7\n", 0.01)

    monkeypatch.setattr(scanners, "execute", mismatching_probe)
    report = Report({}, {})
    scanners.scan(
        report,
        tmp_path,
        name="gitleaks",
        executable=executable,
        admission=_entry(executable),
    )
    assert len(calls) == 1
    assert report.status == "incomplete"
    assert "version differs" in report.checks[0]["reason"]
    assert report.decision == "not_evaluated"


@pytest.mark.parametrize(
    "filename",
    ["startup.pth", "module.pyc", "module.pyo", "sitecustomize.py", "usercustomize.py"],
)
def test_environment_rejects_startup_and_bytecode_files(tmp_path, filename):
    site = tmp_path / "site-packages"
    site.mkdir()
    (site / "library.py").write_text("value = 1\n")
    initial = tree_hash(site)
    (site / filename).write_text("unreviewed startup content\n")
    with pytest.raises(ValueError, match="startup or bytecode"):
        tree_hash(site)
    (site / filename).unlink()
    assert tree_hash(site) == initial


@pytest.mark.parametrize("kind", ["file", "directory", "root"])
def test_environment_rejects_symlinks(tmp_path, kind):
    site = tmp_path / "site-packages"
    site.mkdir()
    original = site / "library.py"
    original.write_text("value = 1\n")
    if kind == "file":
        (site / "linked.py").symlink_to(original)
    elif kind == "directory":
        (site / "linked").symlink_to(tmp_path, target_is_directory=True)
    else:
        link = tmp_path / "site-link"
        link.symlink_to(site, target_is_directory=True)
        site = link
    with pytest.raises(ValueError, match="symlink|real directory"):
        tree_hash(site)


def test_tree_fingerprint_detects_content_changes_but_not_installer_record(tmp_path):
    site = tmp_path / "site-packages"
    metadata = site / "fixture-1.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text("Name: fixture\nVersion: 1.0\n")
    record = metadata / "RECORD"
    record.write_text("relocatable bookkeeping\n")
    before = tree_hash(site)
    record.write_text("different installer bookkeeping\n")
    assert tree_hash(site) == before
    (metadata / "METADATA").write_text("Name: fixture\nVersion: 2.0\n")
    assert tree_hash(site) != before


@pytest.fixture
def module_environment(tmp_path):
    root = tmp_path / "isolated-scanner"
    executable = root / "bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text("Nonexecuting synthetic interpreter bytes.\n")
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    site = (
        root
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    site.mkdir(parents=True)
    (site / "scanner.py").write_text("value = 1\n")
    (root / "pyvenv.cfg").write_text(
        f"home = {executable.parent}\n"
        f"include-system-site-packages = false\nversion = {version}\n"
    )
    entry = _entry(
        executable,
        name="cyclonedx",
        execution={
            "kind": "python_module",
            "python_version": version,
            "site_packages_sha256": tree_hash(site),
        },
    )
    entry["_manifest_hash"] = "f" * 64
    return executable, site, entry


@pytest.mark.parametrize(
    "name,module", [("cyclonedx", "cyclonedx_py"), ("pip-audit", "pip_audit")]
)
def test_isolated_python_binding_has_only_fixed_module_prefix(
    module_environment, name, module
):
    executable, site, entry = module_environment
    entry["tool_id"] = name
    prefix, evidence = binding(executable, entry, name)
    assert prefix == [str(executable), "-I", "-B", "-m", module]
    assert evidence == {
        "executable_hash": file_hash(executable),
        "admission_hash": "f" * 64,
        "environment_hash": tree_hash(site),
    }


def test_environment_tampering_blocks_even_version_probe(
    module_environment, tmp_path, monkeypatch
):
    executable, site, entry = module_environment
    (site / "scanner.py").write_text("value = 2\n")

    def forbidden(*args, **kwargs):
        pytest.fail("changed scanner environment reached execution")

    monkeypatch.setattr(scanners, "execute", forbidden)
    report = Report({}, {})
    scanners.scan(
        report, tmp_path, name="cyclonedx", executable=executable, admission=entry
    )
    assert report.status == "incomplete"
    assert "environment fingerprint differs" in report.checks[0]["reason"]


@pytest.mark.parametrize(
    "before,after",
    [
        ("include-system-site-packages = false", "include-system-site-packages = true"),
        ("home = ", "home = /unreviewed"),
    ],
)
def test_venv_configuration_cannot_expand_bound_environment(
    module_environment, before, after
):
    executable, _, entry = module_environment
    config = executable.parent.parent / "pyvenv.cfg"
    config.write_text(config.read_text().replace(before, after))
    with pytest.raises(ValueError, match="scanner venv"):
        binding(executable, entry, "cyclonedx")
