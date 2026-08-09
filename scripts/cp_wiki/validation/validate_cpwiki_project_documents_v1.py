#!/usr/bin/env python3
"""Run Project Document Validation Engine v1.0 against a cp-wiki Vault."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cp_knowledge_tools.validation.project_documents import (
    PROFILE_COMPLETE,
    PROFILES,
    ProjectDocumentValidationError,
    run_self_test,
    validate_project_documents,
    write_project_document_reports,
)

DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_REPORT_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/"
    "cp-wiki/validation/project-documents"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate cp-wiki project_document files read-only against "
            "CPKS-SPEC-PDOC@0.1."
        )
    )
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--profile", choices=PROFILES, default=PROFILE_COMPLETE)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the deterministic in-memory engine self-test.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        try:
            result = run_self_test()
        except ProjectDocumentValidationError as exc:
            print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
            return 2
        print("Project Document Validation Engine v1.0 self-test passed.")
        print(json.dumps(result, indent=2))
        return 0

    try:
        result = validate_project_documents(args.vault, args.profile)
        json_report, markdown_report = write_project_document_reports(
            result, args.report_root
        )
    except ProjectDocumentValidationError as exc:
        print(f"TECHNICAL ERROR: {exc}", file=sys.stderr)
        return 2

    print("Project Document Validation Engine v1.0 completed read-only.")
    print(f"Profile:            {result.profile}")
    print(f"Project documents:  {result.inventory['total']}")
    print(f"Current:            {result.inventory['current']}")
    print(f"History:            {result.inventory['history']}")
    print(f"Warnings:           {result.summary['warning']}")
    print(f"Info:               {result.summary['info']}")
    print(f"JSON report:        {json_report}")
    print(f"Markdown report:    {markdown_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
