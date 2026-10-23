"""PostgreSQL-backed runtime preferences for PCM."""
from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

_DEFAULTS: dict[str, Any] = {
    "auto_quality": True,
    "delete_menu": True,
    "dump_enabled": False,
    "dump_channel": None,
    "destinations": ["telegram"],
    "gofile_token": "",
    "gofile_guest": False,
    "gofile_folder_id": "",
}


def _database_url() -> str:
    value = os.getenv("INSFORGE_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("INSFORGE_DATABASE_URL is not configured.")
    return value


async def load_preferences(owner_id: int) -> dict[str, Any]:
    """Load preferences for the owner, initializing a row on first use."""
    conn = await asyncpg.connect(_database_url())
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pcm_bot_settings (
                owner_id BIGINT PRIMARY KEY,
                settings JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        row = await conn.fetchrow(
            "SELECT settings FROM pcm_bot_settings WHERE owner_id = $1", owner_id
        )
        if row is None:
            await conn.execute(
                "INSERT INTO pcm_bot_settings (owner_id, settings) VALUES ($1, $2::jsonb) "
                "ON CONFLICT (owner_id) DO NOTHING",
                owner_id,
                json.dumps(_DEFAULTS),
            )
            return dict(_DEFAULTS)
        saved = row["settings"]
        if isinstance(saved, str):
            saved = json.loads(saved)
        return {**_DEFAULTS, **(saved or {})}
    finally:
        await conn.close()


async def save_preferences(owner_id: int, settings: dict[str, Any]) -> None:
    """Persist the complete preferences document for the owner."""
    conn = await asyncpg.connect(_database_url())
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pcm_bot_settings (
                owner_id BIGINT PRIMARY KEY,
                settings JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            """
            INSERT INTO pcm_bot_settings (owner_id, settings, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (owner_id) DO UPDATE
            SET settings = EXCLUDED.settings, updated_at = NOW()
            """,
            owner_id,
            json.dumps({**_DEFAULTS, **settings}),
        )
    finally:
        await conn.close()
