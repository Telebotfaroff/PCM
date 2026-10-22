"""Live WatchHentai episode/player resolver. No browser or JavaScript execution."""
from __future__ import annotations

import base64
import binascii
import json
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.providers.watchhentai import parse_html


class ProviderResolveError(RuntimeError):
    """Raised when an episode's playable sources cannot be resolved."""


def _assert_public_host(url: str) -> None:
    parsed = parse_url(url)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ProviderResolveError(f"Cannot resolve host: {parsed.hostname}") from exc
    if not addresses:
        raise ProviderResolveError("Host did not resolve to an address")
    import ipaddress
    for item in addresses:
        address = ipaddress.ip_address(item[4][0].split("%", 1)[0])
        if not address.is_global:
            raise URLValidationError("Private or reserved network destinations are blocked")


async def _get_text(client: httpx.AsyncClient, url: str, referer: str | None = None) -> str:
    current = url
    headers = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    for _ in range(9):
        _assert_public_host(current)
        response = await client.get(current, headers=headers, follow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise ProviderResolveError("Redirect response has no Location header")
            current = urljoin(current, location)
            headers["Referer"] = url
            continue
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "text/" not in content_type:
            raise ProviderResolveError("Expected an HTML player response")
        return response.text
    raise ProviderResolveError("Too many redirects")


def decode_source(value: str) -> str:
    """Decode WatchHentai's URL-safe base64/XOR/reverse source field."""
    try:
        normalized = value.replace("-", "+").replace("_", "/")
        normalized += "=" * (-len(normalized) % 4)
        first = base64.b64decode(normalized, validate=True)
        transformed = bytes(byte ^ ((13 + index % 17) & 255) for index, byte in enumerate(first))[::-1]
        decoded = base64.b64decode(transformed, validate=True).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ProviderResolveError("Player source could not be decoded") from exc
    parsed = urlsplit(decoded)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderResolveError("Decoded source is not an HTTP(S) URL")
    parse_url(decoded)
    return decoded


def parse_sources(player_html: str) -> list[dict[str, str]]:
    match = re.search(r"var\s+whJwSources\s*=\s*(\[[\s\S]*?\]);", player_html)
    if not match:
        raise ProviderResolveError("No whJwSources array found in player HTML")
    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ProviderResolveError("Player source list is invalid JSON") from exc
    if not isinstance(entries, list):
        raise ProviderResolveError("Player source list is not an array")
    sources: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            continue
        try:
            url = decode_source(entry["file"])
        except ProviderResolveError:
            continue
        label = str(entry.get("label") or "Unknown")[:40]
        media_type = str(entry.get("type") or "video/mp4")[:80]
        if not any(item["url"] == url for item in sources):
            sources.append({"label": label, "type": media_type, "url": url})
    if not sources:
        raise ProviderResolveError("No usable media sources were found")
    return sources


class WatchHentaiResolver:
    """Fetch an episode and its player page to return fresh media sources."""

    def __init__(self, timeout: float = 25.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }

    async def resolve(self, episode_url: str) -> dict:
        parsed = parse_url(episode_url)
        if parsed.hostname.lower() not in {"watchhentai.net", "www.watchhentai.net"} or not parsed.normalized.split("?", 1)[0].rstrip("/").endswith(tuple()):
            # The explicit path check below gives a clear provider boundary.
            if parsed.hostname.lower() not in {"watchhentai.net", "www.watchhentai.net"}:
                raise ProviderResolveError("Only WatchHentai episode URLs are supported")
        if not re.search(r"/videos/[^/]+/?$", urlsplit(parsed.normalized).path, re.I):
            raise ProviderResolveError("URL must be a WatchHentai episode page (/videos/...)")

        async with httpx.AsyncClient(
            headers=self.headers, timeout=self.timeout, follow_redirects=False, trust_env=False
        ) as client:
            episode_html = await _get_text(client, parsed.normalized)
            page = parse_html(episode_html, parsed.normalized)
            player_url = page.primary_player_url
            if not player_url:
                raise ProviderResolveError("Episode page has no primary player URL")
            player_html = await _get_text(client, player_url, parsed.normalized)
            sources = parse_sources(player_html)
        return {
            "provider": "watchhentai",
            "page": page.to_dict(),
            "player_url": player_url,
            "sources": sources,
        }
