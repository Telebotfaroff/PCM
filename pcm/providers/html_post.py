"""Shared HTML metadata extraction for independent single-post providers.

This module intentionally does not modify the existing WatchHentai implementation.
It parses rendered HTML metadata and direct media source tags; it does not treat an
embedded-player URL as a downloadable media URL.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from pcm.resolver.url_model import URLValidationError, parse_url


class HtmlPostResolveError(RuntimeError):
    """Raised when a post page cannot be safely fetched or resolved."""


@dataclass(slots=True)
class HtmlPostPage:
    source_url: str
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    media_id: str | None = None
    embed_urls: list[str] = field(default_factory=list)
    preview_images: list[str] = field(default_factory=list)
    media_urls: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class _PostHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_text: list[str] = []
        self.h1_text: list[str] = []
        self.in_title = False
        self.in_h1 = False
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.images: list[str] = []
        self.embeds: list[str] = []
        self.media: list[dict[str, str]] = []
        self.duration: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (
                attr.get("property") or attr.get("name") or attr.get("itemprop") or ""
            ).strip().lower()
            value = attr.get("content", "").strip()
            if key and value:
                self.meta.setdefault(key, value)
                if key in {"og:image", "twitter:image", "thumbnailurl"}:
                    self._add(self.images, value)
                if key in {"video:duration", "duration"}:
                    try:
                        self.duration = int(float(value))
                    except (TypeError, ValueError):
                        pass
        elif tag == "link" and "canonical" in attr.get("rel", "").lower().split():
            self.canonical = attr.get("href") or self.canonical
        elif tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.in_h1 = True
        elif tag == "img":
            image = attr.get("data-src") or attr.get("data-lazy-src") or attr.get("src") or ""
            if image and not image.startswith("data:"):
                self._add(self.images, image)
        elif tag == "iframe":
            src = attr.get("src", "").strip()
            if src and not src.lower().startswith(("javascript:", "data:")):
                width = attr.get("width", "")
                height = attr.get("height", "")
                if width == "0" or height == "0" or "recaptcha" in src.lower():
                    return
                self._add(self.embeds, src)
        elif tag in {"video", "source"}:
            src = attr.get("src") or attr.get("data-src") or ""
            if src and not src.lower().startswith(("javascript:", "data:")):
                media_type = attr.get("type", "")
                label = attr.get("label") or attr.get("data-quality") or media_type or "Direct media"
                self._add_media(src, label, media_type)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_text.append(data)
        if self.in_h1:
            self.h1_text.append(data)

    def _add(self, items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    def _add_media(self, url: str, label: str, media_type: str) -> None:
        if not any(item["url"] == url for item in self.media):
            self.media.append({"url": url, "label": label[:60], "type": media_type[:80]})


def _absolute_http_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    absolute = urljoin(base_url, value.strip())
    parsed = urlsplit(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return absolute


def parse_post_html(html: str, source_url: str) -> HtmlPostPage:
    """Parse metadata, thumbnails, direct source tags and embed URLs offline."""
    parser = _PostHtmlParser()
    parser.feed(html)
    meta = parser.meta
    canonical = _absolute_http_url(parser.canonical or meta.get("og:url"), source_url)
    title = (
        meta.get("og:title")
        or meta.get("twitter:title")
        or meta.get("title")
        or " ".join("".join(parser.h1_text).split()).strip()
        or " ".join("".join(parser.title_text).split()).strip()
        or None
    )
    description = meta.get("og:description") or meta.get("description")
    images = [
        absolute for value in parser.images
        if (absolute := _absolute_http_url(value, source_url))
    ]
    media_urls = []
    for item in parser.media:
        absolute = _absolute_http_url(item["url"], source_url)
        if absolute:
            media_urls.append({**item, "url": absolute})
    embeds = [
        absolute for value in parser.embeds
        if (absolute := _absolute_http_url(value, source_url))
    ]
    media_id = None
    for candidate in (canonical or source_url, source_url):
        match = re.search(r"/(\d+)(?:\.mp4)?(?:[/?#]|$)", candidate)
        if match:
            media_id = match.group(1)
            break
    return HtmlPostPage(
        source_url=source_url,
        title=title,
        description=description,
        canonical_url=canonical,
        thumbnail_url=images[0] if images else None,
        duration_seconds=parser.duration,
        media_id=media_id,
        embed_urls=embeds,
        preview_images=images,
        media_urls=media_urls,
    )


def _assert_public_http_url(url: str) -> str:
    try:
        parsed = parse_url(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError, URLValidationError) as exc:
        raise HtmlPostResolveError(f"Could not validate provider URL: {exc}") from exc
    if not addresses:
        raise HtmlPostResolveError("Provider hostname did not resolve.")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0].split("%", 1)[0])
        if not address.is_global:
            raise HtmlPostResolveError("Private or reserved network destinations are blocked.")
    return parsed.normalized


async def fetch_post_html(url: str, timeout: float = 25.0) -> tuple[str, str]:
    """Fetch one public HTML page with manually validated redirects."""
    current = _assert_public_http_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=False, trust_env=False
    ) as client:
        for _ in range(8):
            current = _assert_public_http_url(current)
            try:
                response = await client.get(current)
            except httpx.HTTPError as exc:
                raise HtmlPostResolveError(f"Provider page request failed: {exc}") from exc
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise HtmlPostResolveError("Redirect response has no Location header.")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "html" not in content_type and "text/" not in content_type:
                raise HtmlPostResolveError("Provider returned a non-HTML response.")
            return response.text, current
    raise HtmlPostResolveError("Provider page exceeded the redirect limit.")


class HtmlPostProvider:
    """Base adapter for independent single-post HTML providers."""

    name = "html-post"
    display_name = "HTML Post"
    hosts: set[str] = set()

    def supports_url(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            return parsed.scheme.lower() in {"http", "https"} and host in self.hosts
        except ValueError:
            return False

    def classify_url(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
            if not self.supports_url(url) or not parsed.path.strip("/"):
                return "unknown"
            return "episode"
        except ValueError:
            return "unknown"

    async def discover_episodes(self, url: str) -> list[dict[str, str]]:
        # These providers represent single post pages, not series indexes.
        return []

    async def resolve(self, episode_url: str) -> dict:
        if not self.supports_url(episode_url):
            raise HtmlPostResolveError(f"Unsupported URL for {self.display_name}.")
        html, final_url = await fetch_post_html(episode_url)
        page = parse_post_html(html, final_url)
        if not page.media_urls:
            embed_note = (
                f" Page contains {len(page.embed_urls)} embedded player(s), "
                "but no direct <video>/<source> URL was found."
                if page.embed_urls else " No direct media source was found."
            )
            raise HtmlPostResolveError(
                f"{self.display_name} metadata was read, but direct download resolution is not supported yet."
                + embed_note
            )
        sources = []
        for index, media in enumerate(page.media_urls, start=1):
            label = media["label"]
            if label.lower() in {"video/mp4", "video/webm", "application/vnd.apple.mpegurl"}:
                label = label.split("/")[-1].upper()
            if label == "Direct media":
                label = f"Direct source {index}"
            sources.append({"label": label, "type": media["type"], "url": media["url"]})
        return {"provider": self.name, "page": page.to_dict(), "sources": sources}
