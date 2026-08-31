import json
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cp_knowledge_tools.assurance.execution import execute
from cp_knowledge_tools.assurance.report import Report
from cp_knowledge_tools.assurance.repository import file_hash
from cp_knowledge_tools.assurance.scanners import normalize, scan


@pytest.fixture
def protocol_admission(monkeypatch):
    """Only replace the admission seam; keep real subprocess protocol tests.

    Production admission and actual executables are tested separately.
    """
    monkeypatch.setattr(
        "cp_knowledge_tools.assurance.scanners.binding",
        lambda executable, entry, name: (
            [str(executable)],
            {"executable_hash": file_hash(executable, max_bytes=512_000_000)},
        ),
    )
    monkeypatch.setattr(
        "cp_knowledge_tools.assurance.scanners.environment_packages",
        lambda: [{"name": "x", "version": "1"}],
    )
    return {"version": "1.2.3"}


@pytest.mark.parametrize(
    "name,code,payload",
    [
        ("cyclonedx", 0, {"bomFormat": "CycloneDX", "components": [None]}),
        (
            "cyclonedx",
            0,
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "version": 1,
                "components": [None],
            },
        ),
        (
            "pip-audit",
            0,
            {"dependencies": [{"name": ["x"], "version": {"a": "b"}, "vulns": []}]},
        ),
        (
            "gitleaks",
            10,
            [{"RuleID": "x", "File": "x", "StartLine": {"Secret": "SENTINEL"}}],
        ),
        ("gitleaks", 10, [{"RuleID": "x", "File": "x", "StartLine": True}]),
    ],
)
def test_malformed_retained_fields_cannot_be_evidence(name, code, payload):
    with pytest.raises(ValueError):
        normalize(name, code, payload)


def test_scanner_transport_accepts_large_executable_and_stdout_protocol(
    tmp_path, protocol_admission
):
    executable = tmp_path / "fake-cyclonedx"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "if '--version' in sys.argv:\n"
        "    print('fake 1.2.3')\n"
        "else:\n"
        "    assert sys.argv[-2:] == ['--output-file', '-']\n"
        "    print(json.dumps({'bomFormat': 'CycloneDX', 'specVersion': '1.6', "
        "'version': 1, 'components': [{'type': 'library', 'name': 'x', "
        "'version': '1'}]}))\n" + "#" + "x" * 10_000_001 + "\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name="cyclonedx",
        executable=executable,
        timeout=5,
        admission=protocol_admission,
    )
    assert report.status == "passed"
    check = report.checks[0]
    assert check["summary"]["component_count"] == 1
    assert check["tool_version"] == "1.2.3"
    assert check["output_hash"]


def test_process_output_overflow_cannot_leave_success_or_raw_data(tmp_path):
    result = execute(
        [sys.executable, "-c", "import sys; sys.stderr.write('SENSITIVE' * 1000)"],
        tmp_path,
        5,
        max_bytes=100,
    )
    assert result.problem == "output_budget_exceeded"
    assert result.output == b""


def test_scanner_timeout_keeps_safe_reason(tmp_path, protocol_admission):
    executable = tmp_path / "fake-gitleaks"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        "else: time.sleep(3)\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name="gitleaks",
        executable=executable,
        timeout=1,
        admission=protocol_admission,
    )
    assert report.status == "incomplete"
    assert report.checks[0]["reason"] == "timeout"


def test_gitleaks_secrets_and_fragments_never_reach_report():
    result = normalize(
        "gitleaks",
        10,
        [
            {
                "RuleID": "test",
                "File": "source.py",
                "StartLine": 3,
                "Secret": "SENSITIVE_VALUE",
                "Match": "SENSITIVE_VALUE",
                "Fragment": "SENSITIVE_VALUE",
            }
        ],
    )
    assert "SENSITIVE_VALUE" not in json.dumps(result)
    assert result["findings"] == [
        {"RuleID": "test", "File": "source.py", "StartLine": 3}
    ]


@pytest.mark.parametrize(
    "code,payload",
    [
        (1, {}),
        (0, {}),
        (0, {"dependencies": []}),
        (
            0,
            {
                "dependencies": [
                    {"name": "x", "version": "1", "skip_reason": "unavailable"}
                ]
            },
        ),
        (1, {"dependencies": [{"name": "x", "version": "1", "vulns": []}]}),
    ],
)
def test_pip_audit_errors_and_skips_cannot_be_clean(code, payload):
    with pytest.raises(ValueError):
        normalize("pip-audit", code, payload)


