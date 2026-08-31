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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
