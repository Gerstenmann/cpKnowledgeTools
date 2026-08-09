"""Read-only MCP server for the local cp-wiki Obsidian vault."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import MCPConfig
from .governance import (
    read_active_artifact as read_active_artifact_from_vault,
)
from .governance import (
    resolve_active_artifact as resolve_active_artifact_from_vault,
)
from .governance import (
    resolve_governance_bundle as resolve_governance_bundle_from_vault,
)
from .search import (
    resolve_wikilink,
    search_frontmatter,
    search_text,
)
from .vault import Vault

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP(
    name="cp-wiki-read-only",
    instructions=(
        "Read-only access to the live local cp-wiki. Canonical governance and "
        "architecture live in cp-wiki, not in AGENTS.md, repository files, "
        "session context or agent memory. For normative or material development "
        "work, resolve stable IDs with resolve_active_artifact or "
        "resolve_governance_bundle, require integrity_ok=true, then read the "
        "active content with read_active_artifact. The server can list, read and "
        "search Markdown notes and structured JSON, but cannot create, modify, "
        "move or delete Vault files."
    ),
    host=DEFAULT_HTTP_HOST,
    port=DEFAULT_HTTP_PORT,
    streamable_http_path=DEFAULT_HTTP_PATH,
    stateless_http=True,
    json_response=True,
)


def read_only_annotations(title: str) -> ToolAnnotations:
    """Return explicit safety annotations for a local read-only tool."""

    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )


def get_vault() -> Vault:
    """Create a vault instance from current environment configuration."""

    config = MCPConfig.from_environment()
    return Vault(
        config.vault_root,
        max_json_bytes=config.max_json_bytes,
    )


@mcp.tool(annotations=read_only_annotations("Vault information"))
def vault_info() -> dict[str, Any]:
    """Return basic information about the configured cp-wiki vault."""

    vault = get_vault()
    markdown_files = vault.list_markdown_files()
    json_files = vault.list_json_files()

    return {
        "vault_root": str(vault.root),
        "markdown_file_count": len(markdown_files),
        "json_file_count": len(json_files),
        "maximum_readable_json_bytes": vault.max_json_bytes,
        "read_only": True,
    }


@mcp.tool(annotations=read_only_annotations("List vault files"))
def list_vault_files(
    path_prefix: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    List Markdown files inside the vault.

    `path_prefix` filters results by vault-relative path.
    """

    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000.")

    normalized_prefix = path_prefix.strip().casefold()
    vault = get_vault()

    results: list[dict[str, Any]] = []

    for file_info in vault.list_markdown_files():
        if normalized_prefix and not file_info.relative_path.casefold().startswith(
            normalized_prefix
        ):
            continue

        results.append(asdict(file_info))

        if len(results) >= limit:
            break

    return results


@mcp.tool(annotations=read_only_annotations("List vault JSON files"))
def list_vault_json_files(
    path_prefix: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List JSON files inside the vault."""

    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000.")

    normalized_prefix = path_prefix.strip().casefold()
    vault = get_vault()
    results: list[dict[str, Any]] = []

    for file_info in vault.list_json_files():
        if normalized_prefix and not file_info.relative_path.casefold().startswith(
            normalized_prefix
        ):
            continue

        results.append(asdict(file_info))

        if len(results) >= limit:
            break

    return results


@mcp.tool(annotations=read_only_annotations("Read vault note"))
def read_vault_note(
    relative_path: str,
) -> dict[str, Any]:
    """Read and parse one Markdown note by vault-relative path."""

    vault = get_vault()
    document = vault.read_document(relative_path)

    return asdict(document)


@mcp.tool(annotations=read_only_annotations("Read vault JSON"))
def read_vault_json(
    relative_path: str,
) -> dict[str, Any]:
    """Read and parse one JSON file as structured data."""

    vault = get_vault()
    path = vault.resolve_path(relative_path)
    data = vault.read_json(relative_path)

    return {
        "relative_path": path.relative_to(vault.root).as_posix(),
        "size_bytes": path.stat().st_size,
        "data": data,
    }


@mcp.tool(annotations=read_only_annotations("Search vault text"))
def search_vault_text(
    query: str,
    case_sensitive: bool = False,
    context_lines: int = 1,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Search text across Markdown files in the vault."""

    vault = get_vault()

    return [
        asdict(result)
        for result in search_text(
            vault,
            query,
            case_sensitive=case_sensitive,
            context_lines=context_lines,
            max_results=max_results,
        )
    ]


@mcp.tool(annotations=read_only_annotations("Search vault frontmatter"))
def search_vault_frontmatter(
    field: str,
    expected: str,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Search one top-level YAML frontmatter field."""

    vault = get_vault()

    return [
        asdict(result)
        for result in search_frontmatter(
            vault,
            field=field,
            expected=expected,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )
    ]


@mcp.tool(annotations=read_only_annotations("Resolve active Managed Artifact"))
def resolve_active_artifact(
    stable_id: str,
) -> dict[str, Any]:
    """Resolve a stable/current or former ID to exactly one active artifact."""

    vault = get_vault()
    resolution = resolve_active_artifact_from_vault(vault, stable_id)

    return asdict(resolution)


@mcp.tool(annotations=read_only_annotations("Read active Managed Artifact"))
def read_active_artifact(
    stable_id: str,
) -> dict[str, Any]:
    """Resolve and read an active artifact, failing closed on integrity issues."""

    vault = get_vault()
    resolution, document = read_active_artifact_from_vault(vault, stable_id)

    return {
        "resolution": asdict(resolution),
        "document": asdict(document),
    }


@mcp.tool(annotations=read_only_annotations("Resolve governance bundle"))
def resolve_governance_bundle(
    stable_ids: list[str],
) -> dict[str, Any]:
    """Resolve a bounded ordered bundle of stable IDs against the live Vault."""

    vault = get_vault()
    resolutions = resolve_governance_bundle_from_vault(vault, stable_ids)

    return {
        "requested_ids": stable_ids,
        "artifacts": [asdict(item) for item in resolutions],
    }


@mcp.tool(annotations=read_only_annotations("Resolve vault wikilink"))
def resolve_vault_wikilink(
    target: str,
) -> dict[str, Any]:
    """Resolve an Obsidian wikilink target to matching Markdown files."""

    vault = get_vault()
    result = resolve_wikilink(vault, target)

    return asdict(result)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for MCP transport selection."""

    parser = argparse.ArgumentParser(
        prog="cp-wiki-mcp",
        description="Run the read-only MCP server for the local cp-wiki vault.",
    )

    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help=(
            "MCP transport. Use 'stdio' for local clients and "
            "'streamable-http' for the Secure MCP Tunnel."
        ),
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_HTTP_HOST,
        help=("HTTP bind address. Keep 127.0.0.1 when using the Secure MCP Tunnel."),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Local HTTP port for Streamable HTTP.",
    )

    parser.add_argument(
        "--path",
        default=DEFAULT_HTTP_PATH,
        help="MCP Streamable HTTP endpoint path.",
    )

    return parser


def main() -> None:
    """Run the MCP server using the selected transport."""

    parser = build_argument_parser()
    args = parser.parse_args()

    if args.transport == "streamable-http":
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535.")

        if not args.path.startswith("/"):
            parser.error("--path must start with '/'.")

        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = args.path

        print(
            (
                "Starting cp-wiki MCP server at "
                f"http://{args.host}:{args.port}{args.path}"
            ),
            flush=True,
        )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
