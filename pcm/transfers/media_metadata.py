"""Read media metadata and create Telegram-compatible video thumbnails with FFmpeg."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoMetadata:
    duration: int
    width: int
    height: int
    thumbnail: Path | None


def _probe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=width,height,duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract(path: Path, thumbnail_path: Path) -> VideoMetadata:
    probe = _probe(path)
    streams = probe.get("streams") or []
    stream = streams[0] if streams else {}
    fmt = probe.get("format") or {}
    try:
        duration = max(0, int(float(stream.get("duration") or fmt.get("duration") or 0)))
    except (ValueError, TypeError, OverflowError):
        duration = 0
    try:
        width = max(0, int(stream.get("width") or 0))
        height = max(0, int(stream.get("height") or 0))
    except (ValueError, TypeError):
        width, height = 0, 0

    thumbnail: Path | None = None
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        # Sample at 1 second, or earlier for short clips. Keep Telegram's thumb small.
        seek = min(1.0, max(0.0, duration / 3))
        result = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", str(seek), "-i", str(path), "-frames:v", "1",
                "-vf", "scale=w='min(320,iw)':h='min(320,ih)':force_original_aspect_ratio=decrease",
                "-q:v", "5", str(thumbnail_path),
            ],
            capture_output=True, text=True, timeout=45, check=False,
        )
        if result.returncode == 0 and thumbnail_path.exists():
            if thumbnail_path.stat().st_size <= 200 * 1024:
                thumbnail = thumbnail_path
            else:
                thumbnail_path.unlink(missing_ok=True)
    return VideoMetadata(duration=duration, width=width, height=height, thumbnail=thumbnail)


async def prepare_video_metadata(path: str | Path) -> VideoMetadata:
    """Probe a downloaded video and generate a small JPEG thumbnail when FFmpeg exists."""
    source = Path(path)
    thumbnail_path = source.with_name(f"{source.stem}-thumb.jpg")
    return await asyncio.to_thread(_extract, source, thumbnail_path)
