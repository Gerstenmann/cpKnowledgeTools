from __future__ import annotations

import argparse
from pathlib import Path

from cp_knowledge_tools.common.config import (
    load_classification_rules,
    load_project_config,
)
from cp_knowledge_tools.importers.mbox.classifier import apply_classification
from cp_knowledge_tools.importers.mbox.exporter import (
    write_jsonl,
    write_markdown_files,
)
from cp_knowledge_tools.importers.mbox.filter import partition_emails
from cp_knowledge_tools.importers.mbox.overrides import (
    apply_override,
    load_overrides,
)
from cp_knowledge_tools.importers.mbox.reader import read_mbox
from cp_knowledge_tools.importers.mbox.reporter import write_reports

PROJECT_ROOT = Path(__file__).resolve().parents[3]

def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Importiert eine MBOX-Datei und exportiert "
            "die E-Mails als JSONL und Markdown."
        )
    )

    parser.add_argument(
        "input_mbox",
        type=Path,
        help="Pfad zur MBOX-Datei",
    )

    parser.add_argument(
        "--jsonl",
        type=Path,
        required=True,
        help="Zieldatei für den JSONL-Export",
    )

    parser.add_argument(
        "--markdown-dir",
        type=Path,
        required=True,
        help="Zielordner für die Markdown-Dateien",
    )

    return parser


def run_import(
    input_mbox: Path,
    jsonl_path: Path,
    markdown_dir: Path,
) -> dict[str, int]:
    """Run the complete MBOX import and filtering pipeline."""
    config = load_project_config()

    rules = load_classification_rules(config.rules_path)
    
    overrides = load_overrides(config.overrides_path)

    classified_emails = [
        apply_override(
            apply_classification(
                email,
                rules,
            ),
            overrides,
        )
        for email in read_mbox(input_mbox)
    ]

    buckets = partition_emails(classified_emails)

    reports_dir = (
        markdown_dir.parent
        / config.reports_dir_name
    )

    write_reports(
        emails=classified_emails,
        reports_dir=reports_dir,
        sample_size=config.sample_size,
    )
    
    # Vollständiger, revisionsfähiger Export:
    # Jede Mail bleibt mit Klassifikation und Entscheidung erhalten.
    all_jsonl_count = write_jsonl(
        classified_emails,
        jsonl_path,
    )

    # Nur Mails mit Wissenspotenzial erhalten Markdown-Dateien.
    analyze_count = write_markdown_files(
        buckets.analyze,
        markdown_dir / "analyze",
    )

    review_count = write_markdown_files(
        buckets.review,
        markdown_dir / "review",
    )

    archive_only_count = write_markdown_files(
        buckets.archive_only,
        markdown_dir / "archive_only",
    )

    discard_count = write_markdown_files(
        buckets.discard,
        markdown_dir / "discard",
    )

    return {
        "total": buckets.total_count,
        "jsonl": all_jsonl_count,
        "analyze": analyze_count,
        "review": review_count,
        "archive_only": len(buckets.archive_only),
        "discard": len(buckets.discard),
    }


def main() -> None:
    """Entry point for the command-line interface."""
    parser = build_parser()
    args = parser.parse_args()

    statistics = run_import(
        input_mbox=args.input_mbox,
        jsonl_path=args.jsonl,
        markdown_dir=args.markdown_dir,
    )

    print("Import abgeschlossen.")
    print(f"Gesamtzahl E-Mails: {statistics['total']}")
    print(f"JSONL-Datensätze: {statistics['jsonl']}")
    print(f"Für Analyse: {statistics['analyze']}")
    print(f"Zur Prüfung: {statistics['review']}")
    print(f"Nur archiviert: {statistics['archive_only']}")
    print(f"Ausgesondert: {statistics['discard']}")
    print(f"JSONL: {args.jsonl}")
    print(f"Markdown: {args.markdown_dir}")


if __name__ == "__main__":
    main()
