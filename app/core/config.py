from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLICYSCAN_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./policyscan.db"
    secret_key: str = "change-me"
    model_path: str = "models/baseline-v0"

    # Outbound fetch limits (used by the SSRF-safe fetcher)
    fetch_timeout_seconds: float = 10.0
    fetch_max_bytes: int = 2_000_000
    fetch_max_redirects: int = 5

    # Tracker audit: empty URL runs Playwright in-process (dev); set it to the worker in Docker
    enable_audit: bool = True
    audit_worker_url: str = ""

    # Rate limits (requests per minute)
    rate_limit_ip_per_minute: int = 30
    rate_limit_user_per_minute: int = 60
    scan_limit_ip_per_minute: int = 5

    # Unsaved reports are deleted after this many days (data minimization)
    unsaved_report_retention_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
