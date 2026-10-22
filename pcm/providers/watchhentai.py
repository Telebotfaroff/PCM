"""Parse saved WatchHentai WordPress pages without network access."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse, urlunparse


PageType = Literal["series", "episode", "unknown"]


@dataclass(slots=True)
class WatchHentaiEpisode:
    """One episode entry discovered on a series page."""

    title: str
    url: str
    audio_type: str | None = None
    episode_number: int | None = None
    thumbnail_url: str | None = None
    release_date: str | None = None


@dataclass(slots=True)
class WatchHentaiPage:
    source_url: str | None = None
    page_type: PageType = "unknown"
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    thumbnail_url: str | None = None
    preview_images: list[str] = field(default_factory=list)
    primary_player_url: str | None = None
    alternate_player_url: str | None = None
    player_id: str | None = None
    previous_episode_url: str | None = None
    next_episode_url: str | None = None
    series_url: str | None = None
    genres: list[str] = field(default_factory=list)
    episodes: list[WatchHentaiEpisode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def classify_url(url: str) -> PageType:
    """Classify a WatchHentai URL by its path, without fetching it."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return "unknown"
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return "unknown"
    if parsed.hostname.lower().removeprefix("www.") != "watchhentai.net":
        return "unknown"
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0].lower() == "series" and len(segments) >= 2:
        return "series"
    if segments and segments[0].lower() == "videos" and len(segments) >= 2:
        return "episode"
    return "unknown"


def _clean_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url or "https://watchhentai.net/", url.strip())
    parsed = urlparse(absolute)
    # Query strings and fragments are tracking/navigation state, not page identity.
    path = parsed.path or "/"
    if path != "/" and not path.endswith("/"):
        path += "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = WatchHentaiPage()
        self._capture: str | None = None
        self._capture_parts: list[str] = []
        self._div_classes: list[set[str]] = []
        self._li_audio: list[str | None] = []
        self._episode_anchor: dict[str, str | None] | None = None
        self._episode_parts: list[str] = []
        self._episode_date_parts: list[str] = []
        self._in_episode_date = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "div":
            self._div_classes.append(classes)
        elif tag == "li":
            self._li_audio.append(attr.get("data-audio") or None)

        if tag == "meta":
            key = (attr.get("property") or attr.get("name") or attr.get("itemprop") or "").lower()
            value = attr.get("content", "").strip()
            if key == "description" and value:
                self.page.description = self.page.description or value
            elif key == "og:description" and value:
                self.page.description = value
            elif key == "og:title" and value:
                self.page.title = self.page.title or value
            elif key == "og:url" and value:
                self.page.canonical_url = self.page.canonical_url or value
            elif key == "og:image" and value:
                self._add_unique(self.page.preview_images, value.strip())
            elif key in {"contenturl", "embedurl"} and value:
                self.page.primary_player_url = self.page.primary_player_url or value
        elif tag == "link" and attr.get("rel", "").lower() == "canonical":
            self.page.canonical_url = attr.get("href") or self.page.canonical_url
        elif tag == "title":
            self._begin_capture("title")
        elif tag == "h1" and "module-title" in classes:
            self._begin_capture("h1")
        elif tag == "iframe":
            primary = attr.get("data-primary-player-url")
            alternate = attr.get("data-alternate-player-url")
            if primary:
                self.page.primary_player_url = primary
                parts = primary.rstrip("/").split("/")
                if len(parts) >= 3 and parts[-3].isdigit():
                    self.page.player_id = parts[-3]
            if alternate:
                self.page.alternate_player_url = alternate
        elif tag == "a":
            href = attr.get("href", "").strip()
            aria_label = attr.get("aria-label", "").lower()
            if "item-prev" in classes or aria_label == "previous episode":
                self.page.previous_episode_url = href or self.page.previous_episode_url
            if "item-next" in classes or aria_label == "next episode":
                self.page.next_episode_url = href or self.page.next_episode_url

            in_all_episodes = any("item-all" in parent for parent in self._div_classes)
            if "/series/" in urlparse(href).path and in_all_episodes:
                self.page.series_url = href

            if "tv-ep-card-link" in classes and self._li_audio:
                self._episode_anchor = {
                    "url": href,
                    "title": attr.get("title", ""),
                    "audio_type": next((audio for audio in reversed(self._li_audio) if audio), ""),
                    "thumbnail_url": "",
                    "release_date": "",
                }
                self._episode_parts = []
                self._episode_date_parts = []
        elif tag == "img" and self._episode_anchor is not None:
            image_url = attr.get("data-src") or attr.get("data-lazy-src") or attr.get("src", "")
            if image_url and not image_url.startswith("data:"):
                self._episode_anchor["thumbnail_url"] = image_url
        elif tag == "span" and "date" in classes and self._episode_anchor is not None:
            self._in_episode_date = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._in_episode_date:
            self._in_episode_date = False
        if tag == "a" and self._episode_anchor is not None:
            href = self._episode_anchor.get("url", "")
            if href:
                title = self._episode_anchor.get("title") or " ".join(self._episode_parts)
                title = re.sub(r"\s+Watch Hentai\s*$", "", title).strip()
                match = re.search(r"episode\s*(\d+(?:\.\d+)?)", title, re.I)
                if not match:
                    match = re.search(r"episode-(\d+(?:-\d+)?)", href, re.I)
                number = None
                if match:
                    try:
                        number = int(float(match.group(1).replace("-", ".")))
                    except ValueError:
                        number = None
                episode = WatchHentaiEpisode(
                    title=title or href,
                    url=href,
                    audio_type=self._episode_anchor.get("audio_type") or None,
                    episode_number=number,
                    thumbnail_url=self._episode_anchor.get("thumbnail_url") or None,
                    release_date=" ".join(self._episode_date_parts).strip() or None,
                )
                if not any(existing.url == episode.url for existing in self.page.episodes):
                    self.page.episodes.append(episode)
            self._episode_anchor = None
            self._episode_parts = []
            self._episode_date_parts = []
            self._in_episode_date = False
        if tag == "li" and self._li_audio:
            self._li_audio.pop()
        if tag == "div" and self._div_classes:
            self._div_classes.pop()
        if self._capture == tag:
            value = " ".join("".join(self._capture_parts).split()).strip()
            if value:
                if tag == "h1":
                    self.page.title = value
                elif tag == "title":
                    self.page.title = self.page.title or value
            self._capture = None
            self._capture_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._capture_parts.append(data)
        if self._episode_anchor is not None:
            if self._in_episode_date:
                self._episode_date_parts.append(data)
            else:
                self._episode_parts.append(data)

    def _begin_capture(self, tag: str) -> None:
        if self._capture is None:
            self._capture = tag
            self._capture_parts = []

    @staticmethod
    def _add_unique(items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)


