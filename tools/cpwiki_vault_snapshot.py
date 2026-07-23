#!/usr/bin/env python3
"""Create versioned cp-wiki vault snapshots and compare IST vs SOLL.

The tool reads file-system metadata only. File contents are not read unless
--read-frontmatter is explicitly enabled for Markdown files.

Outputs per snapshot:
- manifest.json         machine-readable snapshot metadata
- inventory.jsonl       one record per file-system item
- inventory.csv         spreadsheet-friendly inventory
- tree.md               human/LLM-readable tree
- snapshot-report.md    consolidated development-step report
- comparison.json/.md   IST/SOLL comparison (when --expected is supplied)
- delta.json/.md        change set versus previous snapshot (when available)
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

TOOL_NAME = "cpwiki-vault-snapshot"
TOOL_VERSION = "1.0.0"
DEFAULT_EXCLUDES = (
    ".git",
    ".obsidian",
    ".trash",
    ".Trash",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
)


@dataclass(frozen=True)
class InventoryItem:
    relative_path: str
    name: str
    item_type: str
    extension: str
    size_bytes: int
    modified_at: str
    modified_ns: int
    depth: int
    top_level: str
    is_hidden: bool
    is_symlink: bool
    link_target: str | None = None
    frontmatter: dict[str, Any] | None = None


@dataclass(frozen=True)
class GitState:
    available: bool
    repository_root: str | None = None
    branch: str | None = None
    commit: str | None = None
    commit_short: str | None = None
    dirty: bool | None = None
    describe: str | None = None


@dataclass(frozen=True)
class ExpectedPath:
    path: str
    item_type: str
    severity: str
    rationale: str | None = None


class SnapshotError(RuntimeError):
    """Raised for controlled snapshot failures."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "snapshot"


def run_git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def detect_git_state(root: Path) -> GitState:
    repo_root = run_git(root, "rev-parse", "--show-toplevel")
    if not repo_root:
        return GitState(available=False)

    commit = run_git(root, "rev-parse", "HEAD")
    branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = run_git(root, "status", "--porcelain=v1")
    describe = run_git(root, "describe", "--always", "--dirty", "--tags")
    return GitState(
        available=True,
        repository_root=repo_root,
        branch=branch,
        commit=commit,
        commit_short=commit[:12] if commit else None,
        dirty=bool(status) if status is not None else None,
        describe=describe,
    )


def load_structured_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SnapshotError(
                "YAML-SOLLmodel requires PyYAML. Install with: python3 -m pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        raise SnapshotError(f"Unsupported expected-structure format: {path.suffix}")
    if not isinstance(data, dict):
        raise SnapshotError("Expected-structure file must contain a mapping/object at the root.")
    return data


def normalize_rel(path: Path) -> str:
    return path.as_posix().strip("/")


def path_is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def matches_exclude(relative: Path, patterns: Sequence[str]) -> bool:
    rel = normalize_rel(relative)
    name = relative.name
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern):
            return True
        if pattern in relative.parts:
            return True
    return False


def read_markdown_frontmatter(path: Path, max_bytes: int = 131_072) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        import yaml  # type: ignore
    except ImportError:
        return {"_warning": "PyYAML not installed; frontmatter not parsed"}
    try:
        parsed = yaml.safe_load(text[4:end])
    except Exception as exc:  # noqa: BLE001 - report malformed frontmatter without stopping snapshot
        return {"_error": str(exc)}
    return parsed if isinstance(parsed, dict) else None


