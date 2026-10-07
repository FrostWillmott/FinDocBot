"""Shared fakes for use-case tests."""

from __future__ import annotations

from findocbot.use_cases.ports import UploadJob
from findocbot.use_cases.upload_pdf import UploadPDFUseCase


class StubProvider:
    """Fake provider with a configurable structured response."""

    def __init__(self, structured: dict | None = None) -> None:
        self.structured = structured or {
            "answer": "ok",
            "confidence": "high",
        }

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def embed_one(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        return self.structured


class RecordingQueue:
    """Records enqueued upload jobs instead of processing them."""

    def __init__(self) -> None:
        """Start with no recorded jobs."""
        self.jobs: list[UploadJob] = []

    async def enqueue(self, job: UploadJob) -> None:
        """Record one job."""
        self.jobs.append(job)


async def index_document(
    upload: UploadPDFUseCase, filename: str, content: bytes
) -> None:
    """Submit one upload and process it synchronously for test setup.

    Mirrors the production flow minus the background worker: submit returns
    a pending document, then ``process`` runs the pipeline to completion.
    """
    document = await upload.submit(filename, content)
    await upload.process(
        UploadJob(
            document_id=document.id,
            filename=filename,
            content=content,
        )
    )
