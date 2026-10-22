import pytest

from pcm.resolver.url_model import URLValidationError, parse_url


def test_normalizes_scheme_and_hostname():
    result = parse_url("HTTPS://Example.COM/video?id=4")
    assert result.scheme == "https"
    assert result.hostname == "example.com"
    assert result.normalized == "https://example.com/video?id=4"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example.com/video",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.4/",
        "http://169.254.169.254/latest/meta-data/",
        "http://user:pass@example.com/",
        "https://example.com:bad/path",
    ],
)
def test_rejects_invalid_or_unsafe_urls(value):
    with pytest.raises(URLValidationError):
        parse_url(value)


def test_preserves_query_parameters():
    result = parse_url("https://example.com/file?token=a%2Fb&expires=123")
    assert "token=a%2Fb&expires=123" in result.normalized
