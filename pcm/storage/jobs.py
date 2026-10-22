"""Small PostgreSQL job repository with atomic worker claims."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


class JobRepository:
    """Persistence operations for job creation and lease-based worker claiming."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_job(
        self,
        *,
        owner_telegram_id: int,
        source_url: str,
        source_identity: str,
        settings: dict[str, Any] | None = None,
        batch_id: uuid.UUID | None = None,
        priority: int = 0,
    ) -> uuid.UUID:
        """Create a queued job and its initial event in one transaction."""
        job_id = uuid.uuid4()
        payload = json.dumps(settings or {})
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO pcm_jobs
                        (id, batch_id, owner_telegram_id, source_url,
                         source_identity, state, priority, settings)
                    VALUES ($1, $2, $3, $4, $5, 'queued', $6, $7::jsonb)
                    """,
                    job_id, batch_id, owner_telegram_id, source_url,
                    source_identity, priority, payload,
                )
                await connection.execute(
                    """
                    INSERT INTO pcm_job_events (job_id, event_type, to_state)
                    VALUES ($1, 'job_created', 'queued')
                    """,
                    job_id,
                )
        return job_id

    async def claim_next_job(
        self, *, worker_id: str, lease_seconds: int = 120
    ) -> dict[str, Any] | None:
        """Atomically claim one queued job; concurrent workers cannot claim the same row."""
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds < 10:
            raise ValueError("lease_seconds must be at least 10")

        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM pcm_jobs
                        WHERE state IN ('queued', 'waiting_for_worker')
                           OR (state = 'downloading' AND lease_expires_at < now())
                        ORDER BY priority DESC, created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE pcm_jobs AS job
                    SET state = 'downloading',
                        worker_id = $1,
                        lease_expires_at = now() + ($2 * interval '1 second'),
                        updated_at = now()
                    FROM candidate
                    WHERE job.id = candidate.id
                    RETURNING job.*
                    """,
                    worker_id, lease_seconds,
                )
                if row is None:
                    return None
                await connection.execute(
                    """
                    INSERT INTO pcm_job_events
                        (job_id, event_type, from_state, to_state, details)
                    VALUES ($1, 'job_claimed', NULL, 'downloading', $2::jsonb)
                    """,
                    row["id"], json.dumps({"worker_id": worker_id}),
                )
                return dict(row)

    async def get_job(self, job_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch a job by ID."""
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT * FROM pcm_jobs WHERE id = $1", job_id
            )
        return dict(row) if row is not None else None
