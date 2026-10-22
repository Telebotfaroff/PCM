#!/usr/bin/env python3
"""Fetch a public website's raw HTML for provider research."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 20
USER_AGENT = "PCM-ProviderHTML/1.0 (+https://github.com/Telebotfaroff/PCM)"


def validate_public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must use http:// or https:// and include a hostname.")
    if parts.username or parts.password:
        raise ValueError("URLs containing embedded credentials are not allowed.")
    if parts.port and not (1 <= parts.port <= 65535):
        raise ValueError("Invalid URL port.")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Local hostnames are not allowed.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
            }
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve hostname: {host}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private, local, and non-public IP destinations are not allowed.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def fetch_html(start_url: str) -> tuple[str, bytes, str]:
    current = validate_public_url(start_url)
    opener = build_opener(NoRedirectHandler)
    for redirect_count in range(MAX_REDIRECTS + 1):
        request = Request(
            current,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("Too many redirects.") from exc
                current = validate_public_url(urljoin(current, exc.headers["Location"]))
                continue
            raise ValueError(f"Website returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ValueError(f"Could not fetch website: {exc.reason}") from exc

        with response:
            status = response.status
            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect response did not include a Location header.")
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("Too many redirects.")
                current = validate_public_url(urljoin(current, location))
                continue
            if status < 200 or status >= 300:
                raise ValueError(f"Website returned HTTP {status}.")
            content_type = response.headers.get_content_type().lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"Expected HTML, received {content_type}.")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("HTML response exceeds the 2 MiB safety limit.")
            encoding = response.headers.get_content_charset() or "utf-8"
            try:
                body.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                encoding = "utf-8"
            return current, body, encoding
    raise ValueError("Could not resolve redirects safely.")


def main() -> int:
    url = os.environ.get("WEBSITE_URL", "").strip()
    if not url:
        print("WEBSITE_URL is required.", file=sys.stderr)
        return 2
    try:
        final_url, body, encoding = fetch_html(url)
    except ValueError as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    host = urlsplit(final_url).hostname or "website"
    host_slug = re.sub(r"[^a-zA-Z0-9.-]+", "-", host).strip(".-").lower() or "website"
    digest = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:8]
    os.makedirs("providerhtml", exist_ok=True)
    path = f"providerhtml/{host_slug}-{digest}.html"
    with open(path, "wb") as output:
        output.write(body)
    print(f"Saved {len(body)} bytes from {final_url} to {path} (encoding hint: {encoding}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
