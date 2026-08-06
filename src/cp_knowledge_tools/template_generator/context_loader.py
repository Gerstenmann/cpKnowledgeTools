"""Load and validate declarative context manifests."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import ContextValidationError
from .models import ContextSpec, DirectorySpec, DocumentSpec, SectionSpec
from .yaml_io import load_yaml_file

_CONTEXT_ID = re.compile(r"^[a-z][a-z0-9_-]*$")


def builtin_context_dir() -> Path:
    return Path(
        str(
            files("cp_knowledge_tools.template_generator.resources").joinpath(
                "contexts"
            )
        )
    )


def available_contexts(context_dir: Path | None = None) -> list[str]:
    directory = context_dir or builtin_context_dir()
    return sorted(path.stem for path in directory.glob("*.yaml") if path.is_file())


def load_context(context_id: str, context_dir: Path | None = None) -> ContextSpec:
    directory = context_dir or builtin_context_dir()
    path = directory / f"{context_id}.yaml"
    if not path.is_file():
        choices = ", ".join(available_contexts(directory)) or "keine"
        raise ContextValidationError(
            f"Unbekannter Kontext '{context_id}'. Verfügbar: {choices}"
        )
    data = load_yaml_file(path)
    return context_from_mapping(data, source=path)


def _safe_relative_path(value: Any, field: str, source: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ContextValidationError(
            f"{source}: {field} muss ein nichtleerer String sein."
        )
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts:
        raise ContextValidationError(
            f"{source}: Unsicherer relativer Pfad in {field}: {value!r}"
        )
    return Path(*posix.parts)


def _require_text(value: Any, field: str, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextValidationError(
            f"{source}: {field} muss ein nichtleerer String sein."
        )
    return value.strip()


def context_from_mapping(data: dict[str, Any], source: Path) -> ContextSpec:
    context_id = _require_text(data.get("context_id"), "context_id", source)
    if not _CONTEXT_ID.fullmatch(context_id):
        raise ContextValidationError(f"{source}: Ungültige context_id: {context_id!r}")

    title = _require_text(data.get("title"), "title", source)
    version = _require_text(str(data.get("version", "")), "version", source)
    description = _require_text(data.get("description"), "description", source)
    output_root = _safe_relative_path(data.get("output_root"), "output_root", source)

    raw_dirs = data.get("directories", [])
    raw_docs = data.get("documents", [])
    if not isinstance(raw_dirs, list) or not isinstance(raw_docs, list):
        raise ContextValidationError(
            f"{source}: directories und documents müssen Listen sein."
        )

    directories: list[DirectorySpec] = []
    seen_dirs: set[Path] = set()
    for index, item in enumerate(raw_dirs):
        if not isinstance(item, dict):
            raise ContextValidationError(
                f"{source}: directories[{index}] muss ein Mapping sein."
            )
        directory = DirectorySpec(
            path=_safe_relative_path(
                item.get("path"), f"directories[{index}].path", source
            ),
            purpose=_require_text(
                item.get("purpose"), f"directories[{index}].purpose", source
            ),
            example=_require_text(
                item.get("example"), f"directories[{index}].example", source
            ),
        )
        if directory.path in seen_dirs:
            raise ContextValidationError(
                f"{source}: Doppelter Verzeichnispfad: {directory.path}"
            )
        seen_dirs.add(directory.path)
        directories.append(directory)

    documents: list[DocumentSpec] = []
    seen_docs: set[Path] = set()
    for index, item in enumerate(raw_docs):
        if not isinstance(item, dict):
            raise ContextValidationError(
                f"{source}: documents[{index}] muss ein Mapping sein."
            )
        doc_path = _safe_relative_path(
            item.get("path"), f"documents[{index}].path", source
        )
        if doc_path.suffix.lower() != ".md":
            raise ContextValidationError(
                f"{source}: Dokument muss auf .md enden: {doc_path}"
            )
        frontmatter = item.get("frontmatter")
        if not isinstance(frontmatter, dict) or not frontmatter:
            raise ContextValidationError(
                f"{source}: {doc_path} benötigt Frontmatter als Mapping."
            )
        raw_sections = item.get("sections", [])
        if not isinstance(raw_sections, list) or not raw_sections:
            raise ContextValidationError(
                f"{source}: {doc_path} benötigt mindestens einen Abschnitt."
            )

        sections: list[SectionSpec] = []
        seen_headings: set[tuple[int, str]] = set()
        for sec_index, section in enumerate(raw_sections):
            if not isinstance(section, dict):
                raise ContextValidationError(
                    f"{source}: documents[{index}].sections[{sec_index}] muss ein Mapping sein."
                )
            level = section.get("level")
            if not isinstance(level, int) or not 1 <= level <= 6:
                raise ContextValidationError(
                    f"{source}: Ungültige Überschriftenebene für {doc_path}: {level!r}"
                )
            heading = _require_text(
                section.get("heading"),
                f"documents[{index}].sections[{sec_index}].heading",
                source,
            )
            heading_key = (level, heading.casefold())
            if heading_key in seen_headings:
                raise ContextValidationError(
                    f"{source}: Doppelte Überschrift in {doc_path}: {heading}"
                )
            seen_headings.add(heading_key)
            starter = section.get("starter", [])
            if not isinstance(starter, list) or not all(
                isinstance(line, str) for line in starter
            ):
                raise ContextValidationError(
                    f"{source}: starter muss eine String-Liste sein: {doc_path}"
                )
            sections.append(
                SectionSpec(
                    heading=heading,
                    level=level,
                    instruction=_require_text(
                        section.get("instruction"),
                        f"documents[{index}].sections[{sec_index}].instruction",
                        source,
                    ),
                    example=_require_text(
                        section.get("example"),
                        f"documents[{index}].sections[{sec_index}].example",
                        source,
                    ),
                    starter=starter,
                )
            )

        document = DocumentSpec(
            path=doc_path,
            purpose=_require_text(
                item.get("purpose"), f"documents[{index}].purpose", source
            ),
            example=_require_text(
                item.get("example"), f"documents[{index}].example", source
            ),
            frontmatter=frontmatter,
            sections=sections,
        )
        if document.path in seen_docs:
            raise ContextValidationError(
                f"{source}: Doppelter Dokumentpfad: {document.path}"
            )
        seen_docs.add(document.path)
        documents.append(document)

    return ContextSpec(
        context_id=context_id,
        title=title,
        version=version,
        description=description,
        output_root=output_root,
        directories=directories,
        documents=documents,
    )
