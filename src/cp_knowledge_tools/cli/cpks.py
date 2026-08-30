"""Thin CLI for the CPKS Operation Kernel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from cp_knowledge_tools.operations.application import OperationApplication
from cp_knowledge_tools.operations.contracts import OperationRequest
from cp_knowledge_tools.operations.registry import build_standard_registry
from cp_knowledge_tools.operations.results import to_primitive

VERSION = "0.1.0"


def _mode(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_const", const="check", dest="mode")
    group.add_argument("--apply", action="store_const", const="apply", dest="mode")
    parser.set_defaults(mode="check")


def _authority(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority-ref")
    parser.add_argument(
        "--authority-contract",
        type=Path,
        help=(
            "Structured cpks.runtime_authority@0.1 contract. The contract is "
            "accepted only when independently covered by the resolved authority."
        ),
    )


def _runtime_authority(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime authority contract must be a mapping")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpks",
        description="Governance-aware local operation kernel for cpKnowledgeTools.",
    )
    parser.add_argument("--version", action="version", version=f"cpks {VERSION}")
    root = parser.add_subparsers(dest="group", required=True)

    operation = root.add_parser("operation", help="Resolve standard operations.")
    operation_sub = operation.add_subparsers(dest="command", required=True)
    operation_resolve = operation_sub.add_parser(
        "resolve", help="Resolve one registered operation."
    )
    operation_resolve.add_argument("operation_id")
    operation_resolve.add_argument("--operation-version", default="0.1")

    governance = root.add_parser("governance", help="Read-only governance operations.")
    governance_sub = governance.add_subparsers(dest="command", required=True)
    governance_resolve = governance_sub.add_parser(
        "resolve", help="Resolve an active governance artifact."
    )
    governance_resolve.add_argument("stable_id")
    governance_resolve.add_argument("--vault-root", required=True, type=Path)
    governance_preflight = governance_sub.add_parser(
        "preflight", help="Run an incremental mutation preflight."
    )
    governance_preflight.add_argument("stable_id")
    governance_preflight.add_argument("--target-version")
    governance_preflight.add_argument("--vault-root", required=True, type=Path)
    _authority(governance_preflight)

    artifact = root.add_parser("artifact", help="Safe managed-artifact operations.")
    artifact_sub = artifact.add_subparsers(dest="command", required=True)
    revise = artifact_sub.add_parser(
        "revise", help="Check or materialize an owner-prepared Managed Artifact draft."
    )
    revise.add_argument("stable_id")
    revise.add_argument("--prepared-file", required=True, type=Path)
    revise.add_argument("--target-path", required=True)
    revise.add_argument("--vault-root", required=True, type=Path)
    revise.add_argument("--run-root", required=True, type=Path)
    revise.add_argument("--idempotency-key", required=True)
    revise.add_argument(
        "--target-classification",
        choices=("test", "live", "other"),
        default="other",
        help="Explicit execution-context classification; never inferred from path.",
    )
    _authority(revise)
    _mode(revise)

    activate = artifact_sub.add_parser(
        "activate", help="Check an initial or follow-up Managed Artifact activation."
    )
    activate.add_argument("stable_id")
    activate.add_argument("--draft-path", required=True)
    activate.add_argument(
        "--archive-path",
        help="Required for follow-up activation; forbidden for initial activation.",
    )
    activate.add_argument(
        "--active-path",
        help=(
            "Explicit active target path. Required for initial activation and "
            "optional for a title-changing follow-up."
        ),
    )
    activate.add_argument(
        "--activation-target-file",
        type=Path,
        help=(
            "Optional owner-prepared active target state. Identity, title and "
            "version must match the draft; its body may contain controlled "
            "lifecycle-only transformations."
        ),
    )
    activate.add_argument("--approved-by", required=True)
    activate.add_argument("--approved-at", required=True)
    activate.add_argument("--effective-from", required=True)
    activate.add_argument("--vault-root", required=True, type=Path)
    activate.add_argument("--run-root", required=True, type=Path)
    activate.add_argument("--idempotency-key", required=True)
    activate.add_argument(
        "--target-classification",
        choices=("test", "live", "other"),
        default="other",
        help="Explicit execution-context classification; never inferred from path.",
    )
    _authority(activate)
    _mode(activate)

    work_package = root.add_parser(
        "work-package", help="Controlled Work Package lifecycle operations."
    )
    work_package_sub = work_package.add_subparsers(dest="command", required=True)
    complete = work_package_sub.add_parser(
        "complete", help="Check or apply the work_package.complete transition."
    )
    complete.add_argument("stable_id")
    completion_input = complete.add_mutually_exclusive_group(required=True)
    completion_input.add_argument(
        "--prepared-file",
        type=Path,
        help="Fully prepared completed Work Package target.",
    )
    completion_input.add_argument(
        "--completion-evidence",
        type=Path,
        help=(
            "Explicit owner-prepared Completion Evidence appended without changing "
            "the active Work Package content or authority."
        ),
    )
    complete.add_argument("--archive-path", required=True)
    complete.add_argument("--vault-root", required=True, type=Path)
    complete.add_argument("--run-root", required=True, type=Path)
    complete.add_argument("--idempotency-key", required=True)
    complete.add_argument(
        "--target-classification",
        choices=("test", "live", "other"),
        default="other",
        help="Explicit execution-context classification; never inferred from path.",
    )
    _authority(complete)
    _mode(complete)

    derived = root.add_parser("derived", help="Rebuild non-normative derived state.")
    derived_sub = derived.add_subparsers(dest="command", required=True)
    governance_derived = derived_sub.add_parser(
        "governance", help="Governance-derived-state operations."
    )
    governance_derived_sub = governance_derived.add_subparsers(
        dest="derived_command", required=True
    )
    refresh = governance_derived_sub.add_parser(
        "refresh", help="Check or persist a canonical-input rebuild."
    )
    refresh.add_argument("--vault-root", required=True, type=Path)
    refresh.add_argument("--run-root", required=True, type=Path)
    _mode(refresh)

    incident = root.add_parser("incident", help="Best-effort incident operations.")
    incident_sub = incident.add_subparsers(dest="command", required=True)
    capture = incident_sub.add_parser(
        "capture", help="Preview or capture a sanitized exec failure incident."
    )
    capture.add_argument("--repo-root", required=True, type=Path)
    capture.add_argument("--run-root", type=Path)
    capture.add_argument(
        "--capture-mode", choices=("at_failure", "retrospective"), default="at_failure"
    )
    capture.add_argument("--failure-phase", required=True)
    capture.add_argument("--mutation-state", required=True)
    capture.add_argument("--message")
    _mode(capture)
    return parser


def _request(
    operation_name: str,
    args: argparse.Namespace,
    *,
    targets: tuple[str, ...] = (),
    parameters: dict[str, Any] | None = None,
) -> OperationRequest:
    return OperationRequest(
        operation_name=operation_name,
        operation_version="0.1",
        targets=targets,
        requested_mode=getattr(args, "mode", "check"),
        requester_ref="cpks-cli",
        authority_ref=getattr(args, "authority_ref", None),
        idempotency_key=getattr(args, "idempotency_key", None),
        parameters=parameters or {},
    )


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.group == "operation":
        registered = build_standard_registry().resolve(
            args.operation_id, args.operation_version
        )
        return to_primitive(registered.spec)

    application = OperationApplication()
    if args.group == "governance" and args.command == "resolve":
        request = _request(
            "governance.resolve",
            args,
            targets=(args.stable_id,),
            parameters={
                "vault_root": str(args.vault_root),
                "stable_id": args.stable_id,
            },
        )
    elif args.group == "governance" and args.command == "preflight":
        request = _request(
            "governance.preflight",
            args,
            targets=(args.stable_id,),
            parameters={
                "vault_root": str(args.vault_root),
                "stable_id": args.stable_id,
                "target_version": args.target_version,
                "runtime_authority": _runtime_authority(args.authority_contract),
            },
        )
    elif args.group == "artifact" and args.command == "revise":
        request = _request(
            "artifact.revise",
            args,
            targets=(args.stable_id,),
            parameters={
                "stable_id": args.stable_id,
                "prepared_file": str(args.prepared_file),
                "target_path": args.target_path,
                "vault_root": str(args.vault_root),
                "run_root": str(args.run_root),
                "runtime_authority": _runtime_authority(args.authority_contract),
                "target_classification": args.target_classification,
            },
        )
    elif args.group == "artifact" and args.command == "activate":
        request = _request(
            "artifact.activate",
            args,
            targets=(args.stable_id,),
            parameters={
                "stable_id": args.stable_id,
                "draft_path": args.draft_path,
                "archive_path": args.archive_path,
                "active_path": args.active_path,
                "activation_target_file": (
                    str(args.activation_target_file)
                    if args.activation_target_file
                    else None
                ),
                "approved_by": args.approved_by,
                "approved_at": args.approved_at,
                "effective_from": args.effective_from,
                "vault_root": str(args.vault_root),
                "run_root": str(args.run_root),
                "runtime_authority": _runtime_authority(args.authority_contract),
                "target_classification": args.target_classification,
            },
        )
    elif args.group == "work-package" and args.command == "complete":
        request = _request(
            "artifact.transition",
            args,
            targets=(args.stable_id,),
            parameters={
                "transition_profile": "work_package.complete",
                "stable_id": args.stable_id,
                "prepared_file": (
                    str(args.prepared_file) if args.prepared_file else None
                ),
                "completion_evidence_file": (
                    str(args.completion_evidence)
                    if args.completion_evidence
                    else None
                ),
                "archive_path": args.archive_path,
                "vault_root": str(args.vault_root),
                "run_root": str(args.run_root),
                "runtime_authority": _runtime_authority(args.authority_contract),
                "target_classification": args.target_classification,
            },
        )
    elif args.group == "derived":
        request = _request(
            "derived.governance.refresh",
            args,
            parameters={
                "vault_root": str(args.vault_root),
                "run_root": str(args.run_root),
            },
        )
    elif args.group == "incident":
        request = _request(
            "incident.capture",
            args,
            parameters={
                "repo_root": str(args.repo_root),
                "run_root": str(args.run_root) if args.run_root else None,
                "capture_mode": args.capture_mode,
                "failure_phase": args.failure_phase,
                "mutation_state": args.mutation_state,
                "details": {"message": args.message} if args.message else {},
            },
        )
    else:  # pragma: no cover - argparse constrains this branch
        raise ValueError("unsupported command")
    return to_primitive(application.execute(request, **request.parameters))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = _dispatch(args)
    except SystemExit as exc:
        return int(exc.code)
    except (KeyError, OSError, ValueError) as exc:
        print(
            json.dumps({"disposition": "blocked", "error": str(exc)}), file=sys.stderr
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    disposition = payload.get("disposition")
    return 0 if disposition in {None, "succeeded", "idempotent_replay"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
