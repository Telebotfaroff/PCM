"""Lightweight URL classification before provider-specific extraction."""

from enum import StrEnum
from pathlib import PurePosixPath
from urllib.parse import urlsplit


class ContentKind(StrEnum):
    DIRECT_VIDEO = "direct_video"
    DIRECT_AUDIO = "direct_audio"
    DIRECT_IMAGE = "direct_image"
    DIRECT_FILE = "direct_file"
    WEBPAGE = "webpage"


_VIDEO = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".ts"}
_AUDIO = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav"}
_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp"}


def classify_url(url: str) -> ContentKind:
    """Classify by URL path extension only; the response must still be validated."""
    suffix = PurePosixPath(urlsplit(url).path.lower()).suffix
    if suffix in _VIDEO:
        return ContentKind.DIRECT_VIDEO
    if suffix in _AUDIO:
        return ContentKind.DIRECT_AUDIO
    if suffix in _IMAGE:
        return ContentKind.DIRECT_IMAGE
    if suffix in {".zip", ".rar", ".7z", ".pdf", ".apk", ".bin"}:
        return ContentKind.DIRECT_FILE
    return ContentKind.WEBPAGE
