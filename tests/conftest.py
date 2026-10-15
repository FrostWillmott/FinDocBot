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
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests that require Docker and Ollama",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring Docker (testcontainers)",
    )
    config.addinivalue_line(
        "markers",
        "e2e: mark test as requiring Docker and a real Ollama",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(
            reason="Use --integration to run Docker-dependent tests"
        )
        for item in items:
            if item.get_closest_marker("integration") is not None:
                item.add_marker(skip_integration)
    if not config.getoption("--e2e"):
        skip_e2e = pytest.mark.skip(reason="Use --e2e to run end-to-end tests")
        for item in items:
            if item.get_closest_marker("e2e") is not None:
                item.add_marker(skip_e2e)
