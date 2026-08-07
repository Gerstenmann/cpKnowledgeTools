"""Configuration for the local read-only cp-wiki MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import VaultConfigurationError

DEFAULT_VAULT_ROOT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_MAX_JSON_BYTES = 1_000_000
VAULT_ROOT_ENV = "CP_WIKI_VAULT_ROOT"
MAX_JSON_BYTES_ENV = "CP_WIKI_MAX_JSON_BYTES"


@dataclass(frozen=True, slots=True)
class MCPConfig:
    """Immutable MCP server configuration."""

    vault_root: Path
    max_json_bytes: int

    @classmethod
    def from_environment(cls) -> MCPConfig:
        """Load configuration from the environment."""

        configured_root = os.environ.get(VAULT_ROOT_ENV)
        vault_root = (
            Path(configured_root).expanduser()
            if configured_root
            else DEFAULT_VAULT_ROOT
        )

        vault_root = vault_root.resolve()

        if not vault_root.exists():
            raise VaultConfigurationError(f"Vault root does not exist: {vault_root}")

        if not vault_root.is_dir():
            raise VaultConfigurationError(
                f"Vault root is not a directory: {vault_root}"
            )

        configured_max_json_bytes = os.environ.get(MAX_JSON_BYTES_ENV)

        if configured_max_json_bytes:
            try:
                max_json_bytes = int(configured_max_json_bytes)
            except ValueError as exc:
                raise VaultConfigurationError(
                    f"{MAX_JSON_BYTES_ENV} must be an integer."
                ) from exc
        else:
            max_json_bytes = DEFAULT_MAX_JSON_BYTES

        if not 1 <= max_json_bytes <= 10_000_000:
            raise VaultConfigurationError(
                f"{MAX_JSON_BYTES_ENV} must be between 1 and 10000000."
            )

        return cls(
            vault_root=vault_root,
            max_json_bytes=max_json_bytes,
        )
