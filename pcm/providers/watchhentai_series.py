"""Discover WatchHentai episode links from either a series or episode URL."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from pcm.providers.watchhentai import classify_url, parse_html
from pcm.providers.watchhentai_resolver import ProviderResolveError, _get_text
from pcm.resolver.url_model import parse_url

_ALLOWED_HOSTS = {"watchhentai.net", "www.watchhentai.net"}
_MAX_EPISODES = 50


class _EpisodeLinkParser(HTMLParser):
    """Collect the provider's explicit episode cards, not recommendation links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str | None]] = []
        self._href: str | None = None
        self._title = ""
        self._audio: str | None = None
        self._parts: list[str] = []
        self._li_audio: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "li":
            self._li_audio.append(attr.get("data-audio") or None)
        elif tag == "a":
            classes = set(attr.get("class", "").split())
            href = attr.get("href", "").strip()
            if "tv-ep-card-link" in classes and urlsplit(href).path.startswith("/videos/"):
                self._href = href
                self._title = attr.get("title", "")
                self._audio = next((item for item in reversed(self._li_audio) if item), None)
                self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            title = self._title or " ".join("".join(self._parts).split()).strip()
            title = title.removesuffix(" Watch Hentai").strip()
            self.links.append((self._href, title or "Episode", self._audio))
            self._href = None
            self._title = ""
            self._audio = None
            self._parts = []
        elif tag == "li" and self._li_audio:
            self._li_audio.pop()


async def discover_episodes(url: str, timeout: float = 25.0) -> list[dict[str, str]]:
    """Find episodes from a series page or an episode's linked series page.

    A series URL returns its episode cards. An episode URL is included first,
    followed by cards from its explicitly linked series page. Results are
    deduplicated, limited, and restricted to WatchHentai /videos/ URLs.
    """
    parsed = parse_url(url)
    if parsed.hostname.lower() not in _ALLOWED_HOSTS:
        raise ProviderResolveError("Only WatchHentai URLs are supported.")
    input_type = classify_url(parsed.normalized)
    if input_type not in {"series", "episode"}:
        raise ProviderResolveError("Send a WatchHentai /series/... or /videos/... URL.")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    found: dict[str, dict[str, str]] = {}
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=False, trust_env=False
    ) as client:
        page_html = await _get_text(client, parsed.normalized)
        page = parse_html(page_html, parsed.normalized)
        series_url = page.canonical_url if input_type == "series" else page.series_url
        pages: list[tuple[str, str]] = []
        if input_type == "episode":
            found[parsed.normalized] = {"url": parsed.normalized, "title": page.title or "Episode"}
            pages.append((parsed.normalized, page_html))
        if series_url:
            series = parse_url(series_url)
            if (
                series.hostname.lower() not in _ALLOWED_HOSTS
                or classify_url(series.normalized) != "series"
            ):
                raise ProviderResolveError("The page linked to an unsupported series URL.")
            if input_type == "series" or series.normalized != parsed.normalized:
                try:
                    series_html = page_html if input_type == "series" else await _get_text(
                        client, series.normalized, parsed.normalized
                    )
                    pages.insert(0, (series.normalized, series_html))
                except Exception:
                    # The current episode remains usable even if its series page fails.
                    pass

        for page_url, html in pages:
            parser = _EpisodeLinkParser()
            parser.feed(html)
            for href, title, audio in parser.links:
                absolute = urljoin(page_url, href)
                try:
                    link = parse_url(absolute)
                except Exception:
                    continue
                if link.hostname.lower() not in _ALLOWED_HOSTS or classify_url(link.normalized) != "episode":
                    continue
                found.setdefault(link.normalized, {
                    "url": link.normalized,
                    "title": title,
                    **({"audio_type": audio} if audio else {}),
                })
                if len(found) >= _MAX_EPISODES:
                    break
            if len(found) >= _MAX_EPISODES:
                break

    if not found:
        raise ProviderResolveError("No episode links were found.")
    return list(found.values())[:_MAX_EPISODES]
