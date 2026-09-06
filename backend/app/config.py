from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["auto", "claude", "groq"]


class Settings(BaseSettings):
    """Environment-driven configuration.

    Zero-config locally (SQLite, no key needed until you tailor a resume);
    set DATABASE_URL and a provider key in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./job_tracker.db"

    # Access control for /api routes. When api_key is set, every /api request
    # must send it as X-API-Key; when unset (local dev, tests) the API is open.
    # The frontend keeps this server-side and never exposes it to the browser.
    api_key: str | None = None

    # Browser origins allowed to call the API directly (comma-separated). The
    # frontend normally proxies server-side, so this mainly matters for local
    # tools and the API docs.
    cors_origins: str = "http://localhost:3000"

    # Which LLM backend to tailor with. "auto" picks Claude when an Anthropic
    # key is present, otherwise Groq, so setting a single key is enough.
    llm_provider: Provider = "auto"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"

    groq_api_key: str | None = None
    # Only the gpt-oss models support Groq's strict structured outputs, which is
    # what guarantees the response matches the resume schema.
    groq_model: str = "openai/gpt-oss-120b"
    # gpt-oss is text-only, so reading an uploaded resume image needs a
    # separate multimodal model (best-effort JSON, not strict schemas).
    groq_vision_model: str = "qwen/qwen3.6-27b"

    def cors_origin_list(self) -> list[str]:
        """CORS origins as a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve_provider(self) -> Literal["claude", "groq"]:
        """Pick the backend to use, given the configured keys."""
        if self.llm_provider == "claude":
            return "claude"
        if self.llm_provider == "groq":
            return "groq"
        if self.anthropic_api_key:
            return "claude"
        if self.groq_api_key:
            return "groq"
        # Nothing configured: report against Claude, the default backend.
        return "claude"


settings = Settings()
