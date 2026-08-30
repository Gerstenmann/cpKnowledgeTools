from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.operations.contracts import (
    AuthorityDecision,
    AuthorityDisposition,
    ResultDisposition,
)
from cp_knowledge_tools.operations.governance.managed_artifacts import (
    activate_specification,
    complete_work_package,
    plan_specification_activation,
    plan_work_package_completion,
    revise_managed_artifact,
)
from cp_knowledge_tools.operations.transactions.filesystem import (
    FileTransactionEngine,
)

CASES = {
    "specification": {
        "stable_id": "EX-SPEC-K2",
        "identity": "specification_id",
        "active": "Systems/Example/EX-SPEC-K2 Example Artifact.md",
        "draft": "Development/Example/EX-SPEC-K2@1.1 Example Artifact.md",
        "archive": "Systems/Example/Archive/EX-SPEC-K2@1.0 Example Artifact.md",
    },
    "decision_record": {
        "stable_id": "CPKS-DEC-900",
        "identity": "decision_id",
        "active": (
            "Systems/cpKnowledgeSystem/Governance/Decisions/"
            "CPKS-DEC-900 Example Artifact.md"
        ),
        "draft": (
            "Development/cpKnowledgeSystem/Governance/Draft Decisions/"
            "CPKS-DEC-900@1.1 Example Artifact.md"
        ),
        "archive": (
            "Systems/cpKnowledgeSystem/Governance/Decisions/History/"
            "CPKS-DEC-900@1.0 Example Artifact.md"
        ),
    },
    "policy": {
        "stable_id": "CPKS-POL-K2",
        "identity": "policy_id",
        "active": (
            "Systems/cpKnowledgeSystem/Governance/Policies/"
            "CPKS-POL-K2 Example Artifact.md"
        ),
        "draft": (
            "Development/cpKnowledgeSystem/Governance/Drafts/"
            "CPKS-POL-K2@1.1 Example Artifact.md"
        ),
        "archive": (
            "Systems/cpKnowledgeSystem/Governance/Archive/Policies/"
            "CPKS-POL-K2@1.0 Example Artifact.md"
        ),
    },
    "framework": {
        "stable_id": "CPKS-FWK-K2",
        "identity": "framework_id",
        "active": (
            "Systems/cpKnowledgeSystem/Governance/CPKS-FWK-K2 Example Artifact.md"
        ),
        "draft": (
            "Development/cpKnowledgeSystem/Governance/Drafts/"
            "CPKS-FWK-K2@1.1 Example Artifact.md"
        ),
        "archive": (
            "Systems/cpKnowledgeSystem/Governance/Archive/Frameworks/"
            "CPKS-FWK-K2@1.0 Example Artifact.md"
        ),
    },
    "process": {
        "stable_id": "GOV-P99",
        "identity": "process_id",
        "active": "Processes/Governance/GOV-P99 Example Artifact.md",
        "draft": (
            "Development/cpKnowledgeSystem/Governance/Draft Processes/"
            "GOV-P99@1.1 Example Artifact.md"
        ),
        "archive": (
            "Processes/Governance/Archive/GOV-P99@1.0 Example Artifact.md"
        ),
    },
}


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _artifact(
    document_type: str,
    *,
    stable_id: str,
    version: str,
    status: str,
    canonical_path: str,
    title: str = "Example Artifact",
    source_artifact: str | None = None,
    body: str = "# Example Artifact\n\nOwner-prepared content.\n",
) -> str:
    identity = CASES.get(document_type, {}).get("identity", "work_package_id")
    frontmatter: dict[str, object] = {
        "document_type": document_type,
        identity: stable_id,
        "title": title,
        "version": version,
        "status": status,
        "evidence_class": (
            "active_constraint" if status == "active" else "committed_target"
        ),
        "owner": "Owner",
        "created": "2026-08-01",
        "revised": "2026-08-28",
        "canonical_path": canonical_path,
        "supersedes": [],
    }
    if document_type == "process":
        frontmatter["process_domain"] = "governance"
    if source_artifact is not None:
        frontmatter["source_artifact"] = source_artifact
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n"
        + body
    )


def _authority(stable_id: str) -> AuthorityDecision:
    return AuthorityDecision(
        disposition=AuthorityDisposition.AUTHORIZED,
        authority_ref="CPKT-WP-K2@0.1",
        targets=(stable_id,),
    )


