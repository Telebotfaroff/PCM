"""Discover episode links related to a WatchHentai episode or series page."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import re

from pcm.providers.watchhentai import parse_html
from pcm.providers.watchhentai_resolver import ProviderResolveError, _get_text
from pcm.resolver.url_model import parse_url

_ALLOWED_HOSTS = {"watchhentai.net", "www.watchhentai.net"}
_MAX_EPISODES = 50


class _EpisodeLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {key.lower(): value or "" for key, value in attrs}
        href = attr.get("href", "")
        path = urlsplit(href).path
        if path.startswith("/videos/"):
            self._href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._parts).split()).strip()))
            self._href = None
            self._parts = []


async def discover_episodes(episode_url: str, timeout: float = 25.0) -> list[dict[str, str]]:
    """Find episode links on the episode page and its linked series page.

    The current episode is always included. Results are deduplicated and capped to
    avoid crawling unrelated or unexpectedly huge pages.
    """
    parsed = parse_url(episode_url)
    if parsed.hostname.lower() not in _ALLOWED_HOSTS:
        raise ProviderResolveError("Only WatchHentai episode URLs are supported.")
    if not urlsplit(parsed.normalized).path.startswith("/videos/"):
        raise ProviderResolveError("Expected a WatchHentai episode URL.")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    found: dict[str, str] = {}
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False, trust_env=False) as client:
        episode_html = await _get_text(client, parsed.normalized)
        current_page = parse_html(episode_html, parsed.normalized)
        found[parsed.normalized] = current_page.title or "Episode"

        pages = [(parsed.normalized, episode_html)]
        visited = {parsed.normalized}
        if current_page.series_url:
            series = parse_url(current_page.series_url)
            if series.hostname.lower() not in _ALLOWED_HOSTS or not urlsplit(series.normalized).path.startswith("/series/"):
                raise ProviderResolveError("The page linked to an unsupported series URL.")
            if series.normalized != parsed.normalized:
                try:
                    pages.append((series.normalized, await _get_text(client, series.normalized, parsed.normalized)))
                except Exception:
                    # Previous/next episode links may still provide the episode list.
                    pass

        # Follow explicit previous-episode links too; some provider pages do not expose
        # a separate series page or a complete episode listing.
        cursor = 0
        while cursor < len(pages) and len(found) < _MAX_EPISODES:
            page_url, html = pages[cursor]
            cursor += 1
            page_parser = _EpisodeLinkParser()
            page_parser.feed(html)
            for href, label in page_parser.links:
                absolute = urljoin(page_url, href)
                try:
                    link = parse_url(absolute)
                except Exception:
                    continue
                if link.hostname.lower() not in _ALLOWED_HOSTS:
                    continue
                if not urlsplit(link.normalized).path.startswith("/videos/"):
                    continue
                found.setdefault(
                    link.normalized,
                    label or urlsplit(link.normalized).path.rstrip("/").split("/")[-1],
                )
                if len(found) >= _MAX_EPISODES:
                    break

            # Only episode pages have meaningful previous-episode navigation.
            if urlsplit(page_url).path.startswith("/videos/"):
                page = parse_html(html, page_url)
                previous = page.previous_episode_url
                if previous:
                    try:
                        previous_url = parse_url(previous).normalized
                        if (
                            urlsplit(previous_url).hostname in _ALLOWED_HOSTS
                            and urlsplit(previous_url).path.startswith("/videos/")
                            and previous_url not in visited
                            and len(visited) < _MAX_EPISODES
                        ):
                            visited.add(previous_url)
                            previous_html = await _get_text(client, previous_url, page_url)
                            previous_page = parse_html(previous_html, previous_url)
                            found.setdefault(previous_url, previous_page.title or "Episode")
                            pages.append((previous_url, previous_html))
                    except Exception:
                        # A broken previous link should not discard already discovered episodes.
                        pass

    # Keep the submitted episode first, then retain discovery order.
    ordered = [{"url": parsed.normalized, "title": found.pop(parsed.normalized)}]
    ordered.extend({"url": url, "title": title} for url, title in found.items())
    return ordered[:_MAX_EPISODES]
