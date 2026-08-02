from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration (NFR-PORT-002: no hardcoded env values)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_sync: str
    # Phase 17C-RLS: Alembic connects as erp_migrate (owns schema objects),
    # never as the runtime role the rest of Settings' database_url_sync now
    # points at. Optional with a fallback to database_url_sync ONLY so a
    # developer's plain `.env` (no separate migrate role configured yet)
    # keeps working — production's `.env.migrate` must always set this
    # explicitly; see migrations/env.py and docs/17c-rls-runtime-role-hardening.md.
    database_url_migrate_sync: str | None = None
    redis_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    app_env: str = "development"
    log_level: str = "INFO"

    # Phase 16 audit finding: this was hardcoded to http://localhost:3000 in
    # api/main.py, which is a real production blocker (nothing off localhost
    # could ever call the API) — comma-separated so ops can list multiple
    # origins (e.g. a staging + production frontend) without a code change.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
