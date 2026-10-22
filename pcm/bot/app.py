"""Application entry point for the initial owner-only PCM bot."""

from __future__ import annotations

import asyncio

from pyrogram import Client

from pcm.bot.handlers import register_handlers
from pcm.core.config import Settings


async def run_bot() -> None:
    """Start the bot after validating configuration."""
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
    await app.start()
    print("PCM bot started. Only the configured owner is authorized.")
    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
