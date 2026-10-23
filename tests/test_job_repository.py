"""Fast unit tests for queue input validation; no live InsForge credentials required."""
from __future__ import annotations

import pytest

from pcm.jobs.repository import JobRepository


@pytest.mark.asyncio
async def test_enqueue_rejects_empty_url_before_database_access() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="source_url"):
        await repo.enqueue(123, "  ")


@pytest.mark.asyncio
async def test_enqueue_rejects_unknown_destination_before_database_access() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="destinations"):
        await repo.enqueue(123, "https://example.com/video", destinations=["telegram", "unknown"])


@pytest.mark.asyncio
async def test_enqueue_requires_at_least_one_destination() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="destinations"):
        await repo.enqueue(123, "https://example.com/video", destinations=[])


@pytest.mark.asyncio
async def test_enqueue_bounds_retry_budget_before_database_access() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="max_attempts"):
        await repo.enqueue(123, "https://example.com/video", max_attempts=11)


@pytest.mark.asyncio
async def test_claim_rejects_invalid_lease_without_database_access() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="lease_seconds"):
        await repo.claim_next("colab-worker", lease_seconds=1)


@pytest.mark.asyncio
async def test_action_rejects_unknown_action_before_database_access() -> None:
    repo = JobRepository(database_url="")
    with pytest.raises(ValueError, match="Unsupported job action"):
        await repo.request_action(123, 1, "delete")
