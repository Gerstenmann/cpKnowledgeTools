"""Filesystem generation engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .context_loader import load_context
from .errors import UnsafePathError
from .models import ContextSpec
from .renderer import render_document, render_explanation
from .validation import OutputValidator


@dataclass(frozen=True)
class GenerationResult:
    context_id: str
    output_root: Path
    created_directories: tuple[Path, ...]
    written_files: tuple[Path, ...]
    skipped_files: tuple[Path, ...]
    validation_errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.validation_errors


class TemplateGenerator:
    def __init__(self, context_dir: Path | None = None) -> None:
        self.context_dir = context_dir
        self.validator = OutputValidator()

    def generate(
        self,
        context_id: str,
        output_base: Path,
        *,
        force: bool = False,
        validate: bool = True,
    ) -> GenerationResult:
        context = load_context(context_id, self.context_dir)
        output_base = output_base.expanduser().resolve()
        context_root = self._safe_join(output_base, context.output_root)
        context_root.mkdir(parents=True, exist_ok=True)

        created_directories: list[Path] = []
        written_files: list[Path] = []
        skipped_files: list[Path] = []

        for directory in context.directories:
            path = self._safe_join(context_root, directory.path)
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created_directories.append(path)
            elif not path.is_dir():
                raise UnsafePathError(f"Erwartetes Verzeichnis ist eine Datei: {path}")

        for document in context.documents:
            path = self._safe_join(context_root, document.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not force:
                skipped_files.append(path)
                continue
            path.write_text(render_document(document), encoding="utf-8", newline="\n")
            written_files.append(path)

        explanation_path = context_root / "Erläuterung.md"
        if explanation_path.exists() and not force:
            skipped_files.append(explanation_path)
        else:
            explanation_path.write_text(
                render_explanation(context), encoding="utf-8", newline="\n"
            )
            written_files.append(explanation_path)

        self._write_manifest(context, context_root, written_files, skipped_files)
        validation_errors = (
            tuple(self.validator.validate_context_output(context, output_base))
            if validate
            else ()
        )

        return GenerationResult(
            context_id=context.context_id,
            output_root=context_root,
            created_directories=tuple(created_directories),
            written_files=tuple(written_files),
            skipped_files=tuple(skipped_files),
            validation_errors=validation_errors,
        )

    def validate(self, context_id: str, output_base: Path) -> list[str]:
        context = load_context(context_id, self.context_dir)
        return self.validator.validate_context_output(
            context, output_base.expanduser().resolve()
        )

    @staticmethod
    def default_output_base() -> Path:
        return Path.home() / "Downloads" / "cp-wiki-template-output"

    @staticmethod
    def _safe_join(root: Path, relative: Path) -> Path:
        root = root.resolve()
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            raise UnsafePathError(f"Pfad verlässt das Ausgabeziel: {relative}")
        return target

    @staticmethod
    def _write_manifest(
        context: ContextSpec,
        context_root: Path,
        written_files: list[Path],
        skipped_files: list[Path],
    ) -> None:
        manifest_path = context_root / ".generation-manifest.json"
        payload = {
            "generator": "cpKnowledgeSystem Template Generator",
            "context_id": context.context_id,
            "context_version": context.version,
            "generated_at": datetime.now(UTC).isoformat(),
            "output_root": context.output_root.as_posix(),
            "written_files": [
                str(path.relative_to(context_root)) for path in written_files
            ],
            "skipped_files": [
                str(path.relative_to(context_root)) for path in skipped_files
            ],
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
