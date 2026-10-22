"""Small Telegram handlers; job execution stays outside this module."""

import re

from pyrogram import Client, filters
from pyrogram.types import Message

from pcm.bot.access import owner_filter
from pcm.resolver.url_model import URLValidationError, parse_url

_URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


def register_handlers(app: Client, owner_id: int) -> None:
    """Register the initial private, owner-only command and URL handlers."""
    owner = owner_filter(owner_id)
    private_owner = filters.private & owner

    @app.on_message(filters.command("start") & private_owner)
    async def start_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM — Private Content Manager\n\n"
            "The Python foundation is running. URL validation is available; "
            "download and upload execution is still under development.\n\n"
            "Use /help to see available commands."
        )

    @app.on_message(filters.command("help") & private_owner)
    async def help_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM starter commands:\n"
            "/start — project status\n"
            "/help — this message\n\n"
            "Send a URL to validate it. Job queue and transfer commands "
            "will be enabled in later milestones."
        )

    @app.on_message(filters.text & private_owner)
    async def url_handler(_: Client, message: Message) -> None:
        text = message.text or ""
        urls = _URL_PATTERN.findall(text)
        if not urls:
            return
        lines = []
        for raw_url in urls[:10]:
            candidate = raw_url.rstrip(".,;!?)")
            try:
                parsed = parse_url(candidate)
            except URLValidationError as exc:
                lines.append(f"Rejected: {candidate[:120]}\nReason: {exc}")
            else:
                lines.append(f"Validated: {parsed.hostname} ({parsed.scheme.upper()})")
        if len(urls) > 10:
            lines.append("Only the first 10 URLs were checked.")
        await message.reply_text(
            "URL validation results (no download started):\n\n" + "\n\n".join(lines)
        )
