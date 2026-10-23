"""Polling worker for durable PCM jobs; processing is injected by the bot layer."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from pcm.jobs.repository import JobRepository

logger = logging.getLogger("pcm.jobs.worker")
JobProcessor = Callable[[dict[str, Any]], Awaitable[None]]


async def run_worker(repository: JobRepository, processor: JobProcessor, *, poll_seconds: float = 3.0) -> None:
    """Recover expired jobs, then claim and process jobs until cancelled."""
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(3)}"
    await repository.ensure_schema()
    recovered = await repository.recover_expired()
    logger.info("Job worker %s started; recovered %d expired job(s)", worker_id, recovered)
    while True:
        try:
            await repository.recover_expired()
            job = await repository.claim_next(worker_id, lease_seconds=300)
            if job is None:
                await asyncio.sleep(poll_seconds)
                continue
            job_id = int(job["id"])
            logger.info("Claimed PCM job id=%s type=%s attempt=%s", job_id, job["job_type"], job["attempts"])
            try:
                await processor(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("PCM job failed id=%s", job_id)
                try:
                    status = await repository.finish(job_id, worker_id, error=str(exc))
                    logger.info("PCM job id=%s transitioned to %s", job_id, status)
                except Exception:
                    logger.exception("Could not persist failed state for job id=%s", job_id)
            else:
                status = await repository.finish(job_id, worker_id)
                logger.info("PCM job id=%s transitioned to %s", job_id, status)
        except asyncio.CancelledError:
            logger.info("Job worker stopping")
            raise
        except Exception:
            logger.exception("Worker loop error; will retry")
            await asyncio.sleep(max(poll_seconds, 5.0))