def scan_vault(
    root: Path,
    exclude_patterns: Sequence[str],
    include_hidden: bool,
    read_frontmatter: bool,
    excluded_absolute_paths: Sequence[Path],
) -> tuple[list[InventoryItem], list[str]]:
    items: list[InventoryItem] = []
    errors: list[str] = []
    excluded_resolved = [p.resolve(strict=False) for p in excluded_absolute_paths]

    def is_under_excluded(candidate: Path) -> bool:
        resolved = candidate.resolve(strict=False)
        for excluded in excluded_resolved:
            try:
                resolved.relative_to(excluded)
                return True
            except ValueError:
                continue
        return False

    def onerror(exc: OSError) -> None:
        errors.append(f"{type(exc).__name__}: {exc}")

    for current_dir, dirnames, filenames in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        current = Path(current_dir)
        relative_dir = current.relative_to(root)

        kept_dirs: list[str] = []
        for dirname in sorted(dirnames, key=str.casefold):
            candidate = current / dirname
            rel = candidate.relative_to(root)
            if is_under_excluded(candidate):
                continue
            if not include_hidden and path_is_hidden(rel):
                continue
            if matches_exclude(rel, exclude_patterns):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        entries = [(name, "file") for name in filenames] + [(name, "dir") for name in dirnames]
        for name, kind in sorted(entries, key=lambda x: x[0].casefold()):
            absolute = current / name
            relative = absolute.relative_to(root)
            if is_under_excluded(absolute):
                continue
            if not include_hidden and path_is_hidden(relative):
                continue
            if matches_exclude(relative, exclude_patterns):
                continue

            try:
                stat = absolute.lstat()
            except OSError as exc:
                errors.append(f"{normalize_rel(relative)}: {type(exc).__name__}: {exc}")
                continue

            is_symlink = absolute.is_symlink()
            item_type = "symlink" if is_symlink else kind
            link_target: str | None = None
            if is_symlink:
                try:
                    link_target = os.readlink(absolute)
                except OSError as exc:
                    errors.append(f"{normalize_rel(relative)}: cannot read symlink: {exc}")

            frontmatter: dict[str, Any] | None = None
            if read_frontmatter and item_type == "file" and absolute.suffix.lower() == ".md":
                frontmatter = read_markdown_frontmatter(absolute)

            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            parts = relative.parts
            items.append(
                InventoryItem(
                    relative_path=normalize_rel(relative),
                    name=name,
                    item_type=item_type,
                    extension=absolute.suffix.lower() if item_type == "file" else "",
                    size_bytes=stat.st_size if item_type == "file" else 0,
                    modified_at=iso_utc(modified),
                    modified_ns=stat.st_mtime_ns,
                    depth=len(parts),
                    top_level=parts[0] if parts else "",
                    is_hidden=path_is_hidden(relative),
                    is_symlink=is_symlink,
                    link_target=link_target,
                    frontmatter=frontmatter,
                )
            )

    items.sort(key=lambda item: (item.relative_path.casefold(), item.item_type))
    return items, errors


def fingerprints(items: Sequence[InventoryItem]) -> tuple[str, str]:
    structure = hashlib.sha256()
    state = hashlib.sha256()
    for item in items:
        base = f"{item.relative_path}\0{item.item_type}\n".encode("utf-8")
        structure.update(base)
        state.update(base)
        state.update(f"{item.size_bytes}\0{item.modified_ns}\n".encode("utf-8"))
    return structure.hexdigest(), state.hexdigest()


def aggregate_top_level(items: Sequence[InventoryItem]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for item in items:
        bucket = summary.setdefault(
            item.top_level,
            {"name": item.top_level, "directories": 0, "files": 0, "symlinks": 0, "size_bytes": 0},
        )
        if item.item_type == "dir":
            bucket["directories"] += 1
        elif item.item_type == "file":
            bucket["files"] += 1
            bucket["size_bytes"] += item.size_bytes
        else:
            bucket["symlinks"] += 1
    return sorted(summary.values(), key=lambda row: row["name"].casefold())


def extension_summary(items: Sequence[InventoryItem], limit: int = 30) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {}
    for item in items:
        if item.item_type != "file":
            continue
        ext = item.extension or "[no extension]"
        bucket = counts.setdefault(ext, {"count": 0, "size_bytes": 0})
        bucket["count"] += 1
        bucket["size_bytes"] += item.size_bytes
    rows = [{"extension": ext, **values} for ext, values in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["extension"]))
    return rows[:limit]


