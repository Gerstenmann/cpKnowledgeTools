"""Read-only MCP server for the local cpKnowledgeTools repository."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import MCPConfig
from .git import GitReader
from .operations import resolve_standard_operation as resolve_operation_capability
from .repository import Repository
from .search import search_text

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8766
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP(
    name="cp-tools-macmini-read-only",
    instructions=(
        "Read-only access to the local cpKnowledgeTools Python repository. "
        "The server can inspect the repository tree, list, find, read and "
        "search safe text files, and inspect bounded Git status, diff and "
        "history information. It cannot create, modify, move, execute or "
        "delete files. Version-control internals, virtual environments, "
        "caches, credentials and common secret-file formats are excluded."
    ),
    host=DEFAULT_HTTP_HOST,
    port=DEFAULT_HTTP_PORT,
    streamable_http_path=DEFAULT_HTTP_PATH,
    stateless_http=True,
    json_response=True,
)


def read_only_annotations(title: str) -> ToolAnnotations:
    """Return explicit safety annotations for a read-only tool."""

    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )


def get_repository() -> Repository:
    """Create a repository instance from current configuration."""

    config = MCPConfig.from_environment()

    return Repository(
        root=config.repository_root,
        max_file_bytes=config.max_file_bytes,
    )


def get_git_reader() -> GitReader:
    """Create a restricted Git reader for the repository."""

    return GitReader(get_repository())


@mcp.tool(annotations=read_only_annotations("Repository information"))
def repository_info() -> dict[str, Any]:
    """Return basic information about the configured repository."""

    repository = get_repository()
    files = repository.list_files()

    return {
        "repository_root": str(repository.root),
        "file_count": len(files),
        "maximum_readable_file_bytes": repository.max_file_bytes,
        "read_only": True,
    }


@mcp.tool(annotations=read_only_annotations("Repository tree"))
def repository_tree(
    relative_path: str = "",
    max_depth: int = 4,
    include_files: bool = True,
    max_entries: int = 1000,
) -> dict[str, Any]:
    """Return a bounded directory tree for a repository path."""

    repository = get_repository()
    tree = repository.build_tree(
        relative_path,
        max_depth=max_depth,
        include_files=include_files,
        max_entries=max_entries,
    )

    return asdict(tree)


@mcp.tool(annotations=read_only_annotations("List repository files"))
def list_repository_files(
    path_prefix: str = "",
    suffix: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List safe files inside the configured repository."""

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")

    normalized_prefix = path_prefix.strip().replace("\\", "/").casefold()
    normalized_suffix = suffix.strip().casefold()

    if normalized_suffix and not normalized_suffix.startswith("."):
        normalized_suffix = "." + normalized_suffix

    repository = get_repository()
    results: list[dict[str, Any]] = []

    for file_info in repository.list_files():
        if normalized_prefix and not file_info.relative_path.casefold().startswith(
            normalized_prefix
        ):
            continue

        if normalized_suffix and file_info.suffix != normalized_suffix:
            continue

        results.append(asdict(file_info))

        if len(results) >= limit:
            break

    return results


@mcp.tool(annotations=read_only_annotations("Find repository files"))
def find_repository_files(
    query: str,
    path_prefix: str = "",
    suffix: str = "",
    case_sensitive: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Find files by file name or repository-relative path."""

    repository = get_repository()

    return [
        asdict(file_info)
        for file_info in repository.find_files(
            query,
            path_prefix=path_prefix,
            suffix=suffix,
            case_sensitive=case_sensitive,
            limit=limit,
        )
    ]


@mcp.tool(annotations=read_only_annotations("Read repository file"))
def read_repository_file(
    relative_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """Read one safe UTF-8 text file or selected line range."""

    repository = get_repository()
    document = repository.read_text_file(
        relative_path,
        start_line=start_line,
        end_line=end_line,
    )

    return asdict(document)


@mcp.tool(annotations=read_only_annotations("Search repository text"))
def search_repository_text(
    query: str,
    path_prefix: str = "",
    case_sensitive: bool = False,
    context_lines: int = 1,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Search text across safe UTF-8 repository files."""

    repository = get_repository()

    return [
        asdict(result)
        for result in search_text(
            repository,
            query,
            path_prefix=path_prefix,
            case_sensitive=case_sensitive,
            context_lines=context_lines,
            max_results=max_results,
        )
    ]


@mcp.tool(annotations=read_only_annotations("Git status"))
def git_status() -> dict[str, Any]:
    """Return current branch, HEAD and structured working-tree status."""

    return asdict(get_git_reader().status())


@mcp.tool(annotations=read_only_annotations("Git diff"))
def git_diff(
    relative_path: str = "",
    staged: bool = False,
    context_lines: int = 3,
) -> dict[str, Any]:
    """Return a bounded staged or unstaged Git diff."""

    return asdict(
        get_git_reader().diff(
            relative_path=relative_path,
            staged=staged,
            context_lines=context_lines,
        )
    )


@mcp.tool(annotations=read_only_annotations("Git log"))
def git_log(
    relative_path: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent commit metadata, optionally filtered by path."""

    return [
        asdict(commit)
        for commit in get_git_reader().log(
            relative_path=relative_path,
            limit=limit,
        )
    ]


@mcp.tool(annotations=read_only_annotations("Resolve standard operation"))
def resolve_standard_operation(
    operation_id: str,
    operation_version: str = "0.1",
) -> dict[str, Any]:
    """Resolve capability, version, surfaces and supported scope without execution."""

    return resolve_operation_capability(operation_id, operation_version)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(
        prog="cp-tools-mcp",
        description=(
            "Run the read-only MCP server for the local cpKnowledgeTools repository."
        ),
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
                "Starting cp-tools MCP server at "
                f"http://{args.host}:{args.port}{args.path}"
            ),
            flush=True,
        )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
