"""Conservative URL parsing and host/IP safety checks.

This module validates URL syntax and literal IP addresses. Network fetchers must
also validate DNS results and every redirect immediately before making requests.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class URLValidationError(ValueError):
    """Raised when a URL is malformed or points at a prohibited destination."""


@dataclass(frozen=True, slots=True)
class ParsedURL:
    original: str
    normalized: str
    scheme: str
    hostname: str
    port: int | None


def _validate_literal_ip(host: str) -> None:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if not address.is_global:
        raise URLValidationError("Private or reserved IP destinations are not allowed")


def parse_url(value: str) -> ParsedURL:
    """Parse an HTTP(S) URL and reject credentials, invalid ports, and unsafe IPs."""
    if not isinstance(value, str) or not value.strip():
        raise URLValidationError("URL is empty")
    raw = value.strip()
    if any(ord(char) < 32 for char in raw):
        raise URLValidationError("URL contains control characters")

    try:
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise URLValidationError("URL is malformed") from exc

    if scheme not in {"http", "https"}:
        raise URLValidationError("Only HTTP and HTTPS URLs are supported")
    if not hostname:
        raise URLValidationError("URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise URLValidationError("URLs containing embedded credentials are not allowed")

    host = hostname.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise URLValidationError("Local destinations are not allowed")
    _validate_literal_ip(host)

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise URLValidationError("Hostname is invalid") from exc

    netloc = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    if port is not None:
        netloc = f"{netloc}:{port}"

    normalized = urlunsplit(
        (scheme, netloc, parts.path or "/", parts.query, parts.fragment)
    )
    return ParsedURL(
        original=raw,
        normalized=normalized,
        scheme=scheme,
        hostname=ascii_host,
        port=port,
    )