@pytest.mark.parametrize("document_type", tuple(CASES))
def test_revise_generalizes_the_existing_kernel(
    tmp_path: Path,
    document_type: str,
) -> None:
    case = CASES[document_type]
    vault = tmp_path / "vault"
    _write(
        vault,
        case["active"],
        _artifact(
            document_type,
            stable_id=case["stable_id"],
            version="1.0",
            status="active",
            canonical_path=case["active"],
        ),
    )
    prepared = _write(
        tmp_path,
        f"prepared-{document_type}.md",
        _artifact(
            document_type,
            stable_id=case["stable_id"],
            version="1.1",
            status="draft",
            canonical_path=case["draft"],
            source_artifact=f"{case['stable_id']}@1.0",
        ),
    )
    result = revise_managed_artifact(
        vault_root=vault,
        prepared_file=prepared,
        target_path=case["draft"],
        authority=_authority(case["stable_id"]),
        apply=True,
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
        idempotency_key=f"revise-{document_type}",
    )

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert (vault / case["draft"]).exists()


@pytest.mark.parametrize("document_type", tuple(CASES))
def test_follow_up_activation_is_type_bound_and_reread(
    tmp_path: Path,
    document_type: str,
) -> None:
    case = CASES[document_type]
    vault = tmp_path / "vault"
    _write(
        vault,
        case["active"],
        _artifact(
            document_type,
            stable_id=case["stable_id"],
            version="1.0",
            status="active",
            canonical_path=case["active"],
        ),
    )
    _write(
        vault,
        case["draft"],
        _artifact(
            document_type,
            stable_id=case["stable_id"],
            version="1.1",
            status="draft",
            canonical_path=case["draft"],
            source_artifact=f"{case['stable_id']}@1.0",
        ),
    )
    engine = FileTransactionEngine(vault, tmp_path / "runs")
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id=case["stable_id"],
        draft_path=case["draft"],
        archive_path=case["archive"],
        approved_by="Owner",
        approved_at="2026-08-28",
        effective_from="2026-08-28",
        authority=_authority(case["stable_id"]),
        transaction_engine=engine,
    )
    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key=f"activate-{document_type}",
    )

    assert plan.document_type == document_type
    assert plan.initial_activation is False
    assert result.disposition is ResultDisposition.SUCCEEDED
    assert result.postcondition_report is not None
    assert result.postcondition_report.passed is True
    assert (vault / case["active"]).exists()
    assert (vault / case["archive"]).exists()


@pytest.mark.parametrize(
    ("document_type", "initial_version"),
    (
        ("specification", "0.1"),
        ("decision_record", "0.1"),
        ("decision_record", "1.0"),
        ("policy", "0.1"),
        ("framework", "0.1"),
        ("process", "0.1"),
    ),
)
def test_initial_activation_has_no_phantom_predecessor(
    tmp_path: Path,
    document_type: str,
    initial_version: str,
) -> None:
    case = CASES[document_type]
    vault = tmp_path / "vault"
    draft = case["draft"].replace("@1.1", f"@{initial_version}")
    _write(
        vault,
        draft,
        _artifact(
            document_type,
            stable_id=case["stable_id"],
            version=initial_version,
            status="draft",
            canonical_path=draft,
        ),
    )
    engine = FileTransactionEngine(vault, tmp_path / "runs")
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id=case["stable_id"],
        draft_path=draft,
        archive_path=None,
        active_path=case["active"],
        approved_by="Owner",
        approved_at="2026-08-28",
        effective_from="2026-08-28",
        authority=_authority(case["stable_id"]),
        transaction_engine=engine,
    )
    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key=f"initial-{document_type}-{initial_version}",
    )

    assert plan.initial_activation is True
    assert result.disposition is ResultDisposition.SUCCEEDED
    assert result.postcondition_report is not None
    assert result.postcondition_report.passed is True
    assert not any((vault / case["archive"]).parent.glob("*.md"))


def test_decision_rejects_other_initial_version(tmp_path: Path) -> None:
    case = CASES["decision_record"]
    vault = tmp_path / "vault"
    draft = case["draft"].replace("@1.1", "@0.2")
    _write(
        vault,
        draft,
        _artifact(
            "decision_record",
            stable_id=case["stable_id"],
            version="0.2",
            status="draft",
            canonical_path=draft,
        ),
    )
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id=case["stable_id"],
        draft_path=draft,
        archive_path=None,
        active_path=case["active"],
        approved_by="Owner",
        approved_at="2026-08-28",
        effective_from="2026-08-28",
        authority=_authority(case["stable_id"]),
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
    )

    assert plan.disposition is ResultDisposition.BLOCKED


