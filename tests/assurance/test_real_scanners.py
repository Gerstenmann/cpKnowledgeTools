"""Opt-in execution of explicitly admitted installed scanners; never install.

Set all CPKS_SCANNER_{PYTHON,GITLEAKS,GRANT,ADMISSION} absolute paths to enable
offline protocol tests. Set CPKS_SCANNER_NETWORK=1 separately for the PyPI query.
Absent configuration means not executed; supplied broken configuration fails.
"""

import hashlib
import importlib.metadata
import json
import os
import re
import sys
import sysconfig
from pathlib import Path

import pytest

from cp_knowledge_tools.assurance.admission import binding, load_manifest
from cp_knowledge_tools.assurance.report import Report, persist
from cp_knowledge_tools.assurance.repository import file_hash
from cp_knowledge_tools.assurance.scanners import scan
from cp_knowledge_tools.platform.hashing import canonical_json_bytes, sha256_bytes

PATH_KEYS = (
    "CPKS_SCANNER_PYTHON",
    "CPKS_SCANNER_GITLEAKS",
    "CPKS_SCANNER_GRANT",
    "CPKS_SCANNER_ADMISSION",
)


def _paths_from_environment(environment):
    raw = {key: environment.get(key) for key in PATH_KEYS}
    if all(value is None for value in raw.values()):
        pytest.skip(
            "Real scanners NOT EXECUTED: explicit admitted tool paths are absent."
        )
    if any(not value for value in raw.values()):
        pytest.fail(
            "Incomplete real-scanner opt-in: all four explicit paths are required."
        )
    result = {}
    for key, value in raw.items():
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            pytest.fail(f"Invalid explicit scanner path: {key}")
        if key != "CPKS_SCANNER_ADMISSION" and not os.access(path, os.X_OK):
            pytest.fail(f"Explicit scanner executable is not executable: {key}")
        result[key] = path
    return result


@pytest.fixture(scope="module")
def real_scanners():
    paths = _paths_from_environment(os.environ)
    executables = {
        "cyclonedx": paths["CPKS_SCANNER_PYTHON"],
        "pip-audit": paths["CPKS_SCANNER_PYTHON"],
        "gitleaks": paths["CPKS_SCANNER_GITLEAKS"],
        "grant": paths["CPKS_SCANNER_GRANT"],
    }
    # Validate every supplied tool even when the network test will remain skipped.
    # Admission failures never turn an explicit requested run into a skip.
    try:
        entries = load_manifest(paths["CPKS_SCANNER_ADMISSION"])
        if set(entries) != {"cyclonedx", "pip-audit", "gitleaks", "grant"}:
            pytest.fail("Explicit scanner admission does not cover the complete stack.")
        for name, executable in executables.items():
            binding(executable, entries[name], name)
    except OSError, ValueError, KeyError, TypeError:
        pytest.fail("Explicit scanner admission or artifact binding is invalid.")
    return executables, entries, file_hash(paths["CPKS_SCANNER_ADMISSION"])


def _identities(packages):
    return {
        (re.sub(r"[-_.]+", "-", package["name"]).lower(), package["version"])
        for package in packages
    }


def _installed_identities():
    return _identities(
        [
            {"name": dist.metadata["Name"], "version": dist.version}
            for dist in importlib.metadata.distributions()
        ]
    )


def _completed(report, name, configured):
    executables, entries, manifest_hash = configured
    check = next(check for check in report.checks if check["name"] == name)
    assert check["status"] == "passed", json.dumps(report.payload())
    assert check["execution_status"] == "completed"
    assert check["protocol_status"] == "compatible"
    assert check["tool_version"] == entries[name]["version"]
    assert check["executable_hash"] == entries[name]["executable_sha256"]
    assert check["executable_hash"] == file_hash(
        executables[name].resolve(), max_bytes=512_000_000
    )
    assert check["admission_hash"] == manifest_hash
    assert re.fullmatch(r"[0-9a-f]{64}", check["output_hash"])
    assert check["acceptance"] == "not_evaluated"
    assert report.decision == "not_evaluated"
    if name in {"cyclonedx", "pip-audit"}:
        assert (
            check["environment_hash"]
            == entries[name]["execution"]["site_packages_sha256"]
        )
    return check


