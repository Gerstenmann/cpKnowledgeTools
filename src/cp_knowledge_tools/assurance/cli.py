"""Presentation adapter for local assurance functions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .drift import audit
from .project_environment import project_environment
from .report import Report, persist
from .repository import repository_state
from .supply import supply_chain
from .unattended import unattended
from .unattended_evidence import persist as persist_unattended
from .verify import verify


def _common(parser):
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Print only; do not create a report file.",
    )


def add_parsers(root):
    assurance = root.add_parser(
        "assurance", help="Local technical evidence; never approval."
    )
    commands = assurance.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser(
        "preflight", help="Inspect repository, interpreter and dependency state."
    )
    _common(preflight)
    check = commands.add_parser(
        "verify", help="Run finite checks on reviewed local code."
    )
    _common(check)
    check.add_argument(
        "--profile", choices=("fast", "regression", "extended"), default="fast"
    )
    check.add_argument("--path", action="append", default=[])
    check.add_argument("--test", action="append", default=[])
    check.add_argument("--base")
    check.add_argument("--timeout", type=int, default=300)
    supply = commands.add_parser(
        "supply-chain",
        help="Inventory/delta and explicit assurance gaps; no installation.",
    )
    _common(supply)
    supply.add_argument(
        "--profile",
        required=True,
        choices=("research", "admission", "deep-review", "delta"),
    )
    supply.add_argument(
        "--previous", help="Repository-relative prior assurance report."
    )
    supply.add_argument(
        "--tool",
        action="append",
        default=[],
        help="Opt-in admitted scanner: name=/absolute/executable",
    )
    supply.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow authorized vulnerability-service queries.",
    )
    supply.add_argument("--sbom", type=Path, help="Explicit SBOM input for Grant.")
    supply.add_argument(
        "--admission-manifest",
        type=Path,
        help="Reviewed admission manifest (default: repository config/assurance).",
    )
    supply.add_argument(
        "--retain-sbom",
        action="store_true",
        help="Retain only the sanitized generated CycloneDX SBOM as private evidence.",
    )
    supply.add_argument("--timeout", type=int, default=300)
    environment = commands.add_parser(
        "environment",
        help="Check uv lock consistency or observe an authorized fresh rebuild.",
    )
    _common(environment)
    environment.add_argument(
        "--mode", choices=("check", "routine_check", "rebuild"), default="check"
    )
    environment.add_argument("--uv", required=True, type=Path)
    environment.add_argument("--python", required=True, type=Path)
    environment.add_argument("--environment", required=True, type=Path)
    environment.add_argument("--cache-dir", required=True, type=Path)
    environment.add_argument("--binding", type=Path)
    environment.add_argument("--allow-network", action="store_true")
    environment.add_argument("--offline-frozen", action="store_true")
    environment.add_argument("--timeout", type=int, default=300)
    routine = commands.add_parser(
        "unattended",
        help="Observe bounded routine assurance; never repair or schedule.",
    )
    _common(routine)
    routine.add_argument("--vault-root", required=True, type=Path)
    routine.add_argument("--project-path", required=True)
    for name in ("uv", "python", "environment", "cache-dir"):
        routine.add_argument(f"--{name}", required=True, type=Path)
    routine.add_argument("--timeout", type=int, default=240)
    routine.add_argument("--command-timeout", type=int, default=45)
    routine.add_argument("--task-id")
    routine.add_argument("--automation-id")
    routine.add_argument("--codex-version")
    drift = root.add_parser("drift", help="Read-only current-state audit.")
    command = drift.add_subparsers(dest="command", required=True).add_parser("audit")
    _common(command)
    command.add_argument("--scope", choices=("system", "project"), default="system")
    command.add_argument("--vault-root", type=Path)
    command.add_argument("--rule-id", action="append", default=[])
    command.add_argument("--previous")
    command.add_argument("--project-path")


def dispatch(args: argparse.Namespace) -> int:
    if args.group == "assurance" and args.command == "unattended":
        result = unattended(
            args.repo_root,
            vault_root=args.vault_root,
            project_path=args.project_path,
            uv=args.uv,
            python=args.python,
            environment=args.environment,
            cache_dir=args.cache_dir,
            timeout=args.timeout,
            command_timeout=args.command_timeout,
            task_id=args.task_id,
            automation_id=args.automation_id,
            codex_version=args.codex_version,
        )
        payload = result.payload()
        evidence = None
        if not args.no_evidence:
            evidence = persist_unattended(
                payload, Path(payload["observation"]["repository"]["root"])
            )
        if args.format == "json":
            print(
                json.dumps(
                    {**payload, "evidence_path": str(evidence) if evidence else None},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            print(f"{result.status}: {result.materiality} ({payload['comparison']})")
            print(f"  run: {payload['run_id']}")
            print(f"  input stability: {payload['input_stability']}")
            if payload["material_delta"]:
                print("  material delta: " + ", ".join(payload["material_delta"]))
            for finding in payload["findings"]:
                print(f"  {finding['status']}: {finding['code']}")
            if evidence:
                print(f"  evidence: {evidence}")
        return result.exit_code
    if args.group == "drift":
        report = audit(
            args.repo_root,
            scope=args.scope,
            vault_root=args.vault_root,
            rule_ids=tuple(args.rule_id),
            previous=args.previous,
            project_path=args.project_path,
        )
    elif args.command == "verify":
        report = verify(
            args.repo_root,
            profile=args.profile,
            paths=tuple(args.path),
            tests=tuple(args.test),
            base=args.base,
            timeout=args.timeout,
        )
    elif args.command == "environment":
        report = project_environment(
            args.repo_root,
            uv=args.uv,
            python=args.python,
            environment=args.environment,
            cache_dir=args.cache_dir,
            mode=args.mode,
            binding_path=args.binding,
            allow_network=args.allow_network,
            offline_frozen=args.offline_frozen,
            timeout=args.timeout,
        )
    elif args.command == "supply-chain":
        if args.no_evidence and args.retain_sbom:
            raise ValueError("--no-evidence cannot be combined with --retain-sbom")
        scanner_tools = {}
        for item in args.tool:
            name, separator, path = item.partition("=")
            if not separator or name in scanner_tools:
                raise ValueError("--tool requires unique name=/absolute/executable")
            scanner_tools[name] = Path(path)
        report = supply_chain(
            args.repo_root,
            profile=args.profile,
            previous=args.previous,
            tools=scanner_tools,
            allow_network=args.allow_network,
            sbom=args.sbom,
            admission_manifest=args.admission_manifest,
            retain_sbom=args.retain_sbom,
            timeout=args.timeout,
        )
    else:
        state = repository_state(args.repo_root)
        report = Report(
            {"operation": "preflight"}, state, changed_paths=state["changed_paths"]
        )
        report.check("repository_identity", "passed")
        report.warnings.append(
            "Resolve authority, sandbox and dependency compatibility separately."
        )
    if not args.no_evidence:
        persist(report, Path(report.repository_state["root"]))
    if args.format == "json":
        print(json.dumps(report.payload(), ensure_ascii=False, sort_keys=True))
    else:
        print(f"{report.status}: {report.scope}")
        print(
            f"  status scope: {report.status_scope}; review: {report.review_status}; "
            f"decision: {report.decision}"
        )
        for check in report.checks:
            print(f"  {check['status']}: {check['name']}")
            if check.get("reason"):
                print(f"    {check['reason']}")
        for finding in report.findings:
            print(f"  finding: {json.dumps(finding, ensure_ascii=False)}")
        for blocker in report.blockers:
            print(f"  blocker: {blocker}")
        for warning in report.warnings:
            print(f"  warning: {warning}")
        for path in report.evidence_refs:
            print(f"  evidence: {path}")
    return report.exit_code