def render_tree(items: Sequence[InventoryItem], max_depth: int) -> str:
    paths = [item for item in items if max_depth <= 0 or item.depth <= max_depth]
    child_map: dict[str, list[InventoryItem]] = {}
    for item in paths:
        parent = normalize_rel(Path(item.relative_path).parent)
        if parent == ".":
            parent = ""
        child_map.setdefault(parent, []).append(item)

    for children in child_map.values():
        children.sort(key=lambda item: (item.item_type != "dir", item.name.casefold()))

    lines: list[str] = []

    def visit(parent: str, prefix: str) -> None:
        children = child_map.get(parent, [])
        for index, item in enumerate(children):
            last = index == len(children) - 1
            connector = "└── " if last else "├── "
            suffix = "/" if item.item_type == "dir" else (" → " + item.link_target if item.item_type == "symlink" and item.link_target else "")
            lines.append(f"{prefix}{connector}{item.name}{suffix}")
            if item.item_type == "dir":
                visit(item.relative_path, prefix + ("    " if last else "│   "))

    visit("", "")
    return "\n".join(lines)


def parse_expected(data: dict[str, Any]) -> tuple[dict[str, Any], list[ExpectedPath], list[str]]:
    specification = data.get("specification") or {}
    if not isinstance(specification, dict):
        raise SnapshotError("expected.specification must be a mapping")

    expected: list[ExpectedPath] = []
    for section, severity in (("required_paths", "required"), ("recommended_paths", "recommended"), ("deprecated_paths", "deprecated")):
        raw_items = data.get(section, [])
        if not isinstance(raw_items, list):
            raise SnapshotError(f"{section} must be a list")
        for raw in raw_items:
            if isinstance(raw, str):
                expected.append(ExpectedPath(path=raw.strip("/"), item_type="any", severity=severity))
            elif isinstance(raw, dict):
                expected.append(
                    ExpectedPath(
                        path=str(raw.get("path", "")).strip("/"),
                        item_type=str(raw.get("type", "any")),
                        severity=severity,
                        rationale=str(raw.get("rationale")) if raw.get("rationale") is not None else None,
                    )
                )
            else:
                raise SnapshotError(f"Invalid item in {section}: {raw!r}")

    allowed_top_level = data.get("allowed_top_level", [])
    if not isinstance(allowed_top_level, list):
        raise SnapshotError("allowed_top_level must be a list")
    return specification, expected, [str(value) for value in allowed_top_level]


def compare_expected(items: Sequence[InventoryItem], expected_data: dict[str, Any]) -> dict[str, Any]:
    specification, expected_paths, allowed_top_level = parse_expected(expected_data)
    actual = {item.relative_path: item for item in items}
    actual_top = sorted({item.top_level for item in items if item.depth == 1}, key=str.casefold)

    missing_required: list[dict[str, Any]] = []
    missing_recommended: list[dict[str, Any]] = []
    type_mismatches: list[dict[str, Any]] = []
    deprecated_present: list[dict[str, Any]] = []

    for exp in expected_paths:
        item = actual.get(exp.path)
        if exp.severity == "deprecated":
            if item:
                deprecated_present.append({"path": exp.path, "actual_type": item.item_type, "rationale": exp.rationale})
            continue
        if item is None:
            target = missing_required if exp.severity == "required" else missing_recommended
            target.append({"path": exp.path, "expected_type": exp.item_type, "rationale": exp.rationale})
            continue
        if exp.item_type != "any" and item.item_type != exp.item_type:
            type_mismatches.append(
                {
                    "path": exp.path,
                    "expected_type": exp.item_type,
                    "actual_type": item.item_type,
                    "severity": exp.severity,
                }
            )

    unexpected_top_level = [name for name in actual_top if allowed_top_level and name not in allowed_top_level]
    score_total = max(1, sum(1 for item in expected_paths if item.severity == "required"))
    score_ok = score_total - len(missing_required) - sum(1 for row in type_mismatches if row["severity"] == "required")
    compliance_percent = max(0.0, round(score_ok / score_total * 100, 1))
    status = "conformant" if not missing_required and not type_mismatches and not deprecated_present else "non-conformant"

    return {
        "specification": specification,
        "status": status,
        "required_compliance_percent": compliance_percent,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "type_mismatches": type_mismatches,
        "deprecated_present": deprecated_present,
        "unexpected_top_level": unexpected_top_level,
        "actual_top_level": actual_top,
        "allowed_top_level": allowed_top_level,
    }