def test_real_cyclonedx_to_grant_covers_current_target_environment(
    real_scanners, tmp_path
):
    executables, entries, _ = real_scanners
    expected = _installed_identities()
    assert expected, "Current target interpreter has no distribution inventory"
    report = Report({"operation": "real-scanner-integration"}, {"root": str(tmp_path)})
    generated = scan(
        report,
        tmp_path,
        name="cyclonedx",
        executable=executables["cyclonedx"],
        admission=entries["cyclonedx"],
        timeout=180,
    )
    cyclone = _completed(report, "cyclonedx", real_scanners)
    assert isinstance(generated, bytes)
    components = json.loads(generated)["components"]
    assert _identities(components) == expected
    assert cyclone["target_interpreter"] == sys.executable
    assert cyclone["input_hash"] == sha256_bytes(canonical_json_bytes(sorted(expected)))
    assert cyclone["sbom_hash"] == sha256_bytes(generated)
    assert cyclone["package_coverage"] == "matches_bound_name_version_snapshot"
    target = tmp_path / "sanitized.sbom.json"
    target.write_bytes(generated)
    target.chmod(0o600)
    assert (
        scan(
            report,
            tmp_path,
            name="grant",
            executable=executables["grant"],
            admission=entries["grant"],
            sbom=target,
            timeout=180,
        )
        is None
    )
    grant = _completed(report, "grant", real_scanners)
    assert _identities(grant["summary"]["packages"]) == expected
    assert grant["summary"]["package_count"] == len(expected)
    assert grant["summary"]["policy_evaluated"] is False
    assert grant["package_coverage"] == "matches_bound_name_version_snapshot"
    assert grant["source_hash"] == sha256_bytes(generated)
    assert grant["input_hash"] == sha256_bytes(generated)
    assert report.status == "passed"


def test_real_gitleaks_clean_and_finding_reports_keep_secrets_out_of_evidence(
    real_scanners, tmp_path
):
    executables, entries, _ = real_scanners
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "README.txt").write_text("Synthetic fixture without credentials.\n")
    clean_report = Report({}, {"root": str(clean)})
    scan(
        clean_report,
        clean,
        name="gitleaks",
        executable=executables["gitleaks"],
        admission=entries["gitleaks"],
        timeout=180,
    )
    clean_check = _completed(clean_report, "gitleaks", real_scanners)
    assert clean_check["summary"]["result"] == "no_known_findings"
    assert clean_check["summary"]["findings"] == []

    finding_root = tmp_path / "finding"
    finding_root.mkdir()
    # Assembled at runtime: deterministic harmless detector input, never a credential.
    suffix = hashlib.sha256(b"cpks-noncredential-scanner-fixture").hexdigest()[:36]
    token = "gh" + "p_" + suffix
    (finding_root / "credential_fixture.py").write_text(f'github_token = "{token}"\n')
    report = Report({}, {"root": str(finding_root)})
    scan(
        report,
        finding_root,
        name="gitleaks",
        executable=executables["gitleaks"],
        admission=entries["gitleaks"],
        timeout=180,
    )
    check = _completed(report, "gitleaks", real_scanners)
    assert check["summary"]["result"] == "findings"
    assert check["summary"]["findings"]
    assert any(
        finding["File"].endswith("credential_fixture.py")
        for finding in check["summary"]["findings"]
    )
    retained = persist(report, finding_root).read_text()
    assert token not in retained
    assert all(f'"{key}"' not in retained for key in ("Secret", "Match", "Fragment"))
    assert report.status == "passed"
    assert report.review_status == "review_required"
    assert report.decision == "not_evaluated"


def test_real_cyclonedx_never_executes_target_shadow_modules(
    real_scanners, tmp_path, monkeypatch
):
    executables, entries, _ = real_scanners
    target_site = tmp_path / "target-site"
    target_site.mkdir()
    marker = tmp_path / "target-code-executed"
    harmless_code = f"open({str(marker)!r}, 'w').write('unexpected target execution')\n"
    (target_site / "json.py").write_text(harmless_code)
    (target_site / "sitecustomize.py").write_text(harmless_code)
    (target_site / "startup.pth").write_text("import sitecustomize\n")
    dist = target_site / "synthetic-1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: synthetic\nVersion: 1\n"
    )
    monkeypatch.setattr(
        importlib.metadata,
        "distributions",
        lambda: [importlib.metadata.Distribution.at(dist)],
    )
    # Reproduces the old target-site PYTHONPATH boundary, without changing the
    # real environment or adding the synthetic directory to this process's path.
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(target_site))
    report = Report({}, {})
    generated = scan(
        report,
        tmp_path,
        name="cyclonedx",
        executable=executables["cyclonedx"],
        admission=entries["cyclonedx"],
        timeout=180,
    )
    assert not marker.exists(), "Scanner executed target shadow/startup code"
    check = _completed(report, "cyclonedx", real_scanners)
    assert check["metadata_only"] is True
    assert check["metadata_input_hash"]
    assert isinstance(generated, bytes)
    assert _identities(json.loads(generated)["components"]) == {("synthetic", "1")}


