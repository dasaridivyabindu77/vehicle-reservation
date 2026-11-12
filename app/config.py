"""Application configuration.

Settings load from environment variables / a local ``.env`` file. The single
most important switch is ``DIAL_API_KEY``: when it is empty the whole system
runs in a deterministic *offline* mode (hashing embeddings + extractive
answers) so development, tests and CI need no network access.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- EPAM DIAL (Azure-OpenAI compatible) ---
    dial_api_key: str = ""
    dial_endpoint: str = "https://ai-proxy.lab.epam.com"
    dial_api_version: str = "2024-02-01"
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small-1"

    # --- Weaviate ---
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""

    # --- Dynamic data ---
    sqlite_path: str = "citypark.db"

    # --- Retrieval & grounding ---
    top_k: int = 4
    relevance_min_overlap: float = 0.12
    relevance_min_score: float = 0.30
    embedding_dim: int = 256

    # --- Stage 2: human-in-the-loop admin approval ---
    # Who approves reservations, and how the admin agent reaches them. The
    # dashboard (GET /admin) and admin CLI always work offline; email is an
    # optional extra notification channel that only activates when configured.
    admin_name: str = "CityPark Administrator"
    admin_email: str = ""            # recipient for email escalations (optional)
    admin_token: str = ""            # if set, /admin endpoints require this token

    # SMTP (optional) — only used when smtp_host and admin_email are both set.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""              # falls back to smtp_user if blank
    smtp_use_tls: bool = True

    # --- Stage 3: MCP server for confirmed reservation persistence ---
    mcp_server_url: str = "http://127.0.0.1:8001"
    mcp_server_token: str = ""       # authentication token for MCP server
    mcp_enabled: bool = True          # enable/disable Stage 3 file writing

    @property
    def llm_configured(self) -> bool:
        """True when a real DIAL key is present (i.e. not offline mode)."""
        return bool(self.dial_api_key.strip())

    @property
    def email_configured(self) -> bool:
        """True when the optional SMTP email escalation channel can be used."""
        return bool(self.smtp_host.strip() and self.admin_email.strip())

    @property
    def mcp_configured(self) -> bool:
        """True when Stage 3 MCP server is configured and enabled."""
        return self.mcp_enabled and bool(self.mcp_server_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
