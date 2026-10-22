import base64

import pytest

from pcm.providers.watchhentai_resolver import (
    ProviderResolveError,
    decode_source,
    parse_sources,
)


def _encode_source(url: str) -> str:
    inner = base64.b64encode(url.encode("utf-8"))
    reversed_bytes = inner[::-1]
    transformed = bytes(byte ^ ((13 + (i % 17)) & 255) for i, byte in enumerate(reversed_bytes))
    return base64.urlsafe_b64encode(transformed).decode("ascii").rstrip("=")


def test_decode_watchhentai_source_url() -> None:
    url = "https://cdn.example.test/video.mp4?token=abc"
    assert decode_source(_encode_source(url)) == url


def test_parse_sources_returns_quality_and_url() -> None:
    encoded = _encode_source("https://cdn.example.test/video-1080.mp4")
    html = f'var whJwSources = [{{"label":"1080p","type":"video/mp4","file":"{encoded}"}}];'
    assert parse_sources(html) == [{
        "label": "1080p",
        "type": "video/mp4",
        "url": "https://cdn.example.test/video-1080.mp4",
    }]


def test_parse_sources_rejects_missing_array() -> None:
    with pytest.raises(ProviderResolveError, match="whJwSources"):
        parse_sources("<html><body>no sources</body></html>")


def test_decode_rejects_non_url() -> None:
    with pytest.raises(ProviderResolveError, match="HTTP"):
        decode_source(_encode_source("not-a-url"))
