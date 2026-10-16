"""The in-memory repository fakes show the behaviour Postgres does."""

from __future__ import annotations

import pytest

from tests.in_memory import in_memory_repositories
from tests.repository_contract import (
    ChunkRepositoryContract,
    DocumentRepositoryContract,
    Repositories,
)


@pytest.fixture
def wired_repos() -> Repositories:
    documents, chunks = in_memory_repositories()
    return Repositories(documents=documents, chunks=chunks, dim=4)


class TestInMemoryDocumentRepository(DocumentRepositoryContract):
    @pytest.fixture
    def repos(self, wired_repos: Repositories) -> Repositories:
        return wired_repos


class TestInMemoryChunkRepository(ChunkRepositoryContract):
    @pytest.fixture
    def repos(self, wired_repos: Repositories) -> Repositories:
        return wired_repos