def load_previous_manifest(output_base: Path, current_dir: Path, explicit: str | None) -> tuple[Path | None, dict[str, Any] | None]:
    if explicit and explicit.lower() != "latest":
        path = Path(explicit).expanduser().resolve()
        if path.is_dir():
            path = path / "manifest.json"
        if not path.exists():
            raise SnapshotError(f"Previous manifest not found: {path}")
        return path, json.loads(path.read_text(encoding="utf-8"))

    candidates = sorted(
        (path for path in output_base.glob("*/manifest.json") if path.parent != current_dir),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        return None, None
    path = candidates[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def compare_previous(items: Sequence[InventoryItem], previous_manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not previous_manifest:
        return None
    previous_items = previous_manifest.get("inventory", [])
    if not isinstance(previous_items, list):
        return None
    previous = {str(row.get("relative_path")): row for row in previous_items if isinstance(row, dict)}
    current = {item.relative_path: asdict(item) for item in items}

    added = sorted(set(current) - set(previous), key=str.casefold)
    removed = sorted(set(previous) - set(current), key=str.casefold)
    changed: list[dict[str, Any]] = []
    for path in sorted(set(current) & set(previous), key=str.casefold):
        before = previous[path]
        after = current[path]
        fields = [field for field in ("item_type", "size_bytes", "modified_ns", "link_target") if before.get(field) != after.get(field)]
        if fields:
            changed.append({"path": path, "fields": fields, "before": {f: before.get(f) for f in fields}, "after": {f: after.get(f) for f in fields}})
    return {"added": added, "removed": removed, "changed": changed}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_inventory_csv(path: Path, items: Sequence[InventoryItem]) -> None:
    fields = [
        "relative_path", "name", "item_type", "extension", "size_bytes", "modified_at",
        "modified_ns", "depth", "top_level", "is_hidden", "is_symlink", "link_target",
        "frontmatter",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            row["frontmatter"] = json.dumps(row["frontmatter"], ensure_ascii=False) if row["frontmatter"] is not None else ""
            writer.writerow(row)


def write_inventory_jsonl(path: Path, items: Sequence[InventoryItem]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.2f} {unit}"
        number /= 1024
    return f"{value} B"


def render_comparison_md(comparison: dict[str, Any]) -> str:
    spec = comparison.get("specification", {})
    lines = [
        "# IST/SOLL Comparison",
        "",
        f"- Specification: `{spec.get('id', 'unknown')}`",
        f"- Specification version: `{spec.get('version', 'unknown')}`",
        f"- Status: **{comparison['status']}**",
        f"- Required-path compliance: **{comparison['required_compliance_percent']}%**",
        "",
    ]
    sections = [
        ("Missing required paths", comparison["missing_required"]),
        ("Type mismatches", comparison["type_mismatches"]),
        ("Deprecated paths present", comparison["deprecated_present"]),
        ("Missing recommended paths", comparison["missing_recommended"]),
        ("Unexpected top-level items", comparison["unexpected_top_level"]),
    ]
    for title, rows in sections:
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("None.")
        else:
            for row in rows:
                if isinstance(row, str):
                    lines.append(f"- `{row}`")
                else:
                    path = row.get("path", "")
                    details = ", ".join(f"{key}={value}" for key, value in row.items() if key != "path" and value not in (None, ""))
                    lines.append(f"- `{path}`" + (f" — {details}" if details else ""))
        lines.append("")
    return "\n".join(lines)


def render_delta_md(delta: dict[str, Any] | None, previous_path: Path | None) -> str:
    lines = ["# Vault Snapshot Delta", ""]
    if not delta:
        lines.append("No previous snapshot was available.")
        return "\n".join(lines)
    lines.append(f"- Previous manifest: `{previous_path}`")
    lines.append(f"- Added: **{len(delta['added'])}**")
    lines.append(f"- Removed: **{len(delta['removed'])}**")
    lines.append(f"- Metadata-changed: **{len(delta['changed'])}**")
    lines.append("")
    for title, key in (("Added", "added"), ("Removed", "removed")):
        lines.extend([f"## {title}", ""])
        values = delta[key]
        if not values:
            lines.append("None.")
        else:
            lines.extend(f"- `{value}`" for value in values[:500])
            if len(values) > 500:
                lines.append(f"- … {len(values) - 500} more entries in delta.json")
        lines.append("")
    lines.extend(["## Metadata changed", ""])
    if not delta["changed"]:
        lines.append("None.")
    else:
        for row in delta["changed"][:500]:
            lines.append(f"- `{row['path']}` — {', '.join(row['fields'])}")
        if len(delta["changed"]) > 500:
            lines.append(f"- … {len(delta['changed']) - 500} more entries in delta.json")
    lines.append("")
    return "\n".join(lines)


def render_snapshot_report(manifest: dict[str, Any], comparison: dict[str, Any] | None, delta: dict[str, Any] | None) -> str:
    counts = manifest["counts"]
    git_state = manifest["git"]
    lines = [
        f"# cp-wiki Vault Snapshot — {manifest['snapshot_id']}",
        "",
        "## Development step",
        "",
        f"- Label: `{manifest.get('label') or 'unspecified'}`",
        f"- Captured at: `{manifest['captured_at']}`",
        f"- Tool: `{manifest['tool']['name']} {manifest['tool']['version']}`",
        f"- Expected specification: `{manifest.get('expected_specification_version') or 'not supplied'}`",
        "",
        "## Vault identity",
        "",
        f"- Root: `{manifest['vault']['root']}`",
        f"- Vault name: `{manifest['vault']['name']}`",
        f"- Git repository: `{git_state.get('repository_root') or 'not detected'}`",
        f"- Git branch: `{git_state.get('branch') or 'n/a'}`",
        f"- Git commit: `{git_state.get('commit') or 'n/a'}`",
        f"- Git dirty: `{git_state.get('dirty')}`",
        "",
        "## Snapshot summary",
        "",
        f"- Directories: **{counts['directories']}**",
        f"- Files: **{counts['files']}**",
        f"- Symlinks: **{counts['symlinks']}**",
        f"- Total file size: **{human_bytes(counts['size_bytes'])}**",
        f"- Structure fingerprint: `{manifest['fingerprints']['structure_sha256']}`",
        f"- State fingerprint: `{manifest['fingerprints']['state_sha256']}`",
        "",
        "## Top-level areas",
        "",
        "| Area | Directories | Files | Symlinks | Size |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in manifest["top_level"]:
        lines.append(
            f"| `{row['name']}` | {row['directories']} | {row['files']} | {row['symlinks']} | {human_bytes(row['size_bytes'])} |"
        )
    lines.append("")

    if comparison:
        lines.extend(
            [
                "## IST/SOLL result",
                "",
                f"- Status: **{comparison['status']}**",
                f"- Required-path compliance: **{comparison['required_compliance_percent']}%**",
                f"- Missing required paths: **{len(comparison['missing_required'])}**",
                f"- Missing recommended paths: **{len(comparison['missing_recommended'])}**",
                f"- Type mismatches: **{len(comparison['type_mismatches'])}**",
                f"- Deprecated paths present: **{len(comparison['deprecated_present'])}**",
                "- Detailed result: `comparison.md` and `comparison.json`",
                "",
            ]
        )

    if delta:
        lines.extend(
            [
                "## Change since previous snapshot",
                "",
                f"- Added: **{len(delta['added'])}**",
                f"- Removed: **{len(delta['removed'])}**",
                f"- Metadata-changed: **{len(delta['changed'])}**",
                "- Detailed result: `delta.md` and `delta.json`",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation rules",
            "",
            "- This snapshot records the structural IST state. It does not classify file contents as knowledge objects.",
            "- Missing recommended paths are architecture-review items, not necessarily defects.",
            "- Unexpected top-level items require classification; they are not automatically invalid.",
            "- File contents were not read unless frontmatter parsing was explicitly enabled.",
            "",
            "## Snapshot artifacts",
            "",
            "- `manifest.json` — complete machine-readable snapshot and embedded inventory",
            "- `inventory.jsonl` — one record per item",
            "- `inventory.csv` — tabular inventory",
            "- `tree.md` — human/LLM-readable tree",
            "- `comparison.md` / `comparison.json` — IST/SOLL result when configured",
            "- `delta.md` / `delta.json` — development-step delta when a previous snapshot exists",
            "- `errors.log` — scan errors, if any",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a versioned cp-wiki vault snapshot and optionally compare it with the expected architecture.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("vault", type=Path, help="Path to the cp-wiki vault")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "artifacts" / "vault-snapshots",
        help="Base directory containing one subdirectory per snapshot",
    )
    parser.add_argument("--expected", type=Path, help="YAML or JSON expected-structure model")
    parser.add_argument("--label", default="", help="Development-step label, e.g. 'after vault spec v1.2'")
    parser.add_argument("--snapshot-version", default="", help="Optional explicit snapshot/specification version")
    parser.add_argument("--max-tree-depth", type=int, default=8, help="Maximum depth rendered in tree.md; 0 means unlimited")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden files and directories")
    parser.add_argument("--read-frontmatter", action="store_true", help="Read YAML frontmatter from Markdown files")
    parser.add_argument("--exclude", action="append", default=[], help="Additional exclusion glob or path component; repeatable")
    parser.add_argument(
        "--previous",
        default="latest",
        help="Previous manifest path/directory or 'latest'; use empty string to disable delta",
    )
    parser.add_argument(
        "--publish-report-to",
        type=Path,
        help="Optional directory, typically inside cp-wiki Development, receiving a compact report bundle",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.vault.expanduser().resolve()
    output_base = args.output.expanduser().resolve()

    if not root.exists() or not root.is_dir():
        raise SnapshotError(f"Vault directory does not exist: {root}")

    expected_data: dict[str, Any] | None = None
    expected_version = args.snapshot_version or None
    if args.expected:
        expected_path = args.expected.expanduser().resolve()
        if not expected_path.exists():
            raise SnapshotError(f"Expected-structure file does not exist: {expected_path}")
        expected_data = load_structured_file(expected_path)
        expected_version = expected_version or str((expected_data.get("specification") or {}).get("version") or "") or None

    captured = utc_now()
    timestamp = captured.strftime("%Y%m%dT%H%M%SZ")
    label_slug = safe_slug(args.label) if args.label else "snapshot"
    version_slug = f"spec-{safe_slug(expected_version)}" if expected_version else f"tool-{TOOL_VERSION}"
    snapshot_id = f"{timestamp}_{version_slug}_{label_slug}"
    snapshot_dir = output_base / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    exclude_patterns = list(DEFAULT_EXCLUDES) + list(args.exclude)
    excluded_absolute: list[Path] = []
    try:
        output_base.relative_to(root)
        excluded_absolute.append(output_base)
    except ValueError:
        pass

    items, errors = scan_vault(
        root=root,
        exclude_patterns=exclude_patterns,
        include_hidden=args.include_hidden,
        read_frontmatter=args.read_frontmatter,
        excluded_absolute_paths=excluded_absolute,
    )

    structure_hash, state_hash = fingerprints(items)
    git_state = detect_git_state(root)
    counts = {
        "directories": sum(item.item_type == "dir" for item in items),
        "files": sum(item.item_type == "file" for item in items),
        "symlinks": sum(item.item_type == "symlink" for item in items),
        "size_bytes": sum(item.size_bytes for item in items if item.item_type == "file"),
        "items": len(items),
        "errors": len(errors),
    }

    comparison = compare_expected(items, expected_data) if expected_data else None
    previous_path: Path | None = None
    previous_manifest: dict[str, Any] | None = None
    if args.previous:
        previous_path, previous_manifest = load_previous_manifest(output_base, snapshot_dir, args.previous)
    delta = compare_previous(items, previous_manifest)

    manifest = {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "captured_at": iso_utc(captured),
        "label": args.label or None,
        "expected_specification_version": expected_version,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "python": sys.version.split()[0]},
        "host": {"platform": platform.platform(), "hostname": platform.node()},
        "vault": {"name": root.name, "root": str(root)},
        "git": asdict(git_state),
        "configuration": {
            "include_hidden": args.include_hidden,
            "read_frontmatter": args.read_frontmatter,
            "exclude_patterns": exclude_patterns,
            "max_tree_depth": args.max_tree_depth,
            "expected_structure": str(args.expected.expanduser().resolve()) if args.expected else None,
            "previous_manifest": str(previous_path) if previous_path else None,
        },
        "counts": counts,
        "fingerprints": {"structure_sha256": structure_hash, "state_sha256": state_hash},
        "top_level": aggregate_top_level(items),
        "extensions": extension_summary(items),
        "comparison_summary": None
        if comparison is None
        else {
            "status": comparison["status"],
            "required_compliance_percent": comparison["required_compliance_percent"],
            "missing_required": len(comparison["missing_required"]),
            "missing_recommended": len(comparison["missing_recommended"]),
            "type_mismatches": len(comparison["type_mismatches"]),
            "deprecated_present": len(comparison["deprecated_present"]),
        },
        "delta_summary": None
        if delta is None
        else {"added": len(delta["added"]), "removed": len(delta["removed"]), "changed": len(delta["changed"])},
        "inventory": [asdict(item) for item in items],
    }

    write_json(snapshot_dir / "manifest.json", manifest)
    write_inventory_jsonl(snapshot_dir / "inventory.jsonl", items)
    write_inventory_csv(snapshot_dir / "inventory.csv", items)
    tree = render_tree(items, args.max_tree_depth)
    (snapshot_dir / "tree.md").write_text(
        f"# Vault Tree: `{root.name}`\n\n"
        f"- Snapshot ID: `{snapshot_id}`\n"
        f"- Captured at: `{manifest['captured_at']}`\n"
        f"- Structure fingerprint: `{structure_hash}`\n"
        f"- Tree depth shown: `{args.max_tree_depth if args.max_tree_depth > 0 else 'unlimited'}`\n\n"
        f"```text\n{root.name}/\n{tree}\n```\n",
        encoding="utf-8",
    )

    if comparison is not None:
        write_json(snapshot_dir / "comparison.json", comparison)
        (snapshot_dir / "comparison.md").write_text(render_comparison_md(comparison), encoding="utf-8")
    if delta is not None:
        write_json(snapshot_dir / "delta.json", delta)
    (snapshot_dir / "delta.md").write_text(render_delta_md(delta, previous_path), encoding="utf-8")
    report_text = render_snapshot_report(manifest, comparison, delta)
    (snapshot_dir / "snapshot-report.md").write_text(report_text, encoding="utf-8")
    (snapshot_dir / "errors.log").write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")

    published_dir: Path | None = None
    if args.publish_report_to:
        publish_base = args.publish_report_to.expanduser().resolve()
        published_dir = publish_base / snapshot_id
        published_dir.mkdir(parents=True, exist_ok=False)
        shutil.copy2(snapshot_dir / "snapshot-report.md", published_dir / "snapshot-report.md")
        shutil.copy2(snapshot_dir / "tree.md", published_dir / "tree.md")
        shutil.copy2(snapshot_dir / "delta.md", published_dir / "delta.md")
        if comparison is not None:
            shutil.copy2(snapshot_dir / "comparison.md", published_dir / "comparison.md")
        reference = {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "captured_at": manifest["captured_at"],
            "label": manifest.get("label"),
            "expected_specification_version": expected_version,
            "source_snapshot_directory": str(snapshot_dir),
            "structure_sha256": structure_hash,
            "state_sha256": state_hash,
            "git": manifest["git"],
            "counts": counts,
            "comparison_summary": manifest.get("comparison_summary"),
            "delta_summary": manifest.get("delta_summary"),
        }
        write_json(published_dir / "snapshot-reference.json", reference)

    latest = output_base / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
        latest.symlink_to(snapshot_dir.name, target_is_directory=True)
    except OSError:
        # Symlink creation may be blocked by the file system. The snapshot itself is complete.
        pass

    print(f"Snapshot completed: {snapshot_dir}")
    print(f"Items: {counts['items']} | Files: {counts['files']} | Directories: {counts['directories']} | Errors: {counts['errors']}")
    print(f"Structure fingerprint: {structure_hash}")
    if comparison:
        print(
            f"IST/SOLL: {comparison['status']} | required compliance: "
            f"{comparison['required_compliance_percent']}%"
        )
    if delta:
        print(f"Delta: +{len(delta['added'])} -{len(delta['removed'])} ~{len(delta['changed'])}")
    if published_dir:
        print(f"Published compact report: {published_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print("Aborted.", file=sys.stderr)
        raise SystemExit(130)
