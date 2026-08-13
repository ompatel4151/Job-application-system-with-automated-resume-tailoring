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

    # Which LLM backend to tailor with. "auto" picks Claude when an Anthropic
    # key is present, otherwise Groq — so setting a single key is enough.
    llm_provider: Provider = "auto"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"

    groq_api_key: str | None = None
    # Only the gpt-oss models support Groq's strict structured outputs, which is
    # what guarantees the response matches the resume schema.
    groq_model: str = "openai/gpt-oss-120b"

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
