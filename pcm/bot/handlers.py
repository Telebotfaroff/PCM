"""Owner-only Telegram handlers routed through the provider registry."""
from __future__ import annotations

import asyncio
import os
import re
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from pcm.bot.access import owner_filter
from pcm.bot.persistent_settings import load_preferences, save_preferences
from pcm.bot.progress import TransferProgress
from pcm.bot.ytdlp_handler import register_ytdlp_handler
from pcm.core.config import Settings
from pcm.jobs.repository import JobRepository
from pcm.providers.registry import get_provider, get_provider_by_name
from pcm.resolver.url_model import URLValidationError, parse_url
from pcm.transfers.downloader import download_media
from pcm.transfers.gofile import upload_file as gofile_upload
from pcm.transfers.media_metadata import prepare_video_metadata

_URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_MAX_TELEGRAM_BYTES = 2 * 1024 * 1024 * 1024


def register_handlers(app: Client, owner_id: int) -> Callable[[dict], Awaitable[None]]:
    """Register private owner-only commands and media selection callbacks."""
    register_ytdlp_handler(app, owner_id)
    jobs = JobRepository()

    # Diagnostic handler runs before owner-only handlers and never logs message contents.
    @app.on_message(filters.private, group=-1)
    async def private_message_diagnostic(_: Client, message: Message) -> None:
        sender_id = message.from_user.id if message.from_user else None
        is_owner = sender_id == owner_id
        text = message.text or message.caption or ""
        command = text.split(maxsplit=1)[0] if text.startswith("/") else "<non-command>"
        import logging
        logging.getLogger("pcm.telegram").info(
            "Incoming private message: sender_id=%s owner_match=%s command=%s",
            sender_id,
            is_owner,
            command[:40],
        )

    owner = owner_filter(owner_id)
    private_owner = filters.private & owner
    choices: dict[str, dict] = {}
    menus: dict[str, dict] = {}
    preferences = {"auto_quality": True, "delete_menu": True, "dump_enabled": False, "dump_channel": None, "destinations": ["telegram"], "gofile_token": "", "gofile_guest": False, "gofile_folder_id": ""}
    settings_loaded = False
    awaiting_dump_channel: set[int] = set()

    async def ensure_settings_loaded() -> None:
        nonlocal settings_loaded
        if not settings_loaded:
            saved = await load_preferences(owner_id)
            preferences.update(saved)
            settings_loaded = True

    async def persist_settings() -> None:
        await save_preferences(owner_id, preferences)


    @app.on_message(filters.command("gofile") & private_owner)
    async def gofile_command(_: Client, message: Message) -> None:
        await ensure_settings_loaded()
        parts = (message.text or "").split(maxsplit=2)
        action = parts[1].lower() if len(parts) > 1 else "status"
        if action == "status":
            token_set = not preferences.get("gofile_guest", False) and bool(str(preferences.get("gofile_token") or os.getenv("GOFILE_TOKEN", "")).strip())
            destinations = ", ".join(preferences.get("destinations") or ["telegram"])
            mode = "account token" if token_set else "guest upload"
            await message.reply_text(
                "☁️ <b>GoFile settings</b>\n"
                f"Mode: {mode}\n"
                f"Default destinations: {destinations}\n\n"
                "Commands:\n/gofile guest — use guest uploads\n"
                "/gofile token YOUR_API_KEY — save account token\n"
                "/gofile clear — remove saved token\n"
                "/dest telegram | gofile | both"
            )
            return
        if action == "token":
            if len(parts) < 3 or not parts[2].strip():
                await message.reply_text("Usage: /gofile token YOUR_API_KEY")
                return
            token = parts[2].strip()
            try:
                await message.delete()
            except Exception:
                pass
            if len(token) > 500 or any(ch.isspace() for ch in token):
                await message.reply_text("❌ That token format is not valid.")
                return
            previous_token = preferences.get("gofile_token", "")
            previous_guest = preferences.get("gofile_guest", False)
            preferences["gofile_token"] = token
            preferences["gofile_guest"] = False
            try:
                await persist_settings()
            except Exception as exc:
                preferences["gofile_token"] = previous_token
                preferences["gofile_guest"] = previous_guest
                await message.reply_text(f"❌ Could not save GoFile settings: {str(exc)[:200]}")
                return
            await message.reply_text("✅ GoFile account token saved. I will not display it again.")
            return
        if action in {"guest", "clear"}:
            preferences["gofile_token"] = ""
            preferences["gofile_guest"] = True
            try:
                await persist_settings()
            except Exception as exc:
                await message.reply_text(f"❌ Could not save settings: {str(exc)[:200]}")
                return
            await message.reply_text("✅ GoFile token cleared. Guest uploads will be used.")
            return
        await message.reply_text("Usage: /gofile [status|guest|clear|token YOUR_API_KEY]")

    @app.on_message(filters.command("dest") & private_owner)
    async def destination_command(_: Client, message: Message) -> None:
        await ensure_settings_loaded()
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            current = ", ".join(preferences.get("destinations") or ["telegram"])
            await message.reply_text(
                f"Current default destination(s): {current}\n"
                "Set with /dest telegram, /dest gofile, or /dest both"
            )
            return
        target = parts[1].strip().lower()
        mapping = {"telegram": ["telegram"], "gofile": ["gofile"], "both": ["telegram", "gofile"]}
        if target not in mapping:
            await message.reply_text("Use /dest telegram, /dest gofile, or /dest both")
            return
        preferences["destinations"] = mapping[target]
        try:
            await persist_settings()
        except Exception as exc:
            await message.reply_text(f"❌ Could not save destination: {str(exc)[:200]}")
            return
        await message.reply_text(f"✅ Default destination set to: {', '.join(mapping[target])}")

    @app.on_message(filters.command("me") & private_owner)
    async def me_handler(_: Client, message: Message) -> None:
        try:
            await ensure_settings_loaded()
        except Exception as exc:
            await message.reply_text(f"❌ Could not load settings from database: {str(exc)[:300]}")
            return
        await message.reply_text(
            "⚙️ <b>PCM Control Panel</b>\\nChoose a setting:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🏆 Auto highest quality: {'ON' if preferences['auto_quality'] else 'OFF'}", callback_data="pcm_me:quality")],
                [InlineKeyboardButton(f"🗑 Delete menu on download: {'ON' if preferences['delete_menu'] else 'OFF'}", callback_data="pcm_me:delete")],
                [InlineKeyboardButton(f"📦 Dump channel upload: {'ON' if preferences['dump_enabled'] else 'OFF'}", callback_data="pcm_me:dump")],
                [InlineKeyboardButton("⚙️ Set dump channel", callback_data="pcm_me:setdump")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="pcm_me:refresh")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^pcm_me:(quality|delete|dump|setdump|refresh)$") & owner)
    async def me_settings_callback(_: Client, query) -> None:
        if not query.message:
            await query.answer()
            return
        try:
            await ensure_settings_loaded()
        except Exception as exc:
            await query.answer(f"Database error: {str(exc)[:180]}", show_alert=True)
            return
        action = query.data.split(":", 1)[1]
        if action == "quality":
            preferences["auto_quality"] = not preferences["auto_quality"]
        elif action == "delete":
            preferences["delete_menu"] = not preferences["delete_menu"]
        elif action == "dump":
            preferences["dump_enabled"] = not preferences["dump_enabled"]
        elif action == "setdump":
            awaiting_dump_channel.add(query.from_user.id)
            await query.answer("Send the channel @username or numeric ID in this chat.", show_alert=True)
            await query.message.reply_text("📦 Send the dump channel @username or numeric ID. The bot must be an administrator there.")
            return
        try:
            await persist_settings()
        except Exception as exc:
            await query.answer(f"Could not save settings: {str(exc)[:180]}", show_alert=True)
            return
        await query.answer("Settings updated." if action != "refresh" else "Settings refreshed.")
        await query.message.edit_text(
            "⚙️ <b>PCM Control Panel</b>\\nChoose a setting:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🏆 Auto highest quality: {'ON' if preferences['auto_quality'] else 'OFF'}", callback_data="pcm_me:quality")],
                [InlineKeyboardButton(f"🗑 Delete menu on download: {'ON' if preferences['delete_menu'] else 'OFF'}", callback_data="pcm_me:delete")],
                [InlineKeyboardButton(f"📦 Dump channel upload: {'ON' if preferences['dump_enabled'] else 'OFF'}", callback_data="pcm_me:dump")],
                [InlineKeyboardButton("⚙️ Set dump channel", callback_data="pcm_me:setdump")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="pcm_me:refresh")],
            ]),
        )

    # Run after URL processing; a broad text handler in the same group would swallow URL messages.
    @app.on_message(filters.text & private_owner, group=2)
    async def dump_channel_setup(_: Client, message: Message) -> None:
        if message.from_user and message.from_user.id in awaiting_dump_channel:
            value = (message.text or "").strip()
            if value.startswith("/") or not (value.startswith("@") or value.lstrip("-").isdigit()):
                await message.reply_text("Send a channel @username or numeric channel ID, for example @my_dump_channel or -1001234567890.")
                return
            try:
                chat = await app.get_chat(value)
                me = await app.get_chat_member(chat.id, "me")
                status = str(getattr(me, "status", "")).lower()
                if "administrator" not in status and "owner" not in status and "creator" not in status:
                    await message.reply_text("❌ Make the bot an administrator in that channel, then send the channel again.")
                    return
                await ensure_settings_loaded()
                preferences["dump_channel"] = str(chat.id)
                await persist_settings()
                awaiting_dump_channel.discard(message.from_user.id)
                await message.reply_text(f"✅ Dump channel saved: <b>{chat.title or chat.id}</b>\\nEnable it from /me when you're ready.")
            except Exception as exc:
                await message.reply_text(f"❌ Could not access that channel: {str(exc)[:300]}. Check the ID and bot admin permissions.")


    @app.on_message(filters.command("jobs") & private_owner)
    async def jobs_command(_: Client, message: Message) -> None:
        try:
            rows = await jobs.list_jobs(owner_id, limit=10)
        except Exception as exc:
            await message.reply_text(f"❌ Could not read job queue: {str(exc)[:250]}")
            return
        if not rows:
            await message.reply_text("📭 No saved jobs yet.")
            return
        lines = ["📋 <b>Recent PCM jobs</b>"]
        for row in rows:
            lines.append(
                f"#{row['id']} · <b>{row['status']}</b> · attempt {row['attempts']}/{row['max_attempts']}\n"
                f"{str(row['source_url'])[:110]}"
            )
        lines.append("\nCommands: /pause ID · /resume ID · /cancel ID · /retry ID")
        await message.reply_text("\n\n".join(lines))

    async def job_action(message: Message, action: str) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[1].isdigit():
            await message.reply_text(f"Usage: /{action} JOB_ID")
            return
        try:
            row = await jobs.request_action(owner_id, int(parts[1]), action)
            if row is None:
                await message.reply_text("❌ Job not found.")
            else:
                await message.reply_text(f"✅ Job #{row['id']}: {row['status']}")
        except Exception as exc:
            await message.reply_text(f"❌ Cannot {action} job: {str(exc)[:250]}")

    @app.on_message(filters.command("pause") & private_owner)
    async def pause_command(_: Client, message: Message) -> None:
        await job_action(message, "pause")

    @app.on_message(filters.command("resume") & private_owner)
    async def resume_command(_: Client, message: Message) -> None:
        await job_action(message, "resume")

    @app.on_message(filters.command("cancel") & private_owner)
    async def cancel_command(_: Client, message: Message) -> None:
        await job_action(message, "cancel")

    @app.on_message(filters.command("retry") & private_owner)
    async def retry_command(_: Client, message: Message) -> None:
        await job_action(message, "retry")

    @app.on_message(filters.command("start") & private_owner)
    async def start_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM — Private Content Manager\n\n"
            "Send an episode URL to download only that episode, or a series URL to choose one episode "
            "or download the whole series.\n"
            "Only the configured owner can use this bot."
        )

    @app.on_message(filters.command("help") & private_owner)
    async def help_handler(_: Client, message: Message) -> None:
        await message.reply_text(
            "PCM commands:\n"
            "/start — status and usage\n"
            "/help — this message\n"
            "/resolve URL — discover related episodes\n"
            "/jobs — show recent persistent jobs\n"
            "/pause ID, /resume ID, /cancel ID, /retry ID — control jobs\n"
            "/dest telegram|gofile|both — choose upload destination\n"
            "/gofile — configure guest/account-token uploads\n\n"
            "/ytdlp URL — download a supported video with yt-dlp\n"
            "Send an episode URL to download only that episode. Send a series URL to list its episodes and choose "
            "one episode or Download series to process the whole list sequentially."
        )

    @app.on_message(filters.regex(r"^/resolve(?:\s|$)") & private_owner)
    async def resolve_command(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /resolve https://watchhentai.net/series/series-slug/ or /videos/episode-slug/")
            return
        await resolve_episode(message, parts[1].strip())

    async def resolve_episode(message: Message, url: str) -> None:
        try:
            parsed = parse_url(url)
            provider = get_provider(parsed.normalized)
            if provider is None:
                raise ValueError("No provider is registered for this URL.")
            page_type = provider.classify_url(parsed.normalized)
            if page_type not in {"series", "episode"}:
                raise ValueError(
                    f"{provider.display_name} URL must be a supported episode or series page."
                )
        except (URLValidationError, ValueError) as exc:
            await message.reply_text(f"❌ {exc}")
            return

        status = await message.reply_text(
            "🔎 Reading the series page…" if page_type == "series" else "🔎 Resolving this episode only…"
        )
        try:
            if page_type == "episode":
                # An episode URL means exactly that episode. Never discover or enqueue siblings.
                result = await provider.resolve(parsed.normalized)
                title = result["page"].get("title") or "Episode"
                episodes = [{"url": parsed.normalized, "title": title}]
            else:
                episodes = await provider.discover_episodes(parsed.normalized)
                if not episodes:
                    raise ValueError("No episode links were found on this series page.")
                # Resolve one episode to confirm the series entries are downloadable.
                first_result = await provider.resolve(episodes[0]["url"])
                title = first_result["page"].get("title") or episodes[0]["title"]
                episodes[0]["title"] = title

            token = secrets.token_urlsafe(8)
            menus[token] = {
                "episodes": episodes,
                "series_title": title,
                "is_series": page_type == "series",
                "provider": provider.name,
                "source_url": parsed.normalized,
            }
            buttons = [InlineKeyboardButton(
                "⬇ Download episode" if page_type == "episode" else "⬇ Choose single episode",
                callback_data=f"pcm_menu:{token}",
            )]
            if page_type == "series":
                buttons.append(InlineKeyboardButton(
                    f"📚 Download series ({len(episodes)})",
                    callback_data=f"pcm_all:{token}",
                ))
            keyboard = InlineKeyboardMarkup([buttons])
            episode_lines = "\n".join(
                f"{i + 1}. {episode['title'][:90]}" for i, episode in enumerate(episodes[:20])
            )
            if len(episodes) > 20:
                episode_lines += f"\n… plus {len(episodes) - 20} more"
            heading = "Series found" if page_type == "series" else "Episode ready"
            await status.edit_text(
                f"🎬 <b>{title}</b>\n\n"
                f"{heading}: <b>{len(episodes)}</b> episode link(s)\n{episode_lines}\n\n"
                + ("Choose one episode or download the whole series:" if page_type == "series"
                   else "Only the episode URL you sent will be downloaded."),
                reply_markup=keyboard,
            )
        except Exception as exc:
            await status.edit_text(f"❌ Could not process URL: {str(exc)[:700]}")

    @app.on_message((filters.text | filters.caption) & private_owner, group=1)
    async def url_handler(_: Client, message: Message) -> None:
        import logging
        logger = logging.getLogger("pcm.telegram.url")
        text = message.text or message.caption or ""
        if text.startswith("/"):
            return
        urls = _URL_PATTERN.findall(text)
        logger.info("URL handler received message: text_length=%s url_count=%s", len(text), len(urls))
        if not urls:
            return
        candidate = urls[0].rstrip(".,;!?)")
        logger.info("Processing URL host/path only: %s", candidate.split("?", 1)[0][:180])
        try:
            await ensure_settings_loaded()
            parsed = parse_url(candidate)
        except URLValidationError as exc:
            await message.reply_text(f"❌ URL rejected: {exc}")
            return
        provider = get_provider(parsed.normalized)
        page_type = provider.classify_url(parsed.normalized) if provider else None
        logger.info("URL classified: host=%s provider=%s page_type=%s", parsed.hostname, provider.name if provider else None, page_type)
        if provider and provider.classify_url(parsed.normalized) == "episode":
            if not preferences["auto_quality"]:
                await resolve_episode(message, candidate)
                return
            # A directly sent episode URL starts immediately at the highest available quality.
            status = await message.reply_text("🔎 Resolving episode and selecting the highest quality…")
            try:
                result = await provider.resolve(parsed.normalized)
                title = result.get("page", {}).get("title") or "Episode"
                if not result.get("sources"):
                    raise ValueError("No downloadable video sources were found.")
                await status.edit_text(
                    f"🎬 <b>{title[:120]}</b>\\n"
                    "🏆 Highest available quality selected automatically."
                )
                row = await jobs.enqueue(
                    owner_id, parsed.normalized, job_type="provider_episode",
                    destinations=list(preferences.get("destinations") or ["telegram"]),
                    options={
                        "chat_id": message.chat.id, "provider": provider.name, "title": title,
                        "destinations": list(preferences.get("destinations") or ["telegram"]),
                    },
                )
                await status.edit_text(
                    f"📥 Queued job <b>#{row['id']}</b>\n{title[:140]}\n"
                    "Use /jobs to check status or /cancel ID to cancel."
                )
            except Exception as exc:
                await status.edit_text(f"❌ Could not download episode: {str(exc)[:600]}")
            return
        if provider and provider.classify_url(parsed.normalized) == "series":
            await resolve_episode(message, candidate)
            return
        await message.reply_text(
            f"Validated: {parsed.hostname} ({parsed.scheme.upper()}).\n"
            + (
                f"{provider.display_name} recognizes this host, but this URL is not a supported page."
                if provider
                else "No installed provider supports this URL yet."
            )
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
            provider = get_provider_by_name(menus[token]["provider"])
            if provider is None:
                raise RuntimeError("The provider for this menu is no longer registered.")
            result = await provider.resolve(episode["url"])
            title = result["page"].get("title") or episode["title"]
            buttons = []
            for source_index, source in enumerate(result["sources"][:8]):
                choice_token = secrets.token_urlsafe(8)
                choices[choice_token] = {
                    "url": episode["url"], "label": source["label"],
                    "title": title, "source_index": source_index,
                    "provider": provider.name,
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

    async def download_one(
        chat_id: int,
        status,
        provider_name: str,
        episode_url: str,
        title: str,
        requested_label: str | None = None,
        destinations: list[str] | None = None,
    ) -> None:
        output: Path | None = None
        thumbnail: Path | None = None
        try:
            provider = get_provider_by_name(provider_name)
            if provider is None:
                raise RuntimeError(f"Provider is not registered: {provider_name}")
            result = await provider.resolve(episode_url)
            targets = list(destinations or preferences.get("destinations") or ["telegram"])
            if not targets or any(target not in {"telegram", "gofile"} for target in targets):
                raise ValueError("Invalid upload destination settings.")
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
            configured_limit = settings.max_file_size_mb * 1024 * 1024
            max_bytes = min(configured_limit, _MAX_TELEGRAM_BYTES) if "telegram" in targets else configured_limit
            download_meter = TransferProgress(
                title, "📥 Downloading", quality=source["label"]
            )

            async def download_progress(current: int, total: int) -> None:
                text = download_meter.render(current, total)
                if text:
                    try:
                        await status.edit_text(text)
                    except Exception:
                        # A status-message edit must never interrupt a valid transfer.
                        pass

            await download_media(
                source["url"], output, referer=episode_url,
                max_bytes=max_bytes, timeout=settings.request_timeout_seconds,
                progress=download_progress,
            )
            file_size = output.stat().st_size
            if "telegram" in targets and file_size > _MAX_TELEGRAM_BYTES:
                raise RuntimeError("File exceeds Telegram's 2 GiB upload limit. Choose GoFile-only with /dest gofile.")

            await status.edit_text(
                f"✅ Download complete: <b>{title[:100]}</b>\n"
                f"📦 Size: <b>{file_size / 1048576:.2f} MiB</b>\n"
                f"📤 Preparing upload to: {', '.join(targets)}…"
            )
            metadata = await prepare_video_metadata(output)
            thumbnail = metadata.thumbnail
            if not metadata.duration or not metadata.width or not metadata.height:
                await status.edit_text(
                    f"⚠️ Could not read complete video metadata for <b>{title[:100]}</b>. "
                    "Uploading with available metadata…"
                )
            completed: list[str] = []
            failures: list[str] = []
            if "telegram" in targets:
                upload_meter = TransferProgress(
                    title, "📤 Telegram uploading", quality=source["label"]
                )

                async def upload_progress(current: int, total: int, *_) -> None:
                    text = upload_meter.render(current, total)
                    if text:
                        try:
                            await status.edit_text(text)
                        except Exception:
                            pass

                try:
                    await app.send_video(
                        chat_id=chat_id, video=str(output),
                        caption=f"🎬 <b>{title[:900]}</b>\n🎥 Quality: <b>{source['label']}</b>",
                        supports_streaming=True,
                        duration=metadata.duration,
                        width=metadata.width,
                        height=metadata.height,
                        thumb=str(thumbnail) if thumbnail else None,
                        progress=upload_progress,
                    )
                    completed.append("Telegram")
                    if preferences["dump_enabled"] and preferences.get("dump_channel"):
                        await app.send_video(
                            chat_id=int(preferences["dump_channel"]), video=str(output),
                            caption=f"🎬 <b>{title[:900]}</b>\n🎥 Quality: <b>{source['label']}</b>",
                            supports_streaming=True,
                            duration=metadata.duration, width=metadata.width, height=metadata.height,
                            thumb=str(thumbnail) if thumbnail else None,
                        )
                except Exception as exc:
                    failures.append(f"Telegram: {str(exc)[:180]}")

            if "gofile" in targets:
                try:
                    await status.edit_text(f"☁️ Uploading to GoFile: {title[:100]}…")
                    token = None if preferences.get("gofile_guest", False) else (str(preferences.get("gofile_token") or os.getenv("GOFILE_TOKEN", "")).strip() or None)
                    folder_id = str(preferences.get("gofile_folder_id") or "").strip() or None
                    result = await gofile_upload(output, token=token, folder_id=folder_id)
                    await status.reply_text(
                        f"☁️ <b>GoFile upload complete</b>\n"
                        f"📄 {result['name'][:180]}\n"
                        f"🔗 {result['url']}"
                    )
                    completed.append("GoFile")
                except Exception as exc:
                    failures.append(f"GoFile: {str(exc)[:220]}")

            if completed:
                await status.edit_text(
                    f"✅ Completed: {', '.join(completed)}\n"
                    + (f"⚠️ Failed: {'; '.join(failures)}" if failures else f"🎬 {title[:150]}")
                )
            else:
                raise RuntimeError("All upload destinations failed: " + "; ".join(failures))
        finally:
            if output:
                output.unlink(missing_ok=True)
            if thumbnail:
                thumbnail.unlink(missing_ok=True)

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
        await query.answer("Queueing series…")
        await ensure_settings_loaded()
        episodes = menu["episodes"]
        # Remove the inline-button menu once the user starts the series download.
        if preferences["delete_menu"]:
            try:
                await query.message.delete()
            except Exception:
                pass
        summary = await app.send_message(
            chat_id=query.message.chat.id,
            text=f"📚 Starting {len(episodes)} episode(s), one at a time…",
        )
        try:
            row = await jobs.enqueue(
                owner_id, menu["source_url"], job_type="provider_series",
                destinations=list(preferences.get("destinations") or ["telegram"]),
                options={
                    "chat_id": query.message.chat.id,
                    "provider": menu["provider"],
                    "title": menu["series_title"],
                    "destinations": list(preferences.get("destinations") or ["telegram"]),
                },
            )
            await summary.edit_text(
                f"📥 Queued series job <b>#{row['id']}</b>\n"
                f"📚 Episodes: {len(episodes)}\n"
                "Episodes will be downloaded sequentially. Use /jobs to track it."
            )
        except Exception as exc:
            await summary.edit_text(f"❌ Could not queue series: {str(exc)[:400]}")

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
        # Remove the quality-selection message after the download button is clicked.
        if preferences["delete_menu"]:
            try:
                await query.message.delete()
            except Exception:
                pass
        status = await app.send_message(
            chat_id=query.message.chat.id,
            text=f"📥 Preparing {choice['title'][:100]}…",
        )
        try:
            await download_one(
                query.message.chat.id, status, choice["provider"], choice["url"],
                choice["title"], choice["label"],
            )
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {str(exc)[:700]}")
        finally:
            choices.pop(token, None)

    async def process_persistent_job(job: dict) -> None:
        """Execute a claimed provider episode or series using existing transfer logic."""
        options = job.get("options") or {}
        if isinstance(options, str):
            import json
            options = json.loads(options)
        await ensure_settings_loaded()
        chat_id = int(options["chat_id"])
        provider_name = str(options["provider"])
        destinations = options.get("destinations") or job.get("destinations") or preferences.get("destinations") or ["telegram"]
        if isinstance(destinations, str):
            import json
            destinations = json.loads(destinations)
        job_type = str(job.get("job_type"))
        title = str(options.get("title") or "Episode")
        status = await app.send_message(
            chat_id=chat_id, text=f"🧰 Job #{job['id']} started: {title[:120]}"
        )
        if job_type == "provider_episode":
            await download_one(chat_id, status, provider_name, str(job["source_url"]), title, destinations=list(destinations))
            return
        if job_type == "provider_series":
            provider = get_provider_by_name(provider_name)
            if provider is None:
                raise RuntimeError(f"Provider is not registered: {provider_name}")
            episodes = await provider.discover_episodes(str(job["source_url"]))
            if not episodes:
                raise RuntimeError("No episodes found for this series.")
            succeeded = 0
            failures: list[str] = []
            for index, episode in enumerate(episodes, 1):
                await status.edit_text(
                    f"📚 Job #{job['id']} · Episode {index}/{len(episodes)}\n"
                    f"{str(episode.get('title') or 'Episode')[:120]}\nPreparing…"
                )
                try:
                    await download_one(
                        chat_id, status, provider_name, str(episode["url"]),
                        str(episode.get("title") or f"Episode {index}"),
                        destinations=list(destinations),
                    )
                    succeeded += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures.append(f"{str(episode.get('title') or index)[:70]}: {str(exc)[:100]}")
            if failures:
                await status.edit_text(
                    f"⚠️ Series job #{job['id']} finished with {succeeded}/{len(episodes)} successful episodes.\n"
                    + "\n".join(failures[:8])
                )
            else:
                await status.edit_text(f"✅ Series job #{job['id']} complete: {succeeded}/{len(episodes)} episodes.")
            return
        raise ValueError(f"Unsupported queued job type: {job_type}")

    return process_persistent_job
