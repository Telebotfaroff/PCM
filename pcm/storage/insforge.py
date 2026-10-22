"""InsForge PostgreSQL connectivity using asyncpg.

Pass the server-side PostgreSQL connection string from an environment variable.
Never expose this DSN to Telegram clients or commit it to source control.
"""

from __future__ import annotations

import asyncpg


class InsForgeStore:
    """Owns a bounded asyncpg pool; query/repository methods live in separate modules."""

    def __init__(self, database_url: str, *, max_size: int = 4) -> None:
        if not database_url.strip():
            raise ValueError("INSFORGE_DATABASE_URL is required")
        if max_size < 1:
            raise ValueError("max_size must be positive")
        self._database_url = database_url
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Open the pool and require TLS for hosted PostgreSQL connections."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._database_url,
            min_size=1,
            max_size=self._max_size,
            command_timeout=15,
            ssl="require",
        )

    async def close(self) -> None:
        """Close all pooled connections cleanly."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        """Return whether the database accepts a simple query."""
        if self._pool is None:
            raise RuntimeError("InsForgeStore is not connected")
        async with self._pool.acquire() as connection:
            return await connection.fetchval("SELECT TRUE")

    async def pool(self) -> asyncpg.Pool:
        """Return the connected pool for repository-layer operations."""
        if self._pool is None:
            raise RuntimeError("InsForgeStore is not connected")
        return self._pool