def test_real_grant_unlicensed_package_needs_review_without_automatic_rejection(
    real_scanners, tmp_path
):
    executables, entries, _ = real_scanners
    target = tmp_path / "unlicensed.sbom.json"
    target.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "version": 1,
                "components": [
                    {
                        "type": "library",
                        "name": "cpks-synthetic-unlicensed",
                        "version": "1.0.0",
                    }
                ],
            }
        )
    )
    report = Report({}, {"root": str(tmp_path)})
    scan(
        report,
        tmp_path,
        name="grant",
        executable=executables["grant"],
        admission=entries["grant"],
        sbom=target,
        timeout=180,
    )
    check = _completed(report, "grant", real_scanners)
    assert check["summary"]["unresolved_license_count"] == 1
    assert check["summary"]["policy_evaluated"] is False
    assert check["source_hash"] == file_hash(target)
    assert check["package_coverage"] == "matches_bound_name_version_snapshot"
    assert report.status == "passed"
    assert report.review_status == "review_required"
    assert report.decision == "not_evaluated"
    contextual = next(
        c for c in report.checks if c["name"] == "grant_contextual_review"
    )
    assert contextual["status"] == "review_required"
    assert contextual["required"] is False
    assert report.findings and all(f["severity"] == "review" for f in report.findings)


def test_real_pip_audit_pinned_target_with_explicit_network_authorization(
    real_scanners, tmp_path
):
    if os.environ.get("CPKS_SCANNER_NETWORK") != "1":
        pytest.skip("Real pip-audit NOT EXECUTED: CPKS_SCANNER_NETWORK=1 is required.")
    executables, entries, _ = real_scanners
    expected = {
        package
        for package in _installed_identities()
        if package[0] != "cp-knowledge-tools"
    }
    assert expected, "No installed public target distributions to audit"
    pinned = (
        "\n".join(f"{name}=={version}" for name, version in sorted(expected)) + "\n"
    ).encode()
    report = Report({}, {"root": str(tmp_path)})
    scan(
        report,
        tmp_path,
        name="pip-audit",
        executable=executables["pip-audit"],
        admission=entries["pip-audit"],
        allow_network=True,
        timeout=300,
    )
    check = _completed(report, "pip-audit", real_scanners)
    assert check["input_hash"] == sha256_bytes(pinned)
    assert check["target_interpreter"] == sys.executable
    assert check["vulnerability_service"] == "pypi"
    assert check["service_url"] == "https://pypi.org/pypi/{name}/{version}/json"
    assert "advisory_db_revision" in check
    assert check["package_coverage"] == "matches_bound_name_version_snapshot"
    assert check["summary"]["dependency_count"] == len(expected)
    assert check["summary"]["result"] in {"findings", "no_known_findings"}
    assert "skip_reason" not in json.dumps(check["summary"])
    assert report.status == "passed"
    assert report.decision == "not_evaluated"


def test_no_explicit_real_configuration_is_a_visible_skip():
    with pytest.raises(pytest.skip.Exception, match="NOT EXECUTED"):
        _paths_from_environment({})


def test_partial_explicit_configuration_fails_instead_of_skipping():
    with pytest.raises(pytest.fail.Exception, match="all four"):
        _paths_from_environment({"CPKS_SCANNER_PYTHON": "/not/a/scanner"})


@pytest.mark.parametrize("path", ["relative", "/not/a/real/scanner"])
def test_invalid_explicit_configuration_fails_instead_of_skipping(path):
    with pytest.raises(pytest.fail.Exception, match="Invalid explicit"):
        _paths_from_environment(dict.fromkeys(PATH_KEYS, path))
