import pytest

from pcm.resolver.classify import ContentKind, classify_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://cdn.example/video.mp4?token=abc", ContentKind.DIRECT_VIDEO),
        ("https://cdn.example/audio.flac", ContentKind.DIRECT_AUDIO),
        ("https://cdn.example/image.webp", ContentKind.DIRECT_IMAGE),
        ("https://cdn.example/file.zip", ContentKind.DIRECT_FILE),
        ("https://example.com/watch/123", ContentKind.WEBPAGE),
    ],
)
def test_classifies_by_path_extension(url, expected):
    assert classify_url(url) is expected
