"""Read-only MCP server for the local cp-wiki Obsidian vault."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import MCPConfig
from .search import (
    resolve_wikilink,
    search_frontmatter,
    search_text,
)
from .vault import Vault

mcp = FastMCP("cp-wiki-read-only")


def get_vault() -> Vault:
    """Create a vault instance from current environment configuration."""

    config = MCPConfig.from_environment()
    return Vault(config.vault_root)


@mcp.tool()
def vault_info() -> dict[str, Any]:
    """Return basic information about the configured cp-wiki vault."""

    vault = get_vault()
    files = vault.list_markdown_files()

    return {
        "vault_root": str(vault.root),
        "markdown_file_count": len(files),
        "read_only": True,
    }


@mcp.tool()
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
        if (
            normalized_prefix
            and not file_info.relative_path.casefold().startswith(
                normalized_prefix
            )
        ):
            continue

        results.append(asdict(file_info))

        if len(results) >= limit:
            break

    return results


@mcp.tool()
def read_vault_note(
    relative_path: str,
) -> dict[str, Any]:
    """Read and parse one Markdown note by vault-relative path."""

    vault = get_vault()
    document = vault.read_document(relative_path)

    return asdict(document)


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def resolve_vault_wikilink(
    target: str,
) -> dict[str, Any]:
    """Resolve an Obsidian wikilink target to matching Markdown files."""

    vault = get_vault()
    result = resolve_wikilink(vault, target)

    return asdict(result)


def main() -> None:
    """Run the MCP server over stdio."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()