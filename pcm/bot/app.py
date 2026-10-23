"""Application entry point for the initial owner-only PCM bot."""

from __future__ import annotations

import asyncio
import logging

from pyrogram import Client

from pcm.bot.handlers import register_handlers
from pcm.core.config import Settings

logger = logging.getLogger("pcm")


async def run_bot() -> None:
    """Start the bot after validating configuration."""
    logger.info("Loading PCM configuration")
    settings = Settings.from_env()
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    app = Client(
        "pcm_bot",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        bot_token=settings.telegram_bot_token,
        workdir=str(settings.temp_dir),
    )
    register_handlers(app, settings.telegram_owner_id)
    logger.info("Starting Pyrogram client")
    await app.start()
    me = await app.get_me()
    logger.info(
        "PCM connected to Telegram as @%s (bot_id=%s). Owner-only access is enabled.",
        me.username or "unknown",
        me.id,
    )
    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Stopping Pyrogram client")
        await app.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    main_logger = logging.getLogger("pcm")
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        main_logger.info("PCM stopped by user")
    except Exception:
        main_logger.exception("PCM failed to start or crashed")
        raise


if __name__ == "__main__":
    main()
