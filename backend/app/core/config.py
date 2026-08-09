from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

    # ── The shop's own clock ─────────────────────────────────────────────
    # Timestamps are stored in UTC, but "today's sales" and every daily
    # report line mean a day in the shop's own time, not in Greenwich's.
    # One deployment serves one shop, so this belongs to the deployment.
    store_timezone: str = "Asia/Tehran"

    # When one trading day ends and the next begins, as an hour on the
    # store's clock. 0 is local midnight — the ordinary calendar day, and
    # the right default for a shop that has shut by then. A shop trading
    # until 2am sets 3, and the sales it rings up after midnight stay on
    # the day the shift began instead of opening a new one. Must be
    # 0..23; anything at or past 12 would put the boundary in the middle
    # of trading, which no shop wants.
    store_day_boundary_hour: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("store_timezone")
    @classmethod
    def reject_unknown_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(
                f"STORE_TIMEZONE {value!r} is not a known IANA time zone name "
                '(e.g. "Asia/Tehran", "Europe/Istanbul").'
            ) from error
        return value

    @field_validator("store_day_boundary_hour")
    @classmethod
    def reject_boundary_mid_trading(cls, value: int) -> int:
        if not 0 <= value <= 11:
            raise ValueError(
                "STORE_DAY_BOUNDARY_HOUR must be between 0 and 11 — it marks the "
                "small hours where one trading day hands over to the next, so a "
                "value from midday onwards would split a day of trading in two."
            )
        return value

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
