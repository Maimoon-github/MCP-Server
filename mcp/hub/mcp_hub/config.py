"""
config.py – Application-wide settings.

All values are sourced from environment variables or a `.env` file in the
working directory.  Copy `.env.example` → `.env` and edit to taste.

Generate a token:
    python -c "import secrets; print(secrets.token_hex(32))"
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server identity ─────────────────────────────────────────────────────
    server_name: str = "local-mcp-hub"
    server_version: str = "1.0.0"

    # ── Authentication ───────────────────────────────────────────────────────
    # Comma-separated bearer tokens.  Empty string = auth disabled (dev mode).
    auth_tokens: str = ""
    auth_enabled: bool = False

    # ── Filesystem sandbox ───────────────────────────────────────────────────
    # Comma-separated absolute paths the hub may read/write.
    # If empty, defaults to the current working directory.
    allowed_paths: str = ""

    # ── SQLite connector ─────────────────────────────────────────────────────
    sqlite_db_path: str = ""          # absolute path; empty = disabled

    # ── PostgreSQL connector ─────────────────────────────────────────────────
    postgres_url: str = ""            # e.g. postgresql://user:pass@localhost/db

    # ── Git connector ────────────────────────────────────────────────────────
    git_root: str = ""                # default repo root; empty = disabled

    # ── Shell connector ──────────────────────────────────────────────────────
    shell_enabled: bool = False
    shell_allowed_commands: str = (
        "git,python,pip,node,npm,ls,dir,cat,echo,pwd,whoami,curl"
    )
    shell_timeout_seconds: int = 30

    # ── Sandbox limits ───────────────────────────────────────────────────────
    max_file_size_bytes: int = 10 * 1024 * 1024   # 10 MB
    max_output_rows: int = 500
    tool_timeout_seconds: int = 60

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ─────────────────────────────────────────────────────────────────────────

    def get_allowed_paths(self) -> list[Path]:
        """Return the list of sandbox-allowed root paths."""
        if not self.allowed_paths.strip():
            return [Path.cwd()]
        return [
            Path(p.strip()).expanduser().resolve()
            for p in self.allowed_paths.split(",")
            if p.strip()
        ]

    def get_auth_tokens(self) -> set[str]:
        """Return the set of valid bearer tokens (excluding permission level suffix)."""
        tokens = set()
        for t in self.auth_tokens.split(","):
            t = t.strip()
            if not t:
                continue
            if ":" in t:
                t = t.split(":", 1)[0].strip()
            tokens.add(t)
        return tokens

    def get_allowed_commands(self) -> list[str]:
        """Return the allowlisted shell command prefixes."""
        return [c.strip() for c in self.shell_allowed_commands.split(",") if c.strip()]


# Module-level singleton – import this everywhere.
settings = Settings()
