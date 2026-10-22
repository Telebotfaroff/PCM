"""Owner-only Telegram handlers for URL validation and WatchHentai downloads."""
from __future__ import annotations

import re
import secrets
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from pcm.bot.access import owner_filter
from pcm.core.config import Settings
from pcm.providers.watchhentai_resolver import ProviderResolveError, WatchHentaiResolver
from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.transfers.downloader import download_media

_URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_EPISODE_PATH = re.compile(r"/videos/[^/]+/?$", re.IGNORECASE)
_MAX_TELEGRAM_BYTES = 2 * 1024 * 1024 * 1024


def register_handlers(app: Client, owner_id: int) -> None:
    """Register private owner-only commands and media selection callbacks."""
    owner = owner_filter(owner_id)
    private_owner = filters.private & owner
    resolver = WatchHentaiResolver()
    choices: dict[str, dict[str, str]] = {}

    @app.on_message(filters.command("start") & private_owner)
    async def start_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM — Private Content Manager\n\n"
            "Send a WatchHentai episode URL to resolve available qualities and download it.\n"
            "Only the configured owner can use this bot."
        )

    @app.on_message(filters.command("help") & private_owner)
    async def help_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM commands:\n"
            "/start — status and usage\n"
            "/help — this message\n\n"
            "Send a WatchHentai episode URL. PCM will inspect its player page, "
            "show available qualities, download the selected source, and send the video here."
        )

    @app.on_message(filters.regex(r"^/resolve(?:\s|$)") & private_owner)
    async def resolve_command(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /resolve https://watchhentai.net/videos/episode-slug/")
            return
        await resolve_episode(message, parts[1].strip())

    async def resolve_episode(message: Message, url: str) -> None:
        try:
            parsed = parse_url(url)
            if parsed.hostname.lower() not in {"watchhentai.net", "www.watchhentai.net"}:
                raise ProviderResolveError("Only WatchHentai episode URLs are supported.")
            if not _EPISODE_PATH.search(parsed.normalized.split("?", 1)[0]):
                raise ProviderResolveError("Send an episode URL under /videos/...")
        except (URLValidationError, ProviderResolveError) as exc:
            await message.reply_text(f"❌ {exc}")
            return

        status = await message.reply_text("🔎 Loading episode page and resolving player sources…")
        try:
            result = await resolver.resolve(url)
            sources = result["sources"]
            title = result["page"].get("title") or "WatchHentai episode"
            buttons = []
            for source in sources[:8]:
                token = secrets.token_urlsafe(8)
                choices[token] = {
                    "url": url,
                    "label": source["label"],
                    "title": title,
                }
                buttons.append(
                    InlineKeyboardButton(
                        f"⬇ {source['label']}",
                        callback_data=f"pcm_dl:{token}",
                    )
                )
            if not buttons:
                raise ProviderResolveError("No downloadable qualities were found.")
            await status.edit_text(
                f"🎬 <b>{title}</b>\n\n"
                f"Available qualities: {', '.join(s['label'] for s in sources)}\n"
                "Choose a quality to download:",
                reply_markup=InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)]),
            )
        except Exception as exc:
            await status.edit_text(f"❌ Could not resolve media: {str(exc)[:700]}")

    @app.on_message(filters.text & private_owner, group=1)
    async def url_handler(_: Client, message: Message) -> None:
        text = message.text or ""
        if text.startswith("/"):
            return
        urls = _URL_PATTERN.findall(text)
        if not urls:
            return
        candidate = urls[0].rstrip(".,;!?)")
        try:
            parsed = parse_url(candidate)
        except URLValidationError as exc:
            await message.reply_text(f"❌ URL rejected: {exc}")
            return
        if (
            parsed.hostname.lower() in {"watchhentai.net", "www.watchhentai.net"}
            and _EPISODE_PATH.search(parsed.normalized.split("?", 1)[0])
        ):
            await resolve_episode(message, candidate)
            return
        await message.reply_text(
            f"Validated: {parsed.hostname} ({parsed.scheme.upper()}).\n"
            "Live media resolution is currently enabled for WatchHentai episode URLs."
        )

    @app.on_callback_query(filters.regex(r"^pcm_dl:") & owner)
    async def download_callback(_: Client, query) -> None:
        if not query.message or getattr(query.message.chat.type, "value", str(query.message.chat.type)) != "private":
            await query.answer("Private chat only.", show_alert=True)
            return
        token = query.data.split(":", 1)[1]
        choice = choices.get(token)
        if not choice:
            await query.answer("This selection expired. Send the episode URL again.", show_alert=True)
            return
        await query.answer("Preparing download…")
        status = await query.message.reply_text(
            f"📥 Resolving {choice['label']} again before download…"
        )
        output: Path | None = None
        try:
            result = await resolver.resolve(choice["url"])
            source = next(
                (item for item in result["sources"] if item["label"].lower() == choice["label"].lower()),
                None,
            )
            if source is None:
                raise ProviderResolveError(
                    f"Quality {choice['label']} is no longer available. Send the episode URL again."
                )
            settings = Settings.from_env(require_secrets=False)
            settings.temp_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", choice["title"]).strip("._")[:70] or "episode"
            output = settings.temp_dir / f"{safe_title}-{secrets.token_hex(4)}.mp4"
            max_bytes = min(settings.max_file_size_mb * 1024 * 1024, _MAX_TELEGRAM_BYTES)
            last_update = 0.0

            async def progress(current: int, total: int) -> None:
                nonlocal last_update
                now = time.monotonic()
                if now - last_update < 4 and (not total or current < total):
                    return
                last_update = now
                percent = f"{current * 100 / total:.1f}%" if total else "size unknown"
                await status.edit_text(
                    f"📥 <b>Downloading {choice['label']}</b>\n"
                    f"{current / 1048576:.1f} MiB / {total / 1048576:.1f} MiB ({percent})"
                    if total else f"📥 <b>Downloading {choice['label']}</b>\n{current / 1048576:.1f} MiB"
                )

            await download_media(
                source["url"], output, referer=choice["url"],
                max_bytes=max_bytes, timeout=settings.request_timeout_seconds,
                progress=progress,
            )
            if output.stat().st_size > _MAX_TELEGRAM_BYTES:
                raise RuntimeError("File exceeds Telegram's 2 GiB upload limit.")
            await status.edit_text("📤 Download complete. Uploading video to this chat…")
            await app.send_video(
                chat_id=query.message.chat.id,
                video=str(output),
                caption=f"🎬 <b>{choice['title']}</b>\n🎥 Quality: <b>{choice['label']}</b>",
                supports_streaming=True,
            )
            await status.edit_text("✅ Download and Telegram upload completed.")
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {str(exc)[:700]}")
        finally:
            if output:
                output.unlink(missing_ok=True)
            choices.pop(token, None)
