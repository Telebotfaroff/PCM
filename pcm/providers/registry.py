""Provider registry used by Telegram handlers to route supported URLs.""
from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit


class Provider(Protocol):
    name: str
    display_name: str

    def supports_url(self, url: str) -> bool:
        ...

    def classify_url(self, url: str) -> str:
        ...

    async def discover_episodes(self, url: str) -> list[dict[str, str]]:
        ...

    async def resolve(self, episode_url: str) -> dict:
        ...


def _load_providers() -> list[Provider]:
    # Register independent post adapters without changing the existing WatchHentai provider.
    from pcm.providers.analbabes import AnalBabesProvider
    from pcm.providers.bestporn4free import BestPorn4FreeProvider
    from pcm.providers.hanime_red import HanimeRedProvider
    from pcm.providers.movie4days import Movie4DaysProvider
    from pcm.providers.netfapx import NetfapxProvider
    from pcm.providers.porn4days import Porn4DaysProvider
    from pcm.providers.tube321 import Tube321Provider
    from pcm.providers.watchhentai_adapter import WatchHentaiProvider

    return [
        WatchHentaiProvider(),
        HanimeRedProvider(),
        Porn4DaysProvider(),
        Movie4DaysProvider(),
        Tube321Provider(),
        BestPorn4FreeProvider(),
        NetfapxProvider(),
        AnalBabesProvider(),
    ]


_PROVIDERS = _load_providers()


def get_provider(url: str) -> Provider | None:
    """Return the first registered provider that explicitly claims this URL."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
    except ValueError:
        return None
    for provider in _PROVIDERS:
        if provider.supports_url(url):
            return provider
    return None


def get_provider_by_name(name: str) -> Provider | None:
    """Look up a provider stored with a menu/quality choice."""
    return next((provider for provider in _PROVIDERS if provider.name == name), None)


def registered_providers() -> tuple[str, ...]:
    """Expose registered provider names for diagnostics and tests."""
    return tuple(provider.name for provider in _PROVIDERS)
