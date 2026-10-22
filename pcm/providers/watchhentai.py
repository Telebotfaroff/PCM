"""Parse saved WatchHentai WordPress episode pages without network access."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


@dataclass(slots=True)
class WatchHentaiPage:
    source_url: str | None = None
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    thumbnail_url: str | None = None
    preview_images: list[str] | None = None
    primary_player_url: str | None = None
    alternate_player_url: str | None = None
    player_id: str | None = None
    previous_episode_url: str | None = None
    series_url: str | None = None
    genres: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = WatchHentaiPage(preview_images=[], genres=[])
        self._capture: str | None = None
        self._capture_depth = 0
        self._capture_parts: list[str] = []
        self._div_classes: list[set[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "div":
            self._div_classes.append(set(attr.get("class", "").split()))
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
                self._add_unique(self.page.preview_images, value)
            elif key in {"contenturl", "embedurl"} and value:
                self.page.primary_player_url = self.page.primary_player_url or value
        elif tag == "link" and attr.get("rel", "").lower() == "canonical":
            self.page.canonical_url = attr.get("href") or self.page.canonical_url
        elif tag == "title":
            self._begin_capture("title")
        elif tag == "h1" and "module-title" in attr.get("class", "").split():
            self._begin_capture("h1")
        elif tag == "iframe":
            primary = attr.get("data-primary-player-url")
            alternate = attr.get("data-alternate-player-url")
            if primary:
                self.page.primary_player_url = primary
            if alternate:
                self.page.alternate_player_url = alternate
            if primary:
                parts = primary.rstrip("/").split("/")
                if len(parts) >= 3 and parts[-3].isdigit():
                    self.page.player_id = parts[-3]
        elif tag == "a":
            href = attr.get("href", "")
            classes = attr.get("class", "").split()
            if "item-prev" in classes or attr.get("aria-label", "").lower() == "previous episode":
                self.page.previous_episode_url = href or self.page.previous_episode_url
            if "/series/" in href:
                path = href.split("?", 1)[0].rstrip("/")
                is_specific_series = path.strip("/") != "series"
                in_all_episodes = any("item-all" in parent for parent in self._div_classes)
                # Prefer the explicit “All Episodes” link. Otherwise keep the first
                # specific series link, never the generic /series/ navigation link.
                if in_all_episodes or (is_specific_series and not self.page.series_url):
                    self.page.series_url = href
            # Ignore global navigation genres; they are not episode metadata.

    def handle_endtag(self, tag: str) -> None:
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
            self._capture_depth = 0
            self._capture_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._capture_parts.append(data)

    def _begin_capture(self, tag: str) -> None:
        if self._capture is None:
            self._capture = tag
            self._capture_parts = []

    @staticmethod
    def _add_unique(items: list[str] | None, value: str) -> None:
        if items is not None and value not in items:
            items.append(value)


def parse_html(html: str, source_url: str | None = None) -> WatchHentaiPage:
    """Parse one HTML document; does not fetch URLs or execute JavaScript."""
    parser = _PageParser()
    parser.feed(html)
    page = parser.page
    page.source_url = source_url
    if page.canonical_url and source_url:
        page.canonical_url = urljoin(source_url, page.canonical_url)
    if page.primary_player_url and source_url:
        page.primary_player_url = urljoin(source_url, page.primary_player_url)
    if page.alternate_player_url and source_url:
        page.alternate_player_url = urljoin(source_url, page.alternate_player_url)
    if page.previous_episode_url and source_url:
        page.previous_episode_url = urljoin(source_url, page.previous_episode_url)
    if page.series_url and source_url:
        page.series_url = urljoin(source_url, page.series_url)
    page.thumbnail_url = page.preview_images[0] if page.preview_images else None
    return page


def parse_file(path: str | Path, source_url: str | None = None) -> WatchHentaiPage:
    """Parse a previously saved provider HTML file."""
    return parse_html(Path(path).read_text(encoding="utf-8", errors="replace"), source_url)
