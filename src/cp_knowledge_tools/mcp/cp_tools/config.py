"""Configuration for the read-only cpKnowledgeTools MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import RepositoryConfigurationError

DEFAULT_REPOSITORY_ROOT = Path("/Users/cp/Developer/cpKnowledgeTools")
DEFAULT_MAX_FILE_BYTES = 1_000_000

REPOSITORY_ROOT_ENV = "CP_TOOLS_REPOSITORY_ROOT"
MAX_FILE_BYTES_ENV = "CP_TOOLS_MAX_FILE_BYTES"


@dataclass(frozen=True, slots=True)
class MCPConfig:
    """Immutable MCP server configuration."""

    repository_root: Path
    max_file_bytes: int

    @classmethod
    def from_environment(cls) -> MCPConfig:
        """Load configuration from environment variables."""

        configured_root = os.environ.get(REPOSITORY_ROOT_ENV)

        repository_root = (
            Path(configured_root).expanduser()
            if configured_root
            else DEFAULT_REPOSITORY_ROOT
        ).resolve()

        if not repository_root.exists():
            raise RepositoryConfigurationError(
                f"Repository root does not exist: {repository_root}"
            )

        if not repository_root.is_dir():
            raise RepositoryConfigurationError(
                f"Repository root is not a directory: {repository_root}"
            )

        configured_max_size = os.environ.get(MAX_FILE_BYTES_ENV)

        if configured_max_size:
            try:
                max_file_bytes = int(configured_max_size)
            except ValueError as exc:
                raise RepositoryConfigurationError(
                    f"{MAX_FILE_BYTES_ENV} must be an integer."
                ) from exc
        else:
            max_file_bytes = DEFAULT_MAX_FILE_BYTES

        if not 1 <= max_file_bytes <= 10_000_000:
            raise RepositoryConfigurationError(
                f"{MAX_FILE_BYTES_ENV} must be between 1 and 10000000."
            )

        return cls(
            repository_root=repository_root,
            max_file_bytes=max_file_bytes,
        )