def parse_html(html: str, source_url: str | None = None) -> WatchHentaiPage:
    """Parse a saved series or episode document; never fetches URLs or executes JavaScript."""
    parser = _PageParser()
    parser.feed(html)
    page = parser.page
    page.source_url = source_url
    identity_url = page.canonical_url or source_url
    if identity_url:
        identity_url = _clean_url(identity_url, source_url)
        page.canonical_url = identity_url
        page.page_type = classify_url(identity_url)
    if page.page_type == "series":
        page.series_url = page.canonical_url
    elif page.series_url:
        page.series_url = _clean_url(page.series_url, source_url)
    for attr in ("primary_player_url", "alternate_player_url", "previous_episode_url"):
        value = getattr(page, attr)
        if value:
            setattr(page, attr, _clean_url(value, source_url))
    for episode in page.episodes:
        episode.url = _clean_url(episode.url, source_url)
        if episode.thumbnail_url:
            episode.thumbnail_url = urljoin(source_url or "https://watchhentai.net/", episode.thumbnail_url)
    page.preview_images = [
        urljoin(source_url or "https://watchhentai.net/", image) for image in page.preview_images
    ]
    page.thumbnail_url = page.preview_images[0] if page.preview_images else None
    return page


def parse_file(path: str | Path, source_url: str | None = None) -> WatchHentaiPage:
    """Parse a previously saved provider HTML file."""
    return parse_html(Path(path).read_text(encoding="utf-8", errors="replace"), source_url)
