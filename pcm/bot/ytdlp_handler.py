"""Owner-only /ytdlp command using yt-dlp for supported video sites."""
from __future__ import annotations

import asyncio
import re
import secrets
import sys
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

from pcm.bot.access import owner_filter
from pcm.core.config import Settings
from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.transfers.downloader import _assert_public_host

_MAX_UPLOAD_BYTES = 1900 * 1024 * 1024
_PROGRESS = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%.*?(?:at\s+(.+?))?(?:\s+ETA\s+(.+))?$")


def register_ytdlp_handler(app: Client, owner_id: int) -> None:
    """Register /ytdlp URL; download a supported video and send it to the owner."""
    private_owner = filters.private & owner_filter(owner_id)

    @app.on_message(filters.command("ytdlp") & private_owner)
    async def ytdlp_command(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /ytdlp https://example.com/video")
            return

        try:
            parsed = parse_url(parts[1].strip())
            url = parsed.normalized
            await asyncio.to_thread(_assert_public_host, url)
        except (URLValidationError, ValueError, OSError) as exc:
            await message.reply_text(f"❌ URL rejected: {str(exc)[:300]}")
            return
        except Exception as exc:
            await message.reply_text(f"❌ Could not validate URL: {str(exc)[:300]}")
            return

        settings = Settings.from_env(require_secrets=False)
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        marker = secrets.token_hex(5)
        output_template = str(settings.temp_dir / f"ytdlp-{marker}-%(title).80B-%(id)s.%(ext)s")
        status = await message.reply_text("🔎 Starting yt-dlp…")
        process = None
        output_path: Path | None = None
        last_update = 0.0
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "yt_dlp",
                "--ignore-config", "--no-playlist", "--no-warnings", "--newline",
                "--restrict-filenames", "--max-filesize", f"{min(settings.max_file_size_mb, 1900)}M",
                "-f", "best[ext=mp4]/best",
                "-o", output_template,
                "--print", "after_move:filepath",
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert process.stdout is not None
            while True:
                try:
                    raw = await asyncio.wait_for(process.stdout.readline(), timeout=3600)
                except asyncio.TimeoutError as exc:
                    process.kill()
                    await process.wait()
                    raise RuntimeError("yt-dlp produced no output for one hour; stopped.") from exc
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("[download]"):
                    match = _PROGRESS.search(line)
                    now = time.monotonic()
                    if match and now - last_update >= 4:
                        last_update = now
                        percent, speed, eta = match.groups()
                        detail = f"\nSpeed: {speed.strip()}" if speed else ""
                        detail += f"\nETA: {eta.strip()}" if eta else ""
                        await status.edit_text(
                            f"📥 yt-dlp downloading: {percent}%{detail}"
                        )
                elif line.startswith(str(settings.temp_dir)):
                    candidate = Path(line)
                    if candidate.exists() and candidate.is_file():
                        output_path = candidate

            return_code = await process.wait()
            if return_code != 0:
                raise RuntimeError(
                    "yt-dlp could not download this URL. It may be unsupported, private, "
                    "or require cookies/login."
                )
            if output_path is None or not output_path.exists():
                candidates = list(settings.temp_dir.glob(f"ytdlp-{marker}-*"))
                candidates = [path for path in candidates if path.is_file()]
                if len(candidates) == 1:
                    output_path = candidates[0]
            if output_path is None or not output_path.exists():
                raise RuntimeError("yt-dlp finished but no output video was found.")
            size = output_path.stat().st_size
            if size <= 0:
                raise RuntimeError("yt-dlp created an empty file.")
            if size > _MAX_UPLOAD_BYTES:
                raise RuntimeError("Video exceeds the bot upload limit (about 1.9 GiB).")
            await status.edit_text("📤 Uploading video to your private chat…")
            await app.send_video(
                chat_id=message.chat.id,
                video=str(output_path),
                caption=f"Downloaded with yt-dlp\n{output_path.name[:900]}",
                supports_streaming=True,
            )
            await status.edit_text("✅ yt-dlp download and Telegram upload completed.")
        except Exception as exc:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            await status.edit_text(f"❌ yt-dlp failed: {str(exc)[:650]}")
        finally:
            if output_path:
                output_path.unlink(missing_ok=True)
            else:
                for candidate in settings.temp_dir.glob(f"ytdlp-{marker}-*"):
                    candidate.unlink(missing_ok=True)
