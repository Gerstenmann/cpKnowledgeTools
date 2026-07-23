"""Validation of generated Markdown and context-specific metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import OutputValidationError
from .models import ContextSpec, DocumentSpec
from .yaml_io import parse_frontmatter

SENSITIVITY_VALUES = {"public", "internal", "confidential", "restricted", "secret-reference-only"}
ENTITY_TYPES = {
    "organization",
    "product",
    "program",
    "service_offering",
    "operational_activity",
}
ENTITY_STATUS = {
    "organization": {"candidate", "active", "inactive", "deprecated", "archived"},
    "product": {"candidate", "active", "inactive", "deprecated", "archived"},
    "program": {"idea", "draft", "active", "paused", "retired", "archived"},
    "service_offering": {"idea", "draft", "active", "paused", "retired", "archived"},
    "operational_activity": {"planned", "confirmed", "active", "completed", "evaluated", "archived"},
}
RUN_STATUS = {"draft", "active", "deprecated", "archived"}
ID_VALUE = re.compile(r"^[A-Z][A-Z0-9-]*$")


class OutputValidator:
    def validate_context_output(self, context: ContextSpec, root: Path) -> list[str]:
        errors: list[str] = []
        context_root = root / context.output_root
        expected_files = [context_root / document.path for document in context.documents]
        expected_files.append(context_root / "Erläuterung.md")

        for directory in context.directories:
            path = context_root / directory.path
            if not path.is_dir():
                errors.append(f"Fehlendes Verzeichnis: {path}")

        for document, path in zip(context.documents, expected_files[:-1], strict=True):
            if not path.is_file():
                errors.append(f"Fehlende Datei: {path}")
                continue
            try:
                self.validate_file(path, document)
            except OutputValidationError as exc:
                errors.append(str(exc))

        explanation = expected_files[-1]
        if not explanation.is_file():
            errors.append(f"Fehlende Datei: {explanation}")
        else:
            try:
                self.validate_generic_markdown(explanation)
            except OutputValidationError as exc:
                errors.append(str(exc))
        return errors

    def validate_file(self, path: Path, document: DocumentSpec) -> None:
        text = self._read_text(path)
        self._validate_text_rules(text, path)
        frontmatter, markdown = parse_frontmatter(text, path)
        self._validate_metadata(frontmatter, path)
        self._validate_sections(markdown, document, path)

    def validate_generic_markdown(self, path: Path) -> None:
        text = self._read_text(path)
        self._validate_text_rules(text, path)
        frontmatter, _ = parse_frontmatter(text, path)
        self._require(frontmatter, ["document_type", "title", "status", "sensitivity", "memory_eligible"], path)

    @staticmethod
    def _read_text(path: Path) -> str:
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OutputValidationError(f"{path}: Datei ist nicht gültiges UTF-8.") from exc

    @staticmethod
    def _validate_text_rules(text: str, path: Path) -> None:
        if "\r" in text:
            raise OutputValidationError(f"{path}: Nur LF-Zeilenenden sind zulässig.")
        if "\t" in text:
            raise OutputValidationError(f"{path}: Tabulatorzeichen sind nicht zulässig.")
        if not text.endswith("\n") or text.endswith("\n\n"):
            raise OutputValidationError(f"{path}: Datei muss mit genau einem Newline enden.")
        if any(char in text for char in ("“", "”", "„", "‘", "’", "‚")):
            raise OutputValidationError(f"{path}: Typografische Anführungszeichen sind nicht zulässig.")

    def _validate_metadata(self, data: dict[str, Any], path: Path) -> None:
        self._require(data, ["document_type", "title", "status", "sensitivity", "memory_eligible"], path)
        if data["sensitivity"] not in SENSITIVITY_VALUES:
            raise OutputValidationError(f"{path}: Ungültige sensitivity: {data['sensitivity']!r}")
        if not isinstance(data["memory_eligible"], bool):
            raise OutputValidationError(f"{path}: memory_eligible muss boolean sein.")
        if "contains_personal_data" in data and not isinstance(data["contains_personal_data"], bool):
            raise OutputValidationError(f"{path}: contains_personal_data muss boolean sein.")

        document_type = data["document_type"]
        if document_type == "entity_document":
            self._require(
                data,
                ["entity_id", "entity_type", "owner", "aliases", "related_entities"],
                path,
            )
            entity_type = data["entity_type"]
            if entity_type not in ENTITY_TYPES:
                raise OutputValidationError(f"{path}: Ungültiger entity_type: {entity_type!r}")
            if data["status"] not in ENTITY_STATUS[entity_type]:
                raise OutputValidationError(
                    f"{path}: Status {data['status']!r} ist für {entity_type!r} nicht zulässig."
                )
            self._validate_id(data["entity_id"], "entity_id", path)
            self._validate_list(data["aliases"], "aliases", path)
            self._validate_list(data["related_entities"], "related_entities", path)
        elif document_type == "run_document":
            self._require(data, ["document_id", "primary_entity", "owner"], path)
            if data["status"] not in RUN_STATUS:
                raise OutputValidationError(f"{path}: Ungültiger Run-Status: {data['status']!r}")
            self._validate_id(data["document_id"], "document_id", path)
        elif document_type in {"human_note", "template_documentation"}:
            if data["status"] not in {"draft", "active", "archived"}:
                raise OutputValidationError(f"{path}: Ungültiger Status: {data['status']!r}")
        else:
            raise OutputValidationError(f"{path}: Unbekannter document_type: {document_type!r}")

    @staticmethod
    def _require(data: dict[str, Any], keys: list[str], path: Path) -> None:
        missing = [key for key in keys if key not in data]
        if missing:
            raise OutputValidationError(f"{path}: Fehlende Pflichtfelder: {', '.join(missing)}")

    @staticmethod
    def _validate_list(value: Any, field: str, path: Path) -> None:
        if not isinstance(value, list):
            raise OutputValidationError(f"{path}: {field} muss eine Liste sein.")

    @staticmethod
    def _validate_id(value: Any, field: str, path: Path) -> None:
        if not isinstance(value, str) or not ID_VALUE.fullmatch(value):
            raise OutputValidationError(
                f"{path}: {field} muss Großbuchstaben, Zahlen und Bindestriche verwenden: {value!r}"
            )

    @staticmethod
    def _validate_sections(markdown: str, document: DocumentSpec, path: Path) -> None:
        cursor = -1
        for section in document.sections:
            marker = f"{'#' * section.level} {section.heading}\n"
            found = markdown.find(marker, cursor + 1)
            if found < 0:
                raise OutputValidationError(f"{path}: Fehlender Abschnitt: {marker.strip()}")
            if found <= cursor:
                raise OutputValidationError(f"{path}: Falsche Abschnittsreihenfolge: {marker.strip()}")
            cursor = found
