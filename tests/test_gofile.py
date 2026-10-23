"""Unit tests for GoFile uploader validation without network access."""
from __future__ import annotations

from pathlib import Path

import pytest

from pcm.transfers.gofile import GoFileError, _payload, upload_file


class FakeResponse:
    def __init__(self, body, *, is_error: bool = False, status_code: int = 200):
        self.body = body
        self.is_error = is_error
        self.status_code = status_code

    def json(self):
        return self.body


def test_payload_accepts_success_response() -> None:
    assert _payload(FakeResponse({"status": "ok", "data": {"code": "abc"}})) == {"code": "abc"}


def test_payload_rejects_api_error() -> None:
    with pytest.raises(GoFileError, match="GoFile API error"):
        _payload(FakeResponse({"status": "error", "message": "bad token"}))


def test_payload_rejects_http_error() -> None:
    with pytest.raises(GoFileError, match="HTTP error 503"):
        _payload(FakeResponse({"status": "ok", "data": {}}, is_error=True, status_code=503))


@pytest.mark.asyncio
async def test_upload_rejects_missing_file_before_network(tmp_path: Path) -> None:
    with pytest.raises(GoFileError, match="does not exist or is empty"):
        await upload_file(tmp_path / "missing.mp4")
