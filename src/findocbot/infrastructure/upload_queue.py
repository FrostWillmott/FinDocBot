"""In-process background queue for PDF ingestion."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from findocbot.use_cases.ports import UploadJob

logger = logging.getLogger(__name__)


class InProcessUploadQueue:
    """Bounded asyncio queue drained by a single background worker.

    Uploaded bytes are held in memory until processed, so jobs queued but not
    yet handled do not survive a restart; see DECISIONS.md.
    """

    def __init__(self, maxsize: int = 100) -> None:
        """Create a bounded queue with no processor attached yet."""
        self._queue: asyncio.Queue[UploadJob] = asyncio.Queue(maxsize=maxsize)
        self._processor: Callable[[UploadJob], Awaitable[None]] | None = None
        self._worker: asyncio.Task[None] | None = None

    def set_processor(
        self, processor: Callable[[UploadJob], Awaitable[None]]
    ) -> None:
        """Attach the callable that handles each queued job."""
        self._processor = processor

    async def enqueue(self, job: UploadJob) -> None:
        """Queue one upload for background processing."""
        await self._queue.put(job)

    async def start(self) -> None:
        """Spawn the worker task if it is not already running."""
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the worker; unprocessed jobs are dropped (not durable)."""
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    async def drain(self) -> None:
        """Process every queued job to completion (used by tests)."""
        while not self._queue.empty():
            job = await self._queue.get()
            await self._handle(job)
            self._queue.task_done()

    async def _run(self) -> None:
        """Consume jobs until cancelled."""
        while True:
            job = await self._queue.get()
            try:
                await self._handle(job)
            except Exception:
                # An unexpected bug must not kill the worker; log it and
                # keep processing. Expected failures are already turned
                # into a 'failed' document status by the processor.
                logger.exception(
                    "Upload worker failed on job %s", job.document_id
                )
            finally:
                self._queue.task_done()

    async def _handle(self, job: UploadJob) -> None:
        if self._processor is None:
            raise RuntimeError("Upload queue has no processor attached.")
        await self._processor(job)
