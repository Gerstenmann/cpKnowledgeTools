import json
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cp_knowledge_tools.assurance.execution import execute
from cp_knowledge_tools.assurance.report import Report
from cp_knowledge_tools.assurance.scanners import normalize, scan


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


def test_scanner_transport_accepts_large_executable_and_stdout_protocol(tmp_path):
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
    scan(report, tmp_path, name="cyclonedx", executable=executable, timeout=5)
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


def test_scanner_timeout_keeps_safe_reason(tmp_path):
    executable = tmp_path / "fake-gitleaks"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "if '--version' in sys.argv: print('fake 1.2.3')\n"
        "else: time.sleep(3)\n"
    )
    executable.chmod(0o700)
    report = Report({}, {})
    scan(report, tmp_path, name="gitleaks", executable=executable, timeout=1)
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
