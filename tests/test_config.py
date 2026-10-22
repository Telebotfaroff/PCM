import pytest

from pcm.core.config import ConfigError, Settings


def test_missing_secrets_fail_fast(monkeypatch):
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_OWNER_ID",
        "INSFORGE_DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigError, match="Missing required environment"):
        Settings.from_env()


def test_invalid_concurrency_is_rejected(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_DOWNLOADS", "0")
    with pytest.raises(ConfigError, match="MAX_CONCURRENT_DOWNLOADS"):
        Settings.from_env(require_secrets=False)
