"""Owner-only Telegram handlers for WatchHentai series discovery and downloads."""
from __future__ import annotations

import re
import secrets
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from pcm.bot.access import owner_filter
from pcm.bot.ytdlp_handler import register_ytdlp_handler
from pcm.core.config import Settings
from pcm.providers.watchhentai_resolver import ProviderResolveError, WatchHentaiResolver
from pcm.providers.watchhentai_series import discover_episodes
from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.transfers.downloader import download_media

_URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_EPISODE_PATH = re.compile(r"/videos/[^/]+/?$", re.IGNORECASE)
_MAX_TELEGRAM_BYTES = 2 * 1024 * 1024 * 1024


def register_handlers(app: Client, owner_id: int) -> None:
    """Register private owner-only commands and media selection callbacks."""
    register_ytdlp_handler(app, owner_id)
    owner = owner_filter(owner_id)
    private_owner = filters.private & owner
    resolver = WatchHentaiResolver()
    choices: dict[str, dict] = {}
    menus: dict[str, dict] = {}

    @app.on_message(filters.command("start") & private_owner)
    async def start_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM — Private Content Manager\n\n"
            "Send a WatchHentai episode URL. PCM will find related episodes, "
            "then let you download one episode or the full discovered list.\n"
            "Only the configured owner can use this bot."
        )

    @app.on_message(filters.command("help") & private_owner)
    async def help_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM commands:\n"
            "/start — status and usage\n"
            "/help — this message\n"
            "/resolve URL — discover related episodes\n\n"
            "Send a WatchHentai episode URL to list episodes. Choose Download single "
            "to select one episode and quality, or Download all to process the list sequentially."
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

        status = await message.reply_text("🔎 Finding episodes related to this page…")
        try:
            episodes = await discover_episodes(url)
            if not episodes:
                raise ProviderResolveError("No episode links were found.")
            # Resolve the requested episode as an early check that its player works.
            first_result = await resolver.resolve(episodes[0]["url"])
            first_title = first_result["page"].get("title") or episodes[0]["title"]
            episodes[0]["title"] = first_title
            token = secrets.token_urlsafe(8)
            menus[token] = {"episodes": episodes, "series_title": first_title}
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("⬇ Download single episode", callback_data=f"pcm_menu:{token}"),
                InlineKeyboardButton(f"⬇ Download all ({len(episodes)})", callback_data=f"pcm_all:{token}"),
            ]])
            episode_lines = "\n".join(
                f"{i + 1}. {episode['title'][:90]}" for i, episode in enumerate(episodes[:20])
            )
            if len(episodes) > 20:
                episode_lines += f"\n… plus {len(episodes) - 20} more"
            await status.edit_text(
                f"🎬 <b>{first_title}</b>\n\n"
                f"Found <b>{len(episodes)}</b> episode link(s):\n{episode_lines}\n\n"
                "Choose what to download:",
                reply_markup=keyboard,
            )
        except Exception as exc:
            await status.edit_text(f"❌ Could not discover episodes: {str(exc)[:700]}")

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
            "Episode discovery is currently enabled for WatchHentai episode URLs."
        )

    @app.on_callback_query(filters.regex(r"^pcm_menu:") & owner)
    async def single_menu_callback(_: Client, query) -> None:
        token = query.data.split(":", 1)[1]
        menu = menus.get(token)
        if not query.message or not menu:
            await query.answer("This episode list expired. Send the URL again.", show_alert=True)
            return
        await query.answer()
        buttons = []
        for index, episode in enumerate(menu["episodes"]):
            buttons.append(InlineKeyboardButton(
                f"{index + 1}. {episode['title'][:45]}",
                callback_data=f"pcm_one:{token}:{index}",
            ))
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        await query.message.reply_text(
            "Choose one episode to download:",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    @app.on_callback_query(filters.regex(r"^pcm_one:") & owner)
    async def single_episode_callback(_: Client, query) -> None:
        if not query.message:
            await query.answer()
            return
        try:
            _, token, raw_index = query.data.split(":", 2)
            episode = menus[token]["episodes"][int(raw_index)]
        except (KeyError, ValueError, IndexError):
            await query.answer("Episode list expired. Send the URL again.", show_alert=True)
            return
        await query.answer("Resolving episode…")
        status = await query.message.reply_text(f"🔎 Resolving {episode['title'][:100]}…")
        try:
            result = await resolver.resolve(episode["url"])
            title = result["page"].get("title") or episode["title"]
            buttons = []
            for source_index, source in enumerate(result["sources"][:8]):
                choice_token = secrets.token_urlsafe(8)
                choices[choice_token] = {
                    "url": episode["url"], "label": source["label"],
                    "title": title, "source_index": source_index,
                }
                buttons.append(InlineKeyboardButton(
                    f"⬇ {source['label']}", callback_data=f"pcm_dl:{choice_token}",
                ))
            await status.edit_text(
                f"🎬 <b>{title}</b>\nChoose quality:",
                reply_markup=InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)]),
            )
        except Exception as exc:
            await status.edit_text(f"❌ Could not resolve episode: {str(exc)[:600]}")

    async def download_one(chat_id: int, status, episode_url: str, title: str, requested_label: str | None = None) -> None:
        output: Path | None = None
        try:
            result = await resolver.resolve(episode_url)
            sources = result["sources"]
            source = None
            if requested_label:
                source = next((item for item in sources if item["label"].lower() == requested_label.lower()), None)
            if source is None:
                def quality_rank(item: dict) -> int:
                    match = re.search(r"(\d{3,4})\s*p?", item["label"].lower())
                    return int(match.group(1)) if match else 0
                source = max(sources, key=quality_rank)
            settings = Settings.from_env(require_secrets=False)
            settings.temp_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._")[:70] or "episode"
            output = settings.temp_dir / f"{safe_title}-{secrets.token_hex(4)}.mp4"
            max_bytes = min(settings.max_file_size_mb * 1024 * 1024, _MAX_TELEGRAM_BYTES)
            last_update = 0.0

            async def progress(current: int, total: int) -> None:
                nonlocal last_update
                now = time.monotonic()
                if now - last_update < 4 and (not total or current < total):
                    return
                last_update = now
                if total:
                    await status.edit_text(
                        f"📥 <b>{title[:100]}</b> — {source['label']}\n"
                        f"{current / 1048576:.1f} / {total / 1048576:.1f} MiB "
                        f"({current * 100 / total:.1f}%)"
                    )
                else:
                    await status.edit_text(
                        f"📥 <b>{title[:100]}</b> — {source['label']}\n{current / 1048576:.1f} MiB"
                    )

            await download_media(
                source["url"], output, referer=episode_url,
                max_bytes=max_bytes, timeout=settings.request_timeout_seconds,
                progress=progress,
            )
            if output.stat().st_size > _MAX_TELEGRAM_BYTES:
                raise RuntimeError("File exceeds Telegram's 2 GiB upload limit.")
            await status.edit_text(f"📤 Uploading <b>{title[:100]}</b> to this chat…")
            await app.send_video(
                chat_id=chat_id, video=str(output),
                caption=f"🎬 <b>{title[:900]}</b>\n🎥 Quality: <b>{source['label']}</b>",
                supports_streaming=True,
            )
            await status.edit_text(f"✅ Completed: {title[:150]}")
        finally:
            if output:
                output.unlink(missing_ok=True)

    @app.on_callback_query(filters.regex(r"^pcm_all:") & owner)
    async def all_episodes_callback(_: Client, query) -> None:
        if not query.message or getattr(query.message.chat.type, "value", str(query.message.chat.type)) != "private":
            await query.answer("Private chat only.", show_alert=True)
            return
        token = query.data.split(":", 1)[1]
        menu = menus.get(token)
        if not menu:
            await query.answer("Episode list expired. Send the URL again.", show_alert=True)
            return
        await query.answer("Starting sequential downloads…")
        episodes = menu["episodes"]
        summary = await query.message.reply_text(f"📚 Starting {len(episodes)} episode(s), one at a time…")
        succeeded = 0
        failed = []
        for index, episode in enumerate(episodes, 1):
            await summary.edit_text(f"📚 Episode {index}/{len(episodes)}\n{episode['title'][:150]}\nPreparing…")
            try:
                await download_one(query.message.chat.id, summary, episode["url"], episode["title"])
                succeeded += 1
            except Exception as exc:
                failed.append(f"{episode['title'][:80]}: {str(exc)[:120]}")
                await summary.edit_text(f"⚠️ Episode {index}/{len(episodes)} failed; continuing…")
        text = f"🏁 Series download finished.\n✅ Completed: {succeeded}/{len(episodes)}"
        if failed:
            text += "\n\n❌ Failed:\n" + "\n".join(failed[:10])
        await summary.edit_text(text)

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
        await query.answer("Starting download…")
        status = await query.message.reply_text(f"📥 Preparing {choice['title'][:100]}…")
        try:
            await download_one(
                query.message.chat.id, status, choice["url"],
                choice["title"], choice["label"],
            )
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {str(exc)[:700]}")
        finally:
            choices.pop(token, None)
