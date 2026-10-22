"""Adapter exposing WatchHentai through PCM's provider interface."""
from __future__ import annotations

from urllib.parse import urlsplit

from pcm.providers.watchhentai import classify_url
from pcm.providers.watchhentai_resolver import ProviderResolveError, WatchHentaiResolver
from pcm.providers.watchhentai_series import discover_episodes


class WatchHentaiProvider:
    """Provider contract: URL matching, classification, discovery, and resolution."""

    name = "watchhentai"
    display_name = "WatchHentai"
    _hosts = {"watchhentai.net", "www.watchhentai.net"}

    def __init__(self) -> None:
        self._resolver = WatchHentaiResolver()

    def supports_url(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            return parsed.hostname is not None and parsed.hostname.lower() in self._hosts
        except ValueError:
            return False

    def classify_url(self, url: str) -> str:
        return classify_url(url)

    async def discover_episodes(self, url: str) -> list[dict[str, str]]:
        return await discover_episodes(url)

    async def resolve(self, episode_url: str) -> dict:
        return await self._resolver.resolve(episode_url)

    def validate_page_type(self, page_type: str) -> bool:
        return page_type in {"series", "episode"}

