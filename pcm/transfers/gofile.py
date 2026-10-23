"""GoFile v2 uploader supporting guest and account-token uploads."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx

_API = "https://api.gofile.io"


class GoFileError(RuntimeError):
    """Raised when GoFile rejects an upload or returns an invalid response."""


def _payload(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GoFileError(f"GoFile returned invalid JSON (HTTP {response.status_code}).") from exc
    if response.is_error:
        raise GoFileError(f"GoFile HTTP error {response.status_code}.")
    if not isinstance(body, dict) or body.get("status") != "ok":
        message = body.get("message", "request failed") if isinstance(body, dict) else "invalid response"
        raise GoFileError(f"GoFile API error: {str(message)[:250]}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise GoFileError("GoFile response did not contain upload data.")
    return data


async def _upload_server(client: httpx.AsyncClient) -> str:
    response = await client.get(f"{_API}/servers")
    data = _payload(response)
    servers = data.get("servers")
    if not isinstance(servers, list) or not servers:
        raise GoFileError("GoFile did not return an available upload server.")
    server = servers[0]
    if isinstance(server, dict):
        name = server.get("name")
        if name:
            return f"https://{name}.gofile.io"
    if isinstance(server, str) and server:
        return f"https://{server}.gofile.io"
    raise GoFileError("GoFile returned an invalid upload server.")


async def upload_file(
    path: str | Path,
    *,
    token: str | None = None,
    folder_id: str | None = None,
    timeout_seconds: float = 3600,
) -> dict[str, str]:
    """Upload one file using GoFile guest mode or an account token.

    Returns a small normalized dictionary with download page, file name, and code.
    The account token is never logged or included in returned data.
    """
    file_path = Path(path)
    if not file_path.is_file() or file_path.stat().st_size <= 0:
        raise GoFileError("Upload file does not exist or is empty.")
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    headers = {"Authorization": f"Bearer {token.strip()}"} if token and token.strip() else {}
    timeout = httpx.Timeout(timeout_seconds, connect=30)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        server = await _upload_server(client)
        data: dict[str, str] = {}
        if folder_id:
            data["folderId"] = folder_id
        if token and token.strip():
            data["token"] = token.strip()
        with file_path.open("rb") as file_handle:
            response = await client.post(
                f"{server}/uploadfile",
                data=data,
                files={"file": (file_path.name, file_handle, mime)},
                headers=headers,
            )
        result = _payload(response)
    page = result.get("downloadPage") or result.get("directLink")
    code = result.get("code")
    if not page and code:
        page = f"https://gofile.io/d/{code}"
    if not page:
        raise GoFileError("GoFile upload succeeded without a share URL.")
    return {"url": str(page), "name": str(result.get("fileName") or file_path.name), "code": str(code or "")}
