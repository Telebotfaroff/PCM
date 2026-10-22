"""Streaming HTTP download with redirect/DNS checks and media validation."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin

import httpx

from pcm.resolver.url_model import URLValidationError, parse_url


class DownloadError(RuntimeError):
    """Raised when a media download fails validation or transport."""


def _assert_public_host(url: str) -> None:
    parsed = parse_url(url)
    try:
        records = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except OSError as exc:
        raise DownloadError(f"Cannot resolve media host: {parsed.hostname}") from exc
    if not records:
        raise DownloadError("Media host did not resolve")
    for record in records:
        address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        if not address.is_global:
            raise URLValidationError("Private or reserved network destinations are blocked")


async def download_media(
    url: str,
    destination: str | Path,
    *,
    referer: str | None = None,
    max_bytes: int = 2 * 1024 * 1024 * 1024,
    timeout: float = 45.0,
    progress=None,
) -> Path:
    """Download a media URL without buffering the full response in memory."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    current = url
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    if referer:
        headers["Referer"] = referer
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=20), trust_env=False) as client:
            for _ in range(9):
                _assert_public_host(current)
                async with client.stream("GET", current, headers=headers, follow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DownloadError("Media redirect has no Location header")
                        current = urljoin(current, location)
                        headers["Referer"] = referer or current
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" in content_type or "application/json" in content_type:
                        raise DownloadError("The source returned a webpage, not a media file")
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise DownloadError(f"Media exceeds the {max_bytes // (1024 * 1024)} MiB limit")
                    total = int(length) if length and length.isdigit() else 0
                    written = 0
                    first = b""
                    with target.open("wb") as output:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            if not chunk:
                                continue
                            if not first:
                                first = chunk[:32]
                                if first.lstrip().lower().startswith((b"<!doctype html", b"<html", b"{")):
                                    raise DownloadError("The source response is not a video file")
                            written += len(chunk)
                            if written > max_bytes:
                                raise DownloadError("Downloaded media exceeded the configured size limit")
                            output.write(chunk)
                            if progress:
                                result = progress(written, total)
                                if asyncio.iscoroutine(result):
                                    await result
                    if written == 0:
                        raise DownloadError("The media response was empty")
                    if content_type and not any(token in content_type for token in ("video/", "octet-stream", "application/mp4")) and b"ftyp" not in first:
                        raise DownloadError(f"Unexpected media content type: {content_type}")
                    return target
            raise DownloadError("Too many media redirects")
    except Exception:
        target.unlink(missing_ok=True)
        raise