def test_title_change_is_allowed_within_the_same_stable_line(tmp_path: Path) -> None:
    case = CASES["policy"]
    vault = tmp_path / "vault"
    renamed_active = case["active"].replace("Example Artifact", "Renamed Policy")
    renamed_draft = case["draft"].replace("Example Artifact", "Renamed Policy")
    _write(
        vault,
        case["active"],
        _artifact(
            "policy",
            stable_id=case["stable_id"],
            version="1.0",
            status="active",
            canonical_path=case["active"],
        ),
    )
    _write(
        vault,
        renamed_draft,
        _artifact(
            "policy",
            stable_id=case["stable_id"],
            version="1.1",
            status="draft",
            canonical_path=renamed_draft,
            title="Renamed Policy",
            source_artifact=f"{case['stable_id']}@1.0",
        ),
    )
    engine = FileTransactionEngine(vault, tmp_path / "runs")
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id=case["stable_id"],
        draft_path=renamed_draft,
        archive_path=case["archive"],
        approved_by="Owner",
        approved_at="2026-08-28",
        effective_from="2026-08-28",
        authority=_authority(case["stable_id"]),
        transaction_engine=engine,
    )
    result = activate_specification(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="title-change",
    )

    assert plan.active_path == renamed_active
    assert result.disposition is ResultDisposition.SUCCEEDED


