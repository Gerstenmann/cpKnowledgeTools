from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import pytest
import yaml

from cp_knowledge_tools.operations.application import OperationApplication
from cp_knowledge_tools.operations.contracts import OperationRequest, ResultDisposition


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _managed(
    path: str,
    stable_id: str,
    version: str,
    document_type: str,
) -> str:
    identity = {
        "policy": "policy_id",
        "specification": "specification_id",
        "process": "process_id",
        "decision_record": "decision_id",
    }[document_type]
    frontmatter = {
        "document_type": document_type,
        identity: stable_id,
        "title": "Rule Fixture",
        "version": version,
        "status": "active",
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-01",
        "effective_from": "2026-08-01",
        "canonical_path": path,
    }
    if document_type == "process":
        frontmatter["process_domain"] = "governance"
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nRule.\n"


def _write_rules(vault: Path) -> None:
    rules = (
        ("Systems/Rules/CPKS-POL-GOV-AUTH.md", "CPKS-POL-GOV-AUTH", "1.1", "policy"),
        ("Systems/Rules/CPKS-SPEC-ART.md", "CPKS-SPEC-ART", "0.5", "specification"),
        ("Systems/Rules/CPKS-SPEC-OPS.md", "CPKS-SPEC-OPS", "0.7", "specification"),
        ("Processes/Rules/GOV-P01.md", "GOV-P01", "0.4", "process"),
        ("Systems/Rules/CPKS-DEC-016.md", "CPKS-DEC-016", "1.1", "decision_record"),
        ("Systems/Rules/CPKS-DEC-019.md", "CPKS-DEC-019", "1.0", "decision_record"),
        ("Systems/Rules/CPKS-DEC-021.md", "CPKS-DEC-021", "0.1", "decision_record"),
    )
    for path, stable_id, version, document_type in rules:
        _write(vault, path, _managed(path, stable_id, version, document_type))


def _policy(path: str, version: str = "0.1") -> str:
    frontmatter = {
        "document_type": "policy",
        "policy_id": "CPKS-POL-NEW",
        "title": "New Policy",
        "version": version,
        "status": "draft",
        "evidence_class": "committed_target",
        "owner": "Owner",
        "created": "2026-08-28",
        "revised": "2026-08-28",
        "canonical_path": path,
        "supersedes": [],
    }
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n# New Policy\n\nOwner-prepared.\n"
    )


def _contract(vault: Path) -> dict[str, object]:
    return {
        "contract": "cpks.runtime_authority",
        "contract_version": "0.1",
        "authority": {
            "ref": "CPKT-WP-AUTH",
            "version": "0.1",
            "class": "work_package",
            "issuer": "Owner",
        },
        "operations": ["artifact.activate"],
        "targets": [
            {
                "stable_id": "CPKS-POL-NEW",
                "version": "0.1",
                "artifact_class": "policy",
                "target_kind": "cp-wiki",
            }
        ],
        "scope": {
            "document_types": ["policy"],
            "mutation_scope": ["lifecycle_activation"],
        },
        "environment": {
            "kind": "local_vault",
            "identity": vault.resolve().as_uri(),
        },
        "effects": {
            "mutate": True,
            "activate": True,
            "remote_effects": False,
        },
        "validity": {
            "effective_from": "2026-08-28T00:00:00+00:00",
            "expires_at": "2026-09-30T00:00:00+00:00",
        },
        "approval": {
            "required": False,
            "approved_by": None,
            "approved_at": None,
            "evidence_ref": None,
        },
    }


def _write_authority(vault: Path, contract: dict[str, object]) -> None:
    path = "Development/Test/Work Packages/CPKT-WP-AUTH Authority.md"
    frontmatter = {
        "document_type": "work_package",
        "work_package_id": "CPKT-WP-AUTH",
        "title": "Authority",
        "version": "0.1",
        "status": "active",
        "evidence_class": "active_constraint",
        "owner": "Owner",
        "approved_by": "Owner",
        "approved_at": "2026-08-28",
        "effective_from": "2026-08-28",
        "canonical_path": path,
        "runtime_authority_contracts": [contract],
    }
    _write(
        vault,
        path,
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nAuthority.\n",
    )


def _case(
    tmp_path: Path,
    *,
    caller_contract: dict[str, object] | None = None,
) -> tuple[OperationApplication, OperationRequest, Path, str]:
    vault = tmp_path / "vault"
    runs = tmp_path / "runs"
    draft = (
        "Development/cpKnowledgeSystem/Governance/Drafts/"
        "CPKS-POL-NEW@0.1 New Policy.md"
    )
    active = (
        "Systems/cpKnowledgeSystem/Governance/Policies/CPKS-POL-NEW New Policy.md"
    )
    _write(vault, draft, _policy(draft))
    _write_rules(vault)
    canonical_contract = _contract(vault)
    _write_authority(vault, canonical_contract)
    request = OperationRequest(
        operation_name="artifact.activate",
        operation_version="0.1",
        targets=("CPKS-POL-NEW",),
        requested_mode="apply",
        authority_ref="CPKT-WP-AUTH@0.1",
        idempotency_key="initial-policy",
        parameters={
            "stable_id": "CPKS-POL-NEW",
            "draft_path": draft,
            "archive_path": None,
            "active_path": active,
            "approved_by": "Owner",
            "approved_at": "2026-08-28",
            "effective_from": "2026-08-28",
            "vault_root": str(vault),
            "run_root": str(runs),
            "runtime_authority": caller_contract or canonical_contract,
            "target_classification": "test",
        },
    )
    app = OperationApplication(
        authority_clock=lambda: dt.datetime(2026, 8, 29, tzinfo=dt.UTC)
    )
    return app, request, vault, active


def test_initial_activation_runs_through_application_context(tmp_path: Path) -> None:
    app, request, vault, active = _case(tmp_path)

    result = app.execute(request, **request.parameters)

    assert result.disposition is ResultDisposition.SUCCEEDED
    assert (vault / active).exists()
    context = result.outputs["operation_context"]
    assert context["lifecycle_profile"] == "policy"
    assert context["document_type"] == "policy"
    assert context["identity_field"] == "policy_id"
    assert context["stable_id"] == "CPKS-POL-NEW"
    assert context["target_version"] == "0.1"
    assert context["active_rule_homes"]["CPKS-DEC-016"] == "1.1"
    assert context["actual_current_state"]["identity_field"] == "policy_id"
    assert context["actual_current_state"]["status"] == "absent"
    assert result.outputs["preflight"]["current_state"]["activation_mode"] == "initial"


@pytest.mark.parametrize(
    "mutator",
    (
        lambda contract: contract["scope"].update(
            document_types=["policy", "specification"]
        ),
        lambda contract: contract["scope"].update(mutation_scope=[]),
        lambda contract: contract["effects"].update(activate=False),
        lambda contract: contract["targets"][0].update(
            stable_id="CPKS-POL-OTHER"
        ),
        lambda contract: contract["targets"][0].update(
            artifact_class="specification"
        ),
    ),
)
def test_runtime_authority_scope_and_type_isolation_fail_closed(
    tmp_path: Path,
    mutator,
) -> None:
    vault = tmp_path / "vault"
    contract = _contract(vault)
    caller_contract = copy.deepcopy(contract)
    mutator(caller_contract)
    app, request, vault, active = _case(
        tmp_path, caller_contract=caller_contract
    )

    result = app.execute(request, **request.parameters)

    assert result.disposition is ResultDisposition.BLOCKED
    assert result.actual_mutations == ()
    assert not (vault / active).exists()
