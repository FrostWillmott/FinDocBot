"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _postgres_dsn_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give Settings a POSTGRES_DSN so tests run without a real .env.

    ``postgres_dsn`` has no default (a password must not ship in source), so
    any test that builds ``Settings()`` needs the variable present.
    """
    monkeypatch.setenv(
        "POSTGRES_DSN",
        "postgresql://postgres:postgres@localhost:5432/findocbot",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require Docker",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring Docker (testcontainers)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--integration"):
        return
    skip_integration = pytest.mark.skip(
        reason="Use --integration to run Docker-dependent tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