def test_process_package_is_unsupported(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    package = (
        "Development/cpKnowledgeSystem/Governance/Draft Processes/"
        "GOV-P99@0.1 Example Artifact/GOV-P99@0.1 Example Artifact.md"
    )
    _write(
        vault,
        package,
        _artifact(
            "process",
            stable_id="GOV-P99",
            version="0.1",
            status="draft",
            canonical_path=package,
        ),
    )
    plan = plan_specification_activation(
        vault_root=vault,
        stable_id="GOV-P99",
        draft_path=package,
        archive_path=None,
        active_path="Processes/Governance/GOV-P99 Example Artifact.md",
        approved_by="Owner",
        approved_at="2026-08-28",
        effective_from="2026-08-28",
        authority=_authority("GOV-P99"),
        transaction_engine=FileTransactionEngine(vault, tmp_path / "runs"),
    )

    assert plan.disposition is ResultDisposition.UNSUPPORTED


def _work_package(
    *,
    path: str,
    status: str,
    evidence_class: str,
    body: str,
) -> str:
    frontmatter = {
        "document_type": "work_package",
        "work_package_id": "CPKT-WP-900",
        "title": "K2 Test",
        "version": "0.1",
        "status": status,
        "evidence_class": evidence_class,
        "authority_scope": "component-wide",
        "owner": "Owner",
        "authority_basis": ["Owner Instruction"],
        "scope_summary": "Bounded K2 test scope",
        "runtime_authority_contracts": [{"contract": "preserved"}],
        "affected_artifacts": ["CPKT-SPEC-ARCH"],
        "target_artifacts": ["K2"],
        "created": "2026-08-28",
        "revised": "2026-08-28",
        "canonical_path": path,
    }
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n" + body


_WP_BODY = "# CPKT-WP-900 – K2 Test\n\n## Preserve\n\nAuthority and scope.\n"
_COMPLETION = """

## Completion Evidence

### Actual Deliverables
Implemented K2.

### Deviations
None.

### Validations
Focused and regression tests passed.

### Open Items
None.

### Completion Decision
Technically complete.

### Follow-up References
CPKT-SPEC-ARCH.

### Run/Report References
Local release evidence.
"""


def _completion_case(
    tmp_path: Path,
    *,
    body_suffix: str = _COMPLETION,
    mutate_frontmatter: tuple[str, object] | None = None,
) -> tuple[Path, Path, str, Path]:
    vault = tmp_path / "vault"
    active = "Development/cpKnowledgeTools/Work Packages/CPKT-WP-900 K2 Test.md"
    archive = (
        "Development/cpKnowledgeTools/Work Packages/Archive/"
        "CPKT-WP-900@0.1 K2 Test.md"
    )
    _write(
        vault,
        active,
        _work_package(
            path=active,
            status="active",
            evidence_class="active_constraint",
            body=_WP_BODY,
        ),
    )
    prepared_text = _work_package(
        path=archive,
        status="completed",
        evidence_class="historical_evidence",
        body=_WP_BODY + body_suffix,
    )
    if mutate_frontmatter is not None:
        field, value = mutate_frontmatter
        parsed = yaml.safe_load(prepared_text.split("---", 2)[1])
        parsed[field] = value
        body = prepared_text.split("---", 2)[2]
        prepared_text = "---\n" + yaml.safe_dump(parsed, sort_keys=False) + "---" + body
    prepared = _write(tmp_path, "prepared-completion.md", prepared_text)
    return vault, prepared, archive, tmp_path / "runs"


def test_work_package_completion_preserves_authority_and_archives(
    tmp_path: Path,
) -> None:
    vault, prepared, archive, runs = _completion_case(tmp_path)
    engine = FileTransactionEngine(vault, runs)
    plan = plan_work_package_completion(
        vault_root=vault,
        stable_id="CPKT-WP-900",
        prepared_file=prepared,
        archive_path=archive,
        authority=_authority("CPKT-WP-900"),
        transaction_engine=engine,
    )
    result = complete_work_package(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="complete",
    )

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert result.postcondition_report is not None
    assert result.postcondition_report.passed is True
    assert (vault / archive).exists()
    assert not (
        vault
        / "Development/cpKnowledgeTools/Work Packages/CPKT-WP-900 K2 Test.md"
    ).exists()


@pytest.mark.parametrize(
    "mutation",
    (
        ("authority_basis", ["Self Authorization"]),
        ("runtime_authority_contracts", [{"contract": "expanded"}]),
        ("scope_summary", "Expanded scope"),
        ("authority_scope", "system-wide"),
    ),
)
def test_work_package_completion_cannot_expand_authority_or_scope(
    tmp_path: Path,
    mutation: tuple[str, object],
) -> None:
    vault, prepared, archive, runs = _completion_case(
        tmp_path, mutate_frontmatter=mutation
    )
    plan = plan_work_package_completion(
        vault_root=vault,
        stable_id="CPKT-WP-900",
        prepared_file=prepared,
        archive_path=archive,
        authority=_authority("CPKT-WP-900"),
        transaction_engine=FileTransactionEngine(vault, runs),
    )

    assert plan.disposition is ResultDisposition.BLOCKED


def test_work_package_completion_requires_evidence(tmp_path: Path) -> None:
    vault, prepared, archive, runs = _completion_case(tmp_path, body_suffix="")
    plan = plan_work_package_completion(
        vault_root=vault,
        stable_id="CPKT-WP-900",
        prepared_file=prepared,
        archive_path=archive,
        authority=_authority("CPKT-WP-900"),
        transaction_engine=FileTransactionEngine(vault, runs),
    )

    assert plan.disposition is ResultDisposition.BLOCKED


def test_work_package_completion_accepts_explicit_bound_evidence(
    tmp_path: Path,
) -> None:
    vault, _, archive, runs = _completion_case(tmp_path)
    evidence = _write(tmp_path, "completion-evidence.md", _COMPLETION)
    engine = FileTransactionEngine(vault, runs)
    plan = plan_work_package_completion(
        vault_root=vault,
        stable_id="CPKT-WP-900",
        completion_evidence_file=evidence,
        archive_path=archive,
        authority=_authority("CPKT-WP-900"),
        transaction_engine=engine,
    )
    result = complete_work_package(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key="complete-from-evidence",
    )

    assert result.disposition is ResultDisposition.SUCCEEDED
    completed = (vault / archive).read_text(encoding="utf-8")
    assert _WP_BODY.strip() in completed
    assert _COMPLETION.strip() in completed


@pytest.mark.parametrize(
    ("fail_compensation", "expected"),
    (
        (False, ResultDisposition.COMPENSATED_FAILURE),
        (True, ResultDisposition.RECOVERY_REQUIRED),
    ),
)
def test_work_package_completion_uses_shared_compensation_and_recovery(
    tmp_path: Path,
    fail_compensation: bool,
    expected: ResultDisposition,
) -> None:
    vault, prepared, archive, runs = _completion_case(tmp_path)
    engine = FileTransactionEngine(
        vault,
        runs,
        fail_action_index=1,
        fail_compensation=fail_compensation,
    )
    plan = plan_work_package_completion(
        vault_root=vault,
        stable_id="CPKT-WP-900",
        prepared_file=prepared,
        archive_path=archive,
        authority=_authority("CPKT-WP-900"),
        transaction_engine=engine,
    )
    result = complete_work_package(
        plan,
        transaction_engine=engine,
        apply=True,
        idempotency_key=f"fault-{fail_compensation}",
    )

    assert result.disposition is expected
    if fail_compensation:
        assert result.recovery_record is not None
    else:
        assert result.compensation_status == "compensated"
