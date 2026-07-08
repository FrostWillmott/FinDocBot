"""Tests for OllamaGateway with httpx mocked via respx."""

import json

import httpx
import pytest
import respx

from findocbot.domain.exceptions import ModelProviderError
from findocbot.infrastructure.ollama_gateway import OllamaGateway

BASE_URL = "http://ollama.test:11434"


@pytest.fixture
async def gateway() -> OllamaGateway:
    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="qwen2.5:7b",
        embed_model="nomic-embed-text",
        batch_size=10,
    )
    await gw.start()
    yield gw
    await gw.stop()


@respx.mock
async def test_embed_many_batches_correctly(
    gateway: OllamaGateway,
) -> None:
    """embed_many() batches large text lists into multiple requests."""
    # Two batches of 2 each (batch_size overridden to 2 in this test).
    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="test",
        embed_model="test",
        batch_size=2,
    )
    await gw.start()
    try:
        route = respx.post(f"{BASE_URL}/api/embed").mock(
            side_effect=[
                httpx.Response(
                    200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
                ),
                httpx.Response(200, json={"embeddings": [[0.5, 0.6]]}),
            ]
        )
        result = await gw.embed_many(["a", "b", "c"])
        assert len(result) == 3
        assert route.call_count == 2  # 2 items first batch, 1 second
    finally:
        await gw.stop()


@respx.mock
async def test_embed_empty_list_returns_empty(
    gateway: OllamaGateway,
) -> None:
    """embed_many with empty list returns [] without calling the API."""
    route = respx.post(f"{BASE_URL}/api/embed")
    result = await gateway.embed_many([])
    assert result == []
    assert route.call_count == 0


@respx.mock
async def test_generate_structured_parses_json(
    gateway: OllamaGateway,
) -> None:
    """generate_structured() constrains output with format and parses JSON."""
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    respx.post(f"{BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": json.dumps({
                    "answer": "20%",
                    "confidence": "high",
                }),
                "done": True,
            },
        )
    )
    result = await gateway.generate_structured("What is the revenue?", schema)
    assert result == {"answer": "20%", "confidence": "high"}


@respx.mock
async def test_generate_structured_raises_on_http_error(
    gateway: OllamaGateway,
) -> None:
    """_post wraps transport errors as ModelProviderError."""
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    respx.post(f"{BASE_URL}/api/generate").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(ModelProviderError):
        await gateway.generate_structured("What is the revenue?", schema)


@respx.mock
async def test_embed_one_uses_embed_many(
    gateway: OllamaGateway,
) -> None:
    """embed_one() delegates to embed_many and returns single embedding."""
    respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.42, 0.73]]})
    )
    result = await gateway.embed_one("single query")
    assert result == [0.42, 0.73]


async def test_gateway_raises_if_not_started() -> None:
    """Calling the gateway before start() raises RuntimeError."""
    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="test",
        embed_model="test",
    )
    with pytest.raises(RuntimeError, match="not started"):
        await gw.embed_one("prompt")
