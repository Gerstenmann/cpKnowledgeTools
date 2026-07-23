"""Deterministic Markdown rendering."""

from __future__ import annotations

from .models import ContextSpec, DocumentSpec
from .yaml_io import dump_frontmatter


def render_document(document: DocumentSpec) -> str:
    chunks: list[str] = [dump_frontmatter(document.frontmatter).rstrip("\n"), ""]
    for section in document.sections:
        chunks.append(f"{'#' * section.level} {section.heading}")
        chunks.append("")
        chunks.append(f"<!-- AUTHORING: {section.instruction} -->")
        chunks.append("")
        if section.starter:
            chunks.extend(section.starter)
            chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def render_explanation(context: ContextSpec) -> str:
    lines: list[str] = [
        "---",
        "document_type: template_documentation",
        f"template_context: {context.context_id}",
        f'title: "Erläuterung – {context.title}"',
        f'version: "{context.version}"',
        "status: active",
        "sensitivity: internal",
        "memory_eligible: false",
        "---",
        "",
        f"# Erläuterung – {context.title}",
        "",
        context.description,
        "",
        "## Verwendung",
        "",
        "1. Den benötigten Template-Ordner oder eine einzelne Markup-Datei duplizieren.",
        "2. Dateinamen, stabile IDs und Platzhalterwerte ersetzen.",
        "3. Die AUTHORING-Kommentare in den Abschnitten beachten; sie dürfen nach der Bearbeitung entfernt werden.",
        "4. YAML und Markdown vor Übernahme in einen kanonischen Vault-Bereich validieren.",
        "5. Keine personenbezogenen Detaildaten oder Secrets in Vorlagen oder Standard-Retrieval übernehmen.",
        "",
        "## Ordner",
        "",
    ]

    for directory in context.directories:
        lines.extend(
            [
                f"### `{directory.path.as_posix()}/`",
                "",
                f"**Funktion:** {directory.purpose}",
                "",
                f"**Beispiel:** {directory.example}",
                "",
            ]
        )

    lines.extend(["## Markup-Dateien", ""])
    for document in context.documents:
        lines.extend(
            [
                f"### `{document.path.as_posix()}`",
                "",
                f"**Funktion:** {document.purpose}",
                "",
                f"**Beispiel für die Verwendung:** {document.example}",
                "",
                "#### YAML-Frontmatter",
                "",
                "Das Frontmatter enthält mindestens die für den jeweiligen Dokumenttyp erforderlichen Identitäts-, Status-, Zugriffs- und Retrieval-Metadaten. Platzhalter wie `TBD` müssen beim Instanziieren ersetzt werden.",
                "",
                "#### Abschnitte",
                "",
            ]
        )
        for section in document.sections:
            lines.extend(
                [
                    f"- **{section.heading}:** {section.instruction}",
                    f"  - Beispiel: {section.example}",
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Validierungsregeln",
            "",
            "- UTF-8 ohne BOM.",
            "- LF-Zeilenenden.",
            "- Keine Tabulatoren in YAML oder Markdown-Einrückungen.",
            "- YAML beginnt in der ersten Dateizeile und verwendet eindeutige Schlüssel.",
            "- Listen werden in Blockform geschrieben; leere Listen bleiben `[]`.",
            "- Die definierte Schlüssel- und Abschnittsreihenfolge bleibt erhalten.",
            "- Jede Datei endet mit genau einem Newline-Zeichen.",
            "- Generierung überschreibt bestehende Dateien nur mit `--force`.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