def test_scanner_findings_are_not_acceptance():
    payload = {
        "dependencies": [
            {
                "name": "x",
                "version": "1",
                "vulns": [{"id": "TEST-123", "description": "untrusted text"}],
            }
        ]
    }
    result = normalize("pip-audit", 1, payload)
    assert result["result"] == "findings"
    assert "accepted" not in json.dumps(result)
    assert "untrusted text" not in json.dumps(result)
    with pytest.raises(ValueError):
        normalize("pip-audit", 0, payload)


@settings(max_examples=40, database=None)
@given(
    st.lists(
        st.sampled_from(["passed", "failed", "incomplete", "not_applicable"]),
        min_size=1,
        max_size=15,
    )
)
def test_later_passes_never_erase_failure_and_order_is_irrelevant(statuses):
    forward, reverse = Report({}, {}), Report({}, {})
    for status in statuses:
        forward.check("check", status)
    for status in reversed(statuses):
        reverse.check("check", status)
    assert forward.status == reverse.status
    if "failed" in statuses:
        assert forward.exit_code == 1
    elif "incomplete" in statuses:
        assert forward.exit_code == 2


def grant_payload(packages=None, status="unevaluated"):
    return {
        "tool": "grant",
        "version": "0.6.8",
        "run": {
            "targets": [
                {
                    "evaluation": {
                        "status": status,
                        "findings": {
                            "packages": packages
                            or [
                                {
                                    "name": "sample",
                                    "version": "1",
                                    "decision": "unevaluated",
                                    "licenses": [
                                        {
                                            "id": "MIT",
                                            "name": "do not retain",
                                            "riskCategory": "do not use as policy",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                }
            ]
        },
    }


def test_grant_observed_contract_and_duplicate_license_rows():
    payload = grant_payload()
    rows = payload["run"]["targets"][0]["evaluation"]["findings"]["packages"]
    rows.append({**rows[0], "licenses": [{"id": "Apache-2.0"}]})
    result = normalize("grant", 0, payload)
    assert result["package_count"] == 1
    assert result["packages"][0]["licenses"] == ["Apache-2.0", "MIT"]
    assert result["policy_evaluated"] is False
    assert "do not" not in json.dumps(result)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"packages": []},
        grant_payload(status="error"),
        grant_payload(status="passed"),
    ],
)
def test_grant_unknown_or_error_schema_is_never_clean(payload):
    with pytest.raises(ValueError):
        normalize("grant", 0, payload)


def test_partial_scanner_inventory_cannot_pass(
    tmp_path, monkeypatch, protocol_admission
):
    monkeypatch.setattr(
        "cp_knowledge_tools.assurance.scanners.environment_packages",
        lambda: [{"name": "x", "version": "1"}, {"name": "y", "version": "2"}],
    )
    executable = tmp_path / "fake-audit"
    executable.write_text(
        f"#!{sys.executable}\nimport json,sys\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        "else: print(json.dumps({'dependencies': "
        "[{'name':'x','version':'1','vulns':[]}]}))\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name="pip-audit",
        executable=executable,
        admission=protocol_admission,
        allow_network=True,
    )
    assert report.status == "incomplete"
    assert "coverage" in report.checks[-1]["reason"]


def test_controlled_environment_excludes_credentials_and_cwd_config(tmp_path):
    result = execute(
        [sys.executable, "-c", "import os; print(sorted(os.environ))"],
        tmp_path,
        5,
        environment={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert result.code == 0
    assert b"TOKEN" not in result.output
    assert b"HOME" in result.output


def test_work_cache_budget_is_finite(tmp_path):
    result = execute(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('cache').write_bytes(b'x'*1000)",
        ],
        tmp_path,
        5,
        work_budget=(tmp_path, 100),
    )
    assert result.problem == "work_budget_exceeded"
    assert result.output == b""


def test_sbom_projection_drops_untrusted_fulltexts_and_paths():
    from cp_knowledge_tools.assurance.scanners import safe_sbom

    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"path": "PRIVATE_SENTINEL"},
        "components": [
            {
                "type": "library",
                "name": "sample",
                "version": "1",
                "description": "PRIVATE_SENTINEL",
                "purl": "PRIVATE_SENTINEL",
                "licenses": [
                    {"license": {"id": "MIT", "text": "PRIVATE_SENTINEL"}},
                    {"license": {"name": "PRIVATE_SENTINEL"}},
                ],
            }
        ],
    }
    output = safe_sbom(payload)
    assert b"PRIVATE_SENTINEL" not in output
    assert json.loads(output)["components"][0]["licenses"] == [
        {"license": {"id": "MIT"}}
    ]


def test_target_ignore_file_is_not_silently_applied(tmp_path, protocol_admission):
    (tmp_path / ".gitleaksignore").write_text("ignored")
    exe = tmp_path / "fake"
    exe.write_text(f"#!{sys.executable}\nprint('fake 1.2.3')\n")
    exe.chmod(0o700)
    report = Report({}, {})
    scan(
        report, tmp_path, name="gitleaks", executable=exe, admission=protocol_admission
    )
    assert report.status == "incomplete"
    assert "ignore" in report.checks[-1]["reason"]


@pytest.mark.parametrize("name", ["grant", "gitleaks"])
def test_deep_json_input_is_incomplete_without_raw_output(
    tmp_path, protocol_admission, name
):
    depth = sys.getrecursionlimit() + 1000
    executable = tmp_path / "fake"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        f"else: print('[' * {depth} + '0' + ']' * {depth})\n"
    )
    executable.chmod(0o700)
    sbom = tmp_path / "deep.json"
    sbom.write_text("[" * depth + "0" + "]" * depth)
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name=name,
        executable=executable,
        admission=protocol_admission,
        sbom=sbom,
    )
    assert report.status == "incomplete"
    # Some Python JSON decoders accept this depth; others raise RecursionError.
    # Both paths must remain structured incomplete, without retaining the input.
    assert report.checks[-1]["reason"] in {
        "RecursionError",
        "invalid or unsuccessful CycloneDX result",
        "invalid or unsuccessful Gitleaks result",
    }
    assert "[[[[" not in json.dumps(report.payload())


def test_gitleaks_ignored_input_mutation_cannot_pass(tmp_path, protocol_admission):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("ignored.txt\n")
    ignored = root / "ignored.txt"
    ignored.write_text("before")
    executable = tmp_path / "fake"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        f"else:\n    Path({str(ignored)!r}).write_text('after')\n    print('[]')\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(
        report,
        root,
        name="gitleaks",
        executable=executable,
        admission=protocol_admission,
    )
    assert report.status == "incomplete"
    assert "input changed" in report.checks[-1]["reason"]


@pytest.mark.parametrize("name", ["grant", "gitleaks"])
def test_parser_recursion_failure_is_structured_incomplete(
    tmp_path, monkeypatch, protocol_admission, name
):
    executable = tmp_path / "fake"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "print('fake 1.2.3' if '--version' in sys.argv else '[]')\n"
    )
    executable.chmod(0o700)
    sbom = tmp_path / "input.json"
    sbom.write_text("{}")

    def parser_limit(_):
        raise RecursionError("SENSITIVE_PARSER_DETAIL")

    monkeypatch.setattr(
        "cp_knowledge_tools.assurance.scanners.json.loads", parser_limit
    )
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name=name,
        executable=executable,
        admission=protocol_admission,
        sbom=sbom,
    )
    assert report.status == "incomplete"
    assert report.checks[-1]["reason"] == "RecursionError"
    assert "SENSITIVE_PARSER_DETAIL" not in json.dumps(report.payload())


def test_changed_distribution_metadata_cannot_pass(
    tmp_path, monkeypatch, protocol_admission
):
    import importlib.metadata

    dist = tmp_path / "x-1.dist-info"
    dist.mkdir()
    metadata = dist / "METADATA"
    metadata.write_text("Metadata-Version: 2.1\nName: x\nVersion: 1\n")
    monkeypatch.setattr(
        importlib.metadata,
        "distributions",
        lambda: [importlib.metadata.Distribution.at(dist)],
    )
    executable = tmp_path / "fake"
    executable.write_text(
        f"#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        f"else:\n    Path({str(metadata)!r}).write_text("
        "'Name: x\\nVersion: 1\\nLicense: MIT\\n')\n"
        "    print(json.dumps({'bomFormat':'CycloneDX', 'specVersion':'1.6', "
        "'version':1, "
        "'components':[{'type':'library','name':'x','version':'1'}]}))\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(
        report,
        tmp_path,
        name="cyclonedx",
        executable=executable,
        admission=protocol_admission,
    )
    assert report.status == "incomplete"
    assert "metadata changed" in report.checks[-1]["reason"]
