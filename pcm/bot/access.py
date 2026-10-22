"""Owner authorization shared by every bot handler."""

from pyrogram import filters
from pyrogram.types import CallbackQuery, Message


def owner_filter(owner_id: int):
    """Create a Pyrogram filter that accepts only the configured owner."""
    async def check(_, __, update: Message | CallbackQuery) -> bool:
        user = update.from_user
        return user is not None and user.id == owner_id

    return filters.create(check)
