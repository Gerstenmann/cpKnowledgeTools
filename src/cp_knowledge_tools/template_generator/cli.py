"""Command-line interface for template generation and validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .context_loader import available_contexts, load_context
from .errors import (
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
    TemplateGeneratorError,
)
from .generator import TemplateGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cp-template",
        description="Erzeugt cp-wiki Filetrees und validierungstreue Markdown-Templates.",
    )
    parser.add_argument(
        "--context-dir",
        type=Path,
        help="Optionales Verzeichnis mit eigenen Kontext-YAML-Dateien.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Verfügbare Generierungskontexte anzeigen.")

    show = sub.add_parser("show", help="Metadaten eines Kontexts anzeigen.")
    show.add_argument("context")

    generate = sub.add_parser("generate", help="Template-Kontext erzeugen.")
    generate.add_argument("context", nargs="+", help="Kontext-ID oder 'all'.")
    generate.add_argument(
        "--output",
        type=Path,
        default=TemplateGenerator.default_output_base(),
        help="Ausgabebasis; Standard: ~/Downloads/cp-wiki-template-output",
    )
    generate.add_argument(
        "--force", action="store_true", help="Bestehende Dateien überschreiben."
    )
    generate.add_argument(
        "--no-validate", action="store_true", help="Nachvalidierung überspringen."
    )

    validate = sub.add_parser("validate", help="Bereits erzeugten Kontext validieren.")
    validate.add_argument("context", nargs="+", help="Kontext-ID oder 'all'.")
    validate.add_argument(
        "--output",
        type=Path,
        default=TemplateGenerator.default_output_base(),
        help="Ausgabebasis; Standard: ~/Downloads/cp-wiki-template-output",
    )
    return parser


def _resolve_contexts(values: list[str], context_dir: Path | None) -> list[str]:
    if "all" in values:
        if len(values) > 1:
            raise ValueError(
                "'all' darf nicht mit weiteren Kontexten kombiniert werden."
            )
        return available_contexts(context_dir)
    return values


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    generator = TemplateGenerator(args.context_dir)

    try:
        if args.command == "list":
            for context_id in available_contexts(args.context_dir):
                print(context_id)
            return EXIT_OK

        if args.command == "show":
            context = load_context(args.context, args.context_dir)
            print(f"ID: {context.context_id}")
            print(f"Titel: {context.title}")
            print(f"Version: {context.version}")
            print(f"Ausgabe: {context.output_root}")
            print(f"Verzeichnisse: {len(context.directories)}")
            print(f"Dokumente: {len(context.documents) + 1} inklusive Erläuterung.md")
            return EXIT_OK

        context_ids = _resolve_contexts(args.context, args.context_dir)
        if not context_ids:
            print("Keine Kontexte verfügbar.", file=sys.stderr)
            return EXIT_USAGE_ERROR

        if args.command == "generate":
            failed = False
            for context_id in context_ids:
                result = generator.generate(
                    context_id,
                    args.output,
                    force=args.force,
                    validate=not args.no_validate,
                )
                print(f"[{context_id}] Ausgabe: {result.output_root}")
                print(
                    f"[{context_id}] Dateien geschrieben: {len(result.written_files)}"
                )
                print(
                    f"[{context_id}] Dateien übersprungen: {len(result.skipped_files)}"
                )
                if result.validation_errors:
                    failed = True
                    for error in result.validation_errors:
                        print(f"ERROR: {error}", file=sys.stderr)
                else:
                    print(f"[{context_id}] Validierung: OK")
            return EXIT_VALIDATION_ERROR if failed else EXIT_OK

        if args.command == "validate":
            failed = False
            for context_id in context_ids:
                errors = generator.validate(context_id, args.output)
                if errors:
                    failed = True
                    for error in errors:
                        print(f"ERROR: {error}", file=sys.stderr)
                else:
                    print(f"[{context_id}] Validierung: OK")
            return EXIT_VALIDATION_ERROR if failed else EXIT_OK

        parser.error("Unbekannter Befehl")
        return EXIT_USAGE_ERROR

    except (TemplateGeneratorError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"INTERNAL ERROR: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
