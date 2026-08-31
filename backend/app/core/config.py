from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_commerce_os"

    session_cookie_name: str = "session_token"
    session_idle_ttl_days: int = 30
    session_absolute_ttl_days: int = 90
    cookie_secure: bool = True
    csrf_cookie_name: str = "csrf_token"

    local_storage_path: str = "var/storage"
    max_upload_size_bytes: int = 10 * 1024 * 1024

    ai_default_provider: str = "anthropic"
    ai_image_provider: str = "openai"
    ai_request_timeout_seconds: int = 60
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None

    # Bounded exponential backoff for transient AI provider failures (see
    # app.ai.tools._common). ai_max_retries is additional attempts beyond
    # the first -- default 3 means up to 4 total attempts.
    ai_max_retries: int = 3
    ai_retry_initial_delay_seconds: float = 0.5
    ai_retry_max_delay_seconds: float = 8.0

    # In-memory sliding-window throttle for auth endpoints (login, signup,
    # password-reset-request) -- see app.core.rate_limit. Per scope, up to
    # this many attempts within the trailing window, keyed independently by
    # client IP and by account identifier (email). Single-instance-only:
    # state lives in process memory and resets on restart / doesn't
    # coordinate across multiple workers -- an accepted limitation for now.
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: float = 60.0

    # Optional per-organization monthly AI spend ceiling in USD, derived from
    # the sum of AIRun.cost_usd for the current calendar month (UTC) -- no
    # dedicated column/table. None (default) means unlimited, so existing
    # behavior/tests are unaffected unless an operator opts in by setting
    # AI_ORG_MONTHLY_SPEND_LIMIT_USD.
    ai_org_monthly_spend_limit_usd: Decimal | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
