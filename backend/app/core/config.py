from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-weak placeholder values that must never actually be used as the
# real secret — includes every default this codebase has ever shipped
# (the old hardcoded default, and the .env.example placeholder), so
# copying .env.example to .env without editing it still fails loudly.
_KNOWN_PLACEHOLDER_SECRETS = {
    "change-me-in-production",
    "replace-with-a-long-random-value",
}


class Settings(BaseSettings):
    app_name: str = "MARKETA"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./marketa.db"
    # No default at all: unset -> pydantic-settings raises at startup.
    secret_key: str
    access_token_expire_minutes: int = 480
    allowed_origins: list[str] = ["http://localhost:5173"]

    # TODO(security): remove this dev-only auth bypass once real role-based
    # permissions (frontend login flow + token wiring) are implemented.
    # Tracked in TODO.md under "Auth wiring". Must default to False always.
    dev_disable_auth: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("secret_key")
    @classmethod
    def reject_weak_secret(cls, value: str) -> str:
        if not value or value in _KNOWN_PLACEHOLDER_SECRETS or len(value) < 16:
            raise ValueError(
                "SECRET_KEY is unset, still a known placeholder, or too short. "
                "Set a real random value (e.g. `python -c \"import secrets; "
                "print(secrets.token_urlsafe(32))\"`) in your .env file."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
