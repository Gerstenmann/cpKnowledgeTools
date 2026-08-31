"""Required scanner orchestration, evidence retention and decision boundaries."""

import json
import subprocess
from pathlib import Path

import pytest

from cp_knowledge_tools.assurance import supply
from cp_knowledge_tools.assurance.report import Report, persist_blob
from cp_knowledge_tools.cli.cpks import main

SCANNER_NAMES = ("cyclonedx", "pip-audit", "grant", "gitleaks")
SBOM = json.dumps(
    {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [{"type": "library", "name": "fixture", "version": "1"}],
    }
).encode()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("artifacts/\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.1"\ndependencies=[]\n'
    )
    for args in (
        ["init", "-b", "test"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


@pytest.fixture
def stack(monkeypatch):
    """Replace only the external adapter: orchestration uses real report/filesystem."""
    from cp_knowledge_tools.assurance import admission, scanners

    calls = []
    manifests = []
    entries = {
        name: {"tool_id": name, "_manifest_hash": "fixture"} for name in SCANNER_NAMES
    }

    def load(path):
        manifests.append(path)
        return entries

    def scan(report, root, *, name, executable, **kwargs):
        assert kwargs["admission"] is entries[name]
        call = {"name": name, "root": root, "executable": executable, **kwargs}
        if name == "grant":
            sbom = kwargs["sbom"]
            call["input_bytes"] = sbom.read_bytes()
            call["input_mode"] = sbom.stat().st_mode & 0o777
            call["directory_mode"] = sbom.parent.stat().st_mode & 0o777
        calls.append(call)
        report.check(name, "passed", kind="external_tool_finding")
        return SBOM if name == "cyclonedx" else None

    monkeypatch.setattr(admission, "load_manifest", load)
    monkeypatch.setattr(scanners, "scan", scan)
    return {
        "calls": calls,
        "manifests": manifests,
        "tools": {name: Path("/admitted-tools") / name for name in SCANNER_NAMES},
    }


@pytest.mark.parametrize("status", ["review_required", "external_evidence"])
def test_review_or_reference_is_not_completed_required_evidence(status):
    report = Report({}, {})
    report.check("context", status)
    report.check("later_success", "passed")
    assert report.status == "incomplete"
    assert report.exit_code == 2
    assert report.review_status == "review_required"
    assert report.decision == "not_evaluated"
    assert report.checks[0]["required"] is True


@pytest.mark.parametrize("failure", ["failed", "incomplete"])
def test_contextual_review_never_masks_required_problem(failure):
    report = Report({}, {})
    report.check("scanner", failure)
    report.check("license_legal", "review_required", required=False)
    report.check("reference", "external_evidence", required=False)
    report.check("later_success", "passed")
    assert report.status == failure
    assert report.review_status == "review_required"


@pytest.mark.parametrize("profile", ["admission", "deep-review"])
def test_all_four_scanners_are_required_and_missing_tools_stay_incomplete(
    repo, profile
):
    report = supply.supply_chain(repo, profile=profile)
    checks = {check["name"]: check for check in report.checks}
    assert report.status == "incomplete"
    assert all(checks[name]["status"] == "incomplete" for name in SCANNER_NAMES)
    assert all(checks[name]["required"] for name in SCANNER_NAMES)
    assert checks["dependency_inventory"]["status"] == "passed"
    assert checks["input_stability"]["status"] == "passed"


@pytest.mark.parametrize("problem", [FileNotFoundError, ValueError])
def test_missing_or_invalid_admission_executes_no_scanner(repo, monkeypatch, problem):
    from cp_knowledge_tools.assurance import admission, scanners

    def no_manifest(path):
        raise problem("untrusted details are not report evidence")

    def must_not_scan(*args, **kwargs):
        pytest.fail("scanner adapter called without valid admission")

    monkeypatch.setattr(admission, "load_manifest", no_manifest)
    monkeypatch.setattr(scanners, "scan", must_not_scan)
    report = supply.supply_chain(
        repo,
        profile="admission",
        tools={name: Path("/tools") / name for name in SCANNER_NAMES},
    )
    assert report.status == "incomplete"
    assert "untrusted details" not in json.dumps(report.payload())
    assert all(
        check["status"] == "incomplete"
        for check in report.checks
        if check["name"] in SCANNER_NAMES
    )


@pytest.mark.parametrize("profile", ["admission", "deep-review"])
def test_completed_stack_hands_sbom_to_grant_and_does_not_grant_acceptance(
    repo, stack, profile
):
    report = supply.supply_chain(
        repo, profile=profile, tools=stack["tools"], allow_network=True, timeout=17
    )
    assert report.status == "passed"
    assert report.status_scope == "required_technical_checks"
    assert report.review_status == "review_required"
    assert report.decision == "not_evaluated"
    assert report.checks[0]["inventory"]["acceptance"] == "not_evaluated"
    assert [call["name"] for call in stack["calls"]] == list(SCANNER_NAMES)
    assert all(call["timeout"] == 17 for call in stack["calls"])
    grant = next(call for call in stack["calls"] if call["name"] == "grant")
    assert grant["input_bytes"] == SBOM
    assert grant["input_mode"] == 0o600
    assert grant["directory_mode"] == 0o700
    assert not grant["sbom"].parent.exists()
    assert not (repo / "artifacts").exists()
    assert stack["manifests"] == [repo / "config/assurance/scanner-admission.json"]
    checks = {check["name"]: check for check in report.checks}
    for name in ("provenance", "candidate_health", "license_legal", "human_acceptance"):
        assert checks[name]["status"] == "review_required"
        assert checks[name]["required"] is False


def test_retention_is_private_and_explicit_grant_input_is_never_raw_retained(
    repo, stack, tmp_path
):
    explicit = tmp_path / "explicit.json"
    supplied = json.loads(SBOM)
    supplied["components"][0]["name"] = "EXPLICIT_SENTINEL"
    explicit.write_text(json.dumps(supplied))
    manifest = tmp_path / "reviewed-admission.json"
    report = supply.supply_chain(
        repo,
        profile="admission",
        tools=stack["tools"],
        admission_manifest=manifest,
        sbom=explicit,
        retain_sbom=True,
    )
    grant = next(call for call in stack["calls"] if call["name"] == "grant")
    assert grant["sbom"] == explicit
    assert grant["input_bytes"] == explicit.read_bytes()
    assert explicit.exists()
    assert stack["manifests"] == [manifest]
    assert report.status == "passed"
    assert len(report.evidence_refs) == 1
    retained = Path(report.evidence_refs[0])
    assert retained.parent == repo / "artifacts/assurance"
    assert retained.name.endswith(".sbom.json")
    assert retained.read_bytes() == SBOM
    assert retained.stat().st_mode & 0o077 == 0
    check = next(check for check in report.checks if check["name"] == "sbom_retention")
    assert check["source"] == "generated_cyclonedx"
    assert check["grant_input"] == "explicit_sbom"
    assert "EXPLICIT_SENTINEL" not in json.dumps(report.payload())


def test_missing_generated_sbom_blocks_grant_but_other_tools_continue(repo, stack):
    tools = {name: path for name, path in stack["tools"].items() if name != "cyclonedx"}
    report = supply.supply_chain(repo, profile="admission", tools=tools)
    assert report.status == "incomplete"
    assert [call["name"] for call in stack["calls"]] == ["pip-audit", "gitleaks"]
    assert (
        next(check for check in report.checks if check["name"] == "grant")["status"]
        == "incomplete"
    )


def test_failed_cyclonedx_does_not_retain_or_imply_complete_stack(
    repo, stack, monkeypatch
):
    from cp_knowledge_tools.assurance import scanners

    original = scanners.scan

    def failed_cyclonedx(report, root, *, name, **kwargs):
        if name == "cyclonedx":
            report.check(name, "incomplete", reason="malformed scanner protocol")
            return None
        return original(report, root, name=name, **kwargs)

    monkeypatch.setattr(scanners, "scan", failed_cyclonedx)
    report = supply.supply_chain(
        repo, profile="admission", tools=stack["tools"], retain_sbom=True
    )
    assert report.status == "incomplete"
    checks = {check["name"]: check for check in report.checks}
    assert checks["grant"]["status"] == "incomplete"
    assert checks["sbom_retention"]["status"] == "incomplete"
    assert checks["pip-audit"]["status"] == "passed"
    assert checks["gitleaks"]["status"] == "passed"
    assert report.evidence_refs == []
    assert not (repo / "artifacts").exists()


@pytest.mark.parametrize("timeout", [0, 3601])
def test_supply_rejects_unbounded_timeout_before_scanner_execution(
    repo, stack, timeout
):
    with pytest.raises(ValueError, match="between 1 and 3600"):
        supply.supply_chain(
            repo, profile="admission", tools=stack["tools"], timeout=timeout
        )
    assert stack["calls"] == []


def test_interpreter_inventory_drift_prevents_technical_pass(repo, stack, monkeypatch):
    initial = supply.inventory(repo)
    inventories = iter([initial, {**initial, "installed": []}])
    monkeypatch.setattr(supply, "inventory", lambda root: next(inventories))
    report = supply.supply_chain(repo, profile="admission", tools=stack["tools"])
    assert report.status == "incomplete"
    stability = next(
        check for check in report.checks if check["name"] == "input_stability"
    )
    assert stability["repository_unchanged"] is True
    assert stability["inventory_unchanged"] is False


def test_repository_drift_during_scanning_prevents_pass(repo, stack, monkeypatch):
    from cp_knowledge_tools.assurance import scanners

    original = scanners.scan

    def mutate(report, root, *, name, **kwargs):
        if name == "gitleaks":
            (root / "new.py").write_text("changed = True\n")
        return original(report, root, name=name, **kwargs)

    monkeypatch.setattr(scanners, "scan", mutate)
    report = supply.supply_chain(repo, profile="admission", tools=stack["tools"])
    assert report.status == "incomplete"
    stability = next(
        check for check in report.checks if check["name"] == "input_stability"
    )
    assert stability["repository_unchanged"] is False
    assert stability["inventory_unchanged"] is True


def test_research_never_loads_admission_or_executes_tools(repo, monkeypatch):
    from cp_knowledge_tools.assurance import admission, scanners

    def forbidden(*args, **kwargs):
        pytest.fail("static research crossed the scanner boundary")

    monkeypatch.setattr(admission, "load_manifest", forbidden)
    monkeypatch.setattr(scanners, "scan", forbidden)
    assert supply.supply_chain(repo, profile="research").status == "passed"
    with pytest.raises(ValueError, match="static"):
        supply.supply_chain(repo, profile="research", tools={"grant": Path("/tool")})
    assert not (repo / "artifacts").exists()


def test_private_sbom_persistence_does_not_clobber_or_follow_symlinks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    first = persist_blob(root, SBOM)
    second = persist_blob(root, SBOM)
    assert first != second
    assert first.read_bytes() == SBOM
    assert first.stat().st_mode & 0o077 == 0
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "artifacts").symlink_to(root / "artifacts", target_is_directory=True)
    with pytest.raises(OSError):
        persist_blob(outside, SBOM)
    with pytest.raises(ValueError, match="bounded"):
        persist_blob(root, b"x" * 10_000_001)


def test_no_evidence_and_retention_conflict_before_execution(repo, capsys, monkeypatch):
    from cp_knowledge_tools.assurance import cli

    def forbidden(*args, **kwargs):
        pytest.fail("conflicting no-write request reached execution")

    monkeypatch.setattr(cli, "supply_chain", forbidden)
    assert (
        main(
            [
                "assurance",
                "supply-chain",
                "--repo-root",
                str(repo),
                "--profile",
                "admission",
                "--no-evidence",
                "--retain-sbom",
            ]
        )
        == 2
    )
    assert "--no-evidence" in capsys.readouterr().err
    assert not (repo / "artifacts").exists()


def test_cli_threads_manifest_timeout_and_retention_to_core(repo, capsys, monkeypatch):
    from cp_knowledge_tools.assurance import cli

    captured = {}

    def fake_supply(root, **kwargs):
        captured.update(kwargs)
        return Report({}, {"root": str(root)})

    monkeypatch.setattr(cli, "supply_chain", fake_supply)
    manifest = repo / "reviewed.json"
    assert (
        main(
            [
                "assurance",
                "supply-chain",
                "--repo-root",
                str(repo),
                "--profile",
                "admission",
                "--admission-manifest",
                str(manifest),
                "--timeout",
                "23",
                "--retain-sbom",
            ]
        )
        == 0
    )
    assert captured["admission_manifest"] == manifest
    assert captured["timeout"] == 23
    assert captured["retain_sbom"] is True
    assert json.loads(capsys.readouterr().out)["decision"] == "not_evaluated"
