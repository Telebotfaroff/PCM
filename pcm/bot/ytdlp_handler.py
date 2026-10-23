"""Owner-only /ytdlp command with download/upload progress and large-video splitting."""
from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message

from pcm.bot.access import owner_filter
from pcm.bot.persistent_settings import load_preferences
from pcm.core.config import Settings
from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.transfers.downloader import _assert_public_host
from pcm.transfers.gofile import upload_file as gofile_upload

# Leave headroom below Telegram's approximate 2 GB bot upload limit.
_PART_LIMIT_BYTES = 1750 * 1024 * 1024
_PERCENT = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_SPEED = re.compile(r"\bat\s+(.+?)(?=\s+ETA\s+|$)")
_ETA = re.compile(r"\bETA\s+(.+)$")


def _human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


async def _run_capture(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail[-500:] or f"Command failed: {args[0]}")
    return stdout.decode("utf-8", errors="replace").strip()


async def _split_video(source: Path, work_dir: Path, status: Message) -> list[Path]:
    """Split a large video into independently playable MKV segments under the upload limit."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("This video is too large for one Telegram upload. Install ffmpeg and ffprobe to split it.")

    duration_text = await _run_capture(
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source)
    )
    try:
        duration = float(duration_text)
    except ValueError as exc:
        raise RuntimeError("Could not read video duration to split this file.") from exc
    if duration <= 0:
        raise RuntimeError("Video duration is invalid; cannot split safely.")

    work_dir.mkdir(parents=True, exist_ok=True)
    # Start conservatively, then shorten segments if variable bitrate makes a part too large.
    target_seconds = max(10.0, duration * min(0.70, _PART_LIMIT_BYTES / source.stat().st_size * 0.82))
    for attempt in range(6):
        for old in work_dir.glob("part-*.mkv"):
            old.unlink(missing_ok=True)
        await status.edit_text(
            f"✂️ Splitting large video into Telegram-sized parts…\n"
            f"Attempt {attempt + 1}/6"
        )
        await _run_capture(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-map", "0", "-c", "copy", "-f", "segment",
            "-segment_time", f"{target_seconds:.2f}", "-reset_timestamps", "1",
            "-segment_format", "matroska", str(work_dir / "part-%03d.mkv")
        )
        parts = sorted(p for p in work_dir.glob("part-*.mkv") if p.is_file() and p.stat().st_size > 0)
        if parts and all(p.stat().st_size <= _PART_LIMIT_BYTES for p in parts):
            return parts
        target_seconds *= 0.65
    raise RuntimeError("Could not split the video into safe Telegram upload sizes after 6 attempts.")


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
        try:
            preferences = await load_preferences(owner_id)
        except Exception as exc:
            await message.reply_text(f"❌ Could not load destination settings: {str(exc)[:250]}")
            return
        destinations = preferences.get("destinations") or ["telegram"]
        if isinstance(destinations, str):
            import json
            destinations = json.loads(destinations)
        if not destinations or any(item not in {"telegram", "gofile"} for item in destinations):
            await message.reply_text("❌ Invalid upload destination settings. Use /dest telegram, /dest gofile, or /dest both.")
            return
        settings.temp_dir.mkdir(parents=True, exist_ok=True)
        marker = secrets.token_hex(5)
        output_template = str(settings.temp_dir / f"ytdlp-{marker}-%(title).80B-%(id)s.%(ext)s")
        split_dir = settings.temp_dir / f"ytdlp-parts-{marker}"
        status = await message.reply_text("🔎 Starting yt-dlp…")
        process = None
        output_path: Path | None = None
        upload_paths: list[Path] = []
        last_download_update = 0.0
        last_upload_update = 0.0

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "yt_dlp",
                "--ignore-config", "--no-playlist", "--no-warnings", "--newline",
                "--progress", "--restrict-filenames", "--max-filesize",
                f"{settings.max_file_size_mb}M",
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
                    percent_match = _PERCENT.search(line)
                    if percent_match:
                        now = time.monotonic()
                        if now - last_download_update >= 3 or percent_match.group(1) == "100":
                            last_download_update = now
                            speed_match = _SPEED.search(line)
                            eta_match = _ETA.search(line)
                            detail = f"\nSpeed: {speed_match.group(1).strip()}" if speed_match else ""
                            detail += f"\nETA: {eta_match.group(1).strip()}" if eta_match else ""
                            try:
                                await status.edit_text(
                                    f"📥 **yt-dlp download**\nProgress: {percent_match.group(1)}%{detail}"
                                )
                            except Exception:
                                pass
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
                candidates = [p for p in settings.temp_dir.glob(f"ytdlp-{marker}-*") if p.is_file()]
                if len(candidates) == 1:
                    output_path = candidates[0]
            if output_path is None or not output_path.exists():
                raise RuntimeError("yt-dlp finished but no output video was found.")

            size = output_path.stat().st_size
            if size <= 0:
                raise RuntimeError("yt-dlp created an empty file.")
            if "telegram" in destinations and size > _PART_LIMIT_BYTES:
                upload_paths = await _split_video(output_path, split_dir, status)
            else:
                upload_paths = [output_path]

            total_parts = len(upload_paths)
            if "telegram" in destinations:
                for part_index, upload_path in enumerate(upload_paths, start=1):
                    part_size = upload_path.stat().st_size
                    label = f"Part {part_index}/{total_parts}\n" if total_parts > 1 else ""
                    await status.edit_text(
                        f"📤 **Telegram upload**\n{label}Progress: 0%\n"
                        f"Uploaded: 0 B / {_human_size(part_size)}"
                    )

                    async def upload_progress(current: int, total: int, *_args) -> None:
                        nonlocal last_upload_update
                        now = time.monotonic()
                        if current < total and now - last_upload_update < 2.5:
                            return
                        last_upload_update = now
                        percent = (current / total * 100) if total else 0
                        text = (
                            f"📤 **Telegram upload**\n{label}Progress: {percent:.1f}%\n"
                            f"Uploaded: {_human_size(current)} / {_human_size(total)}"
                        )
                        try:
                            await status.edit_text(text)
                        except Exception:
                            pass

                    await app.send_video(
                        chat_id=message.chat.id,
                        video=str(upload_path),
                        caption=(f"Downloaded with yt-dlp\n{label}{upload_path.name[:850]}"),
                        supports_streaming=True,
                        progress=upload_progress,
                    )
            gofile_links: list[str] = []
            if "gofile" in destinations:
                token = None if preferences.get("gofile_guest", False) else (str(preferences.get("gofile_token") or os.getenv("GOFILE_TOKEN", "")).strip() or None)
                for part_index, upload_path in enumerate(upload_paths, start=1):
                    await status.edit_text(
                        f"☁️ **GoFile upload**\nPart {part_index}/{len(upload_paths)}"
                    )
                    result = await gofile_upload(upload_path, token=token)
                    gofile_links.append(result["url"])
            summary = []
            if "telegram" in destinations:
                summary.append(f"Telegram: {total_parts} part(s) uploaded")
            if gofile_links:
                summary.append("GoFile links:\n" + "\n".join(gofile_links))
            await status.edit_text("✅ yt-dlp finished.\n" + "\n".join(summary))
        except Exception as exc:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            try:
                await status.edit_text(f"❌ yt-dlp failed: {str(exc)[:650]}")
            except Exception:
                pass
        finally:
            if output_path:
                output_path.unlink(missing_ok=True)
            for candidate in split_dir.glob("*") if split_dir.exists() else []:
                if candidate.is_file():
                    candidate.unlink(missing_ok=True)
            if split_dir.exists():
                split_dir.rmdir()
