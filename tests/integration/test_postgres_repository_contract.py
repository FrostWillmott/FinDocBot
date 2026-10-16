"""PostgreSQL repositories pass the same cases as the in-memory fakes."""

from __future__ import annotations

import pytest

from findocbot.infrastructure.db import PostgresPool
from findocbot.infrastructure.postgres_repositories import (
    PostgresChunkRepository,
    PostgresDocumentRepository,
)
from tests.integration.conftest import EMBEDDING_DIM
from tests.repository_contract import (
    ChunkRepositoryContract,
    DocumentRepositoryContract,
    Repositories,
)


@pytest.fixture
def postgres_repos(db_pool: PostgresPool) -> Repositories:
    return Repositories(
        documents=PostgresDocumentRepository(db_pool),
        chunks=PostgresChunkRepository(db_pool, EMBEDDING_DIM),
        dim=EMBEDDING_DIM,
    )


@pytest.mark.integration
class TestPostgresDocumentRepository(DocumentRepositoryContract):
    @pytest.fixture
    def repos(self, postgres_repos: Repositories) -> Repositories:
        return postgres_repos


@pytest.mark.integration
class TestPostgresChunkRepository(ChunkRepositoryContract):
    @pytest.fixture
    def repos(self, postgres_repos: Repositories) -> Repositories:
        return postgres_repos
