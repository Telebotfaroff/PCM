"""Formatting and throttling for live transfer progress messages."""
from __future__ import annotations

import time


def format_bytes(value: int) -> str:
    """Format byte counts with human-readable binary units."""
    amount = max(0, float(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def format_duration(seconds: float) -> str:
    """Render a non-negative duration as a compact ETA."""
    remaining = max(0, int(seconds))
    hours, remainder = divmod(remaining, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class TransferProgress:
    """Build throttled, rate-aware progress messages for download or upload callbacks."""

    def __init__(self, title: str, phase: str, *, quality: str = "", interval: float = 3.5):
        self.title = title
        self.phase = phase
        self.quality = quality
        self.interval = interval
        self.started_at = time.monotonic()
        self.last_render_at = 0.0
        self.last_sample_at = self.started_at
        self.last_sample_bytes = 0
        self.speed = 0.0

    def render(self, current: int, total: int, *, force: bool = False) -> str | None:
        """Return a message when the throttle permits an edit, otherwise None."""
        now = time.monotonic()
        current = max(0, current)
        total = max(0, total)
        elapsed = now - self.last_sample_at
        if elapsed > 0:
            sample_speed = max(0, current - self.last_sample_bytes) / elapsed
            self.speed = sample_speed if not self.speed else self.speed * 0.7 + sample_speed * 0.3
        self.last_sample_at = now
        self.last_sample_bytes = current

        complete = total > 0 and current >= total
        if not force and not complete and now - self.last_render_at < self.interval:
            return None
        self.last_render_at = now

        if total:
            fraction = min(1.0, current / total)
            percent = fraction * 100
            filled = int(fraction * 12)
            bar = "█" * filled + "░" * (12 - filled)
            details = f"{bar}  <b>{percent:.1f}%</b>\n"
            details += f"{format_bytes(current)} / {format_bytes(total)}"
            if self.speed > 0 and not complete:
                details += f" · {format_bytes(int(self.speed))}/s · ETA {format_duration((total - current) / self.speed)}"
        else:
            details = f"{format_bytes(current)} transferred"
            if self.speed > 0:
                details += f" · {format_bytes(int(self.speed))}/s"

        heading = f"{self.phase} <b>{self.title[:100]}</b>"
        if self.quality:
            heading += f" · <b>{self.quality[:24]}</b>"
        if complete:
            details += "\n✅ Transfer complete"
        return f"{heading}\n{details}"
