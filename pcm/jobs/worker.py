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
            processor_task = asyncio.create_task(processor(job), name=f"pcm-job-{job_id}")
            try:
                while not processor_task.done():
                    done, _ = await asyncio.wait({processor_task}, timeout=45)
                    if done:
                        break
                    alive = await repository.heartbeat(job_id, worker_id, lease_seconds=300)
                    if not alive:
                        logger.info("Job id=%s cancellation requested or lease lost; stopping processor", job_id)
                        processor_task.cancel()
                        try:
                            await processor_task
                        except asyncio.CancelledError:
                            pass
                        break
                if processor_task.cancelled():
                    status = await repository.finish(job_id, worker_id, error="Cancelled by owner or worker lease lost")
                    logger.info("PCM job id=%s transitioned to %s", job_id, status)
                else:
                    error = processor_task.exception()
                    if error is not None:
                        logger.exception("PCM job failed id=%s", job_id, exc_info=error)
                        status = await repository.finish(job_id, worker_id, error=str(error))
                    else:
                        status = await repository.finish(job_id, worker_id)
                    logger.info("PCM job id=%s transitioned to %s", job_id, status)
            except asyncio.CancelledError:
                processor_task.cancel()
                try:
                    await processor_task
                except asyncio.CancelledError:
                    pass
                raise
        except asyncio.CancelledError:
            logger.info("Job worker stopping")
            raise
        except Exception:
            logger.exception("Worker loop error; will retry")
            await asyncio.sleep(max(poll_seconds, 5.0))
