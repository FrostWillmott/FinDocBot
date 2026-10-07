from __future__ import annotations

import asyncio

import pytest

from findocbot.infrastructure.upload_queue import InProcessUploadQueue
from findocbot.use_cases.ports import UploadJob


def _job(document_id: str) -> UploadJob:
    return UploadJob(document_id=document_id, filename="a.pdf", content=b"")


async def test_worker_processor_raises_keeps_processing_next_job() -> None:
    queue = InProcessUploadQueue()
    handled: list[str] = []
    second_done = asyncio.Event()

    async def processor(job: UploadJob) -> None:
        if job.document_id == "bad":
            raise ValueError("boom")
        handled.append(job.document_id)
        second_done.set()

    queue.set_processor(processor)
    await queue.start()
    await queue.enqueue(_job("bad"))
    await queue.enqueue(_job("good"))
    await asyncio.wait_for(second_done.wait(), timeout=1)
    await queue.stop()

    assert handled == ["good"]


async def test_drain_without_processor_raises_runtime_error() -> None:
    queue = InProcessUploadQueue()
    await queue.enqueue(_job("doc"))

    with pytest.raises(RuntimeError, match="no processor"):
        await queue.drain()
