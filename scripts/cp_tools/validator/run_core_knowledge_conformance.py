from __future__ import annotations

import argparse
from pathlib import Path

from cp_knowledge_tools.publication import load_publication_unit
from cp_knowledge_tools.validation.core import (
    CoreKnowledgeValidator,
    CoreValidationInputError,
    integrity_failure_report,
    load_json_object,
    load_manifest,
    prepare_core_inputs,
    run_core_knowledge_corpus,
    write_json_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the executable Core Knowledge Profile and Golden Corpus."
    )
    parser.add_argument("--profile-manifest", type=Path, required=True)
    parser.add_argument("--corpus-manifest", type=Path, required=True)
    parser.add_argument("--corpus-payload", type=Path, required=True)
    parser.add_argument(
        "--required-profile-manifest",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--publication-unit", type=Path)
    parser.add_argument("--publication-report", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        inputs = prepare_core_inputs(
            profile_manifest=load_manifest(args.profile_manifest),
            corpus_manifest=load_manifest(args.corpus_manifest),
            corpus_payload=load_json_object(args.corpus_payload),
            required_profile_manifests=[
                load_manifest(path) for path in args.required_profile_manifest
            ],
        )
        validator = CoreKnowledgeValidator(inputs)
        report = run_core_knowledge_corpus(inputs, validator=validator)
        write_json_report(report, args.report)
        if report["overall_status"] != "pass":
            return 1
        if args.publication_unit is not None:
            publication_report_path = args.publication_report
            if publication_report_path is None:
                raise CoreValidationInputError(
                    "core_knowledge_report_path_missing",
                    "--publication-report is required with --publication-unit",
                )
            document = load_publication_unit(args.publication_unit)
            publication_report = validator.validate_publication_unit(
                document,
                source_ref=str(args.publication_unit),
            )
            write_json_report(publication_report, publication_report_path)
            return 0 if publication_report["conformance_status"] == "pass" else 1
        return 0
    except CoreValidationInputError as exc:
        write_json_report(integrity_failure_report(exc), args.report)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
