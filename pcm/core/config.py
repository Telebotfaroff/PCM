"""Small environment-backed configuration for PCM."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(ValueError):
    """Raised when a configuration value is missing or invalid."""


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < 1:
        raise ConfigError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_owner_id: int
    insforge_database_url: str
    max_concurrent_downloads: int = 1
    max_concurrent_uploads: int = 1
    max_urls_per_batch: int = 10
    max_file_size_mb: int = 4096
    min_free_disk_mb: int = 2048
    max_redirect_hops: int = 8
    request_timeout_seconds: int = 30
    temp_dir: Path = Path("/tmp/pcm")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, *, require_secrets: bool = True) -> Settings:
        """Load settings; require secrets by default for real application startup."""
        required = {
            "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", "").strip(),
            "INSFORGE_DATABASE_URL": os.getenv("INSFORGE_DATABASE_URL", "").strip(),
        }
        if require_secrets:
            missing = [key for key, value in required.items() if not value]
            if not os.getenv("TELEGRAM_API_ID", "").strip():
                missing.append("TELEGRAM_API_ID")
            if not os.getenv("TELEGRAM_OWNER_ID", "").strip():
                missing.append("TELEGRAM_OWNER_ID")
            if missing:
                raise ConfigError("Missing required environment settings: " + ", ".join(missing))

        api_id = _positive_int("TELEGRAM_API_ID", 1)
        owner_id = _positive_int("TELEGRAM_OWNER_ID", 1)
        settings = cls(
            telegram_bot_token=required["TELEGRAM_BOT_TOKEN"],
            telegram_api_id=api_id,
            telegram_api_hash=required["TELEGRAM_API_HASH"],
            telegram_owner_id=owner_id,
            insforge_database_url=required["INSFORGE_DATABASE_URL"],
            max_concurrent_downloads=_positive_int("MAX_CONCURRENT_DOWNLOADS", 1),
            max_concurrent_uploads=_positive_int("MAX_CONCURRENT_UPLOADS", 1),
            max_urls_per_batch=_positive_int("MAX_URLS_PER_BATCH", 10),
            max_file_size_mb=_positive_int("MAX_FILE_SIZE_MB", 4096),
            min_free_disk_mb=_positive_int("MIN_FREE_DISK_MB", 2048),
            max_redirect_hops=_positive_int("MAX_REDIRECT_HOPS", 8),
            request_timeout_seconds=_positive_int("REQUEST_TIMEOUT_SECONDS", 30),
            temp_dir=Path(os.getenv("TEMP_DIR", "/tmp/pcm")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return settings
