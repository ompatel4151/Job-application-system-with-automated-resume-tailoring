from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    Zero-config locally (SQLite, no key needed until you tailor a resume);
    set DATABASE_URL and ANTHROPIC_API_KEY in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./job_tracker.db"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"


settings = Settings()
