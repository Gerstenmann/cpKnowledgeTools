"""Command-line interface for DSM validation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from cp_knowledge_tools.taxonomy.validator import DSMValidator


def _discover_markdown_files(
    inputs: Sequence[str],
) -> list[Path]:
    discovered: set[Path] = set()

    for raw_input in inputs:
        path = Path(raw_input).expanduser().resolve()

        if path.is_file():
            discovered.add(path)
            continue

        if path.is_dir():
            discovered.update(path.rglob("*.md"))
            continue

        raise FileNotFoundError(f"Input path does not exist: {path}")

    return sorted(discovered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cp-taxonomy-validate",
        description=("Validate Domain Specific Markup documents."),
    )

    parser.add_argument(
        "paths",
        nargs="+",
        help=("Markdown files or directories containing Domain DSM documents."),
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        files = _discover_markdown_files(args.paths)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 2

    if not files:
        print("ERROR: No Markdown files found.")
        return 2

    validator = DSMValidator()
    issue_count = 0

    for file_path in files:
        result = validator.validate_file(file_path)

        for issue in result.issues:
            print(issue.render())
            issue_count += 1

    if issue_count:
        print(f"\nValidation failed: {issue_count} issue(s) in {len(files)} file(s).")
        return 1

    print(f"Validation successful: {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
