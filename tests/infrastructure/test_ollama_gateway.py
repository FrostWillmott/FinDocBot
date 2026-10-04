"""Tests for OllamaGateway with httpx mocked via respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from findocbot.domain.exceptions import ModelProviderError
from findocbot.infrastructure.ollama_gateway import OllamaGateway

BASE_URL = "http://ollama.test:11434"


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
async def gateway(sleeps: list[float]) -> OllamaGateway:
    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="qwen2.5:7b",
        embed_model="nomic-embed-text",
        batch_size=10,
        sleep=record_sleep,
    )
    await gw.start()
    yield gw
    await gw.stop()


@respx.mock
async def test_embed_many_over_batch_size_sends_several_requests(
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
async def test_embed_many_empty_list_returns_empty_without_request(
    gateway: OllamaGateway,
) -> None:
    """embed_many with empty list returns [] without calling the API."""
    route = respx.post(f"{BASE_URL}/api/embed")
    result = await gateway.embed_many([])
    assert result == []
    assert route.call_count == 0


@respx.mock
async def test_generate_structured_valid_json_returns_parsed_dict(
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
async def test_generate_structured_request_sends_context_and_output_limits(
    gateway: OllamaGateway,
) -> None:
    route = respx.post(f"{BASE_URL}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "{}"})
    )
    await gateway.generate_structured("question", {})
    body = json.loads(route.calls.last.request.content)
    assert body["options"] == {"num_ctx": 16384, "num_predict": 1024}


@respx.mock
async def test_generate_structured_http_503_raises_provider_error(
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
async def test_embed_one_single_text_returns_its_embedding(
    gateway: OllamaGateway,
) -> None:
    """embed_one() delegates to embed_many and returns single embedding."""
    respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.42, 0.73]]})
    )
    result = await gateway.embed_one("single query")
    assert result == [0.42, 0.73]


@respx.mock
async def test_embed_one_persistent_connect_error_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    """Transport-level failures surface as ModelProviderError."""
    respx.post(f"{BASE_URL}/api/embed").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with pytest.raises(ModelProviderError, match="unreachable"):
        await gateway.embed_one("query")


@respx.mock
async def test_embed_many_count_mismatch_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    """Fewer embeddings than inputs is an error, not silent truncation."""
    respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
    )
    with pytest.raises(ModelProviderError, match="for 2 inputs"):
        await gateway.embed_many(["a", "b"])


@respx.mock
async def test_generate_structured_non_json_text_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    """Non-JSON response payload raises ModelProviderError."""
    respx.post(f"{BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200, json={"response": "not-json", "done": True}
        )
    )
    with pytest.raises(ModelProviderError, match="malformed"):
        await gateway.generate_structured("question", {})


@respx.mock
async def test_generate_structured_json_array_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    respx.post(f"{BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200, json={"response": "[1, 2]", "done": True}
        )
    )
    with pytest.raises(ModelProviderError, match="not a JSON object"):
        await gateway.generate_structured("question", {})


@respx.mock
async def test_embed_many_non_numeric_payload_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [["x"]]})
    )
    with pytest.raises(ModelProviderError, match="malformed embeddings"):
        await gateway.embed_many(["text"])


async def test_start_and_stop_repeated_calls_are_idempotent() -> None:
    """Repeated start() reuses the client; stop() twice does not fail."""
    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="test",
        embed_model="test",
    )
    await gw.stop()  # No-op before start.
    await gw.start()
    client = gw._client
    await gw.start()
    assert gw._client is client
    await gw.stop()
    await gw.stop()
    assert gw._client is None


async def test_embed_one_before_start_raises_runtime_error() -> None:
    """Calling the gateway before start() raises RuntimeError."""
    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="test",
        embed_model="test",
    )
    with pytest.raises(RuntimeError, match="not started"):
        await gw.embed_one("prompt")


_EMBED_OK = httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})


@respx.mock
async def test_post_transient_503_retries_then_succeeds(
    gateway: OllamaGateway, sleeps: list[float]
) -> None:
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        side_effect=[httpx.Response(503), _EMBED_OK]
    )

    result = await gateway.embed_one("query")

    assert (result, route.call_count, len(sleeps)) == ([0.1, 0.2], 2, 1)


@respx.mock
async def test_post_persistent_503_stops_after_max_attempts(
    gateway: OllamaGateway, sleeps: list[float]
) -> None:
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(ModelProviderError, match="HTTP 503"):
        await gateway.embed_one("query")

    assert route.call_count == 3


@respx.mock
async def test_post_repeated_429_backoff_grows_exponentially(
    gateway: OllamaGateway, sleeps: list[float]
) -> None:
    respx.post(f"{BASE_URL}/api/embed").mock(return_value=httpx.Response(429))

    with pytest.raises(ModelProviderError):
        await gateway.embed_one("query")

    first, second = sleeps
    assert 0.5 <= first <= 0.75 and 1.0 <= second <= 1.5


@respx.mock
async def test_post_client_error_400_is_not_retried(
    gateway: OllamaGateway,
) -> None:
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(400)
    )

    with pytest.raises(ModelProviderError, match="HTTP 400"):
        await gateway.embed_one("query")

    assert route.call_count == 1


@respx.mock
async def test_post_timeout_is_not_retried(gateway: OllamaGateway) -> None:
    route = respx.post(f"{BASE_URL}/api/generate").mock(
        side_effect=httpx.ReadTimeout("slow")
    )

    with pytest.raises(ModelProviderError, match="timed out"):
        await gateway.generate_structured("question", {})

    assert route.call_count == 1


@respx.mock
async def test_post_transient_connect_error_retries_then_succeeds(
    gateway: OllamaGateway,
) -> None:
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        side_effect=[httpx.ConnectError("refused"), _EMBED_OK]
    )

    await gateway.embed_one("query")

    assert route.call_count == 2


@respx.mock
async def test_post_transient_read_error_retries_then_succeeds(
    gateway: OllamaGateway,
) -> None:
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        side_effect=[httpx.ReadError("connection reset"), _EMBED_OK]
    )

    await gateway.embed_one("query")

    assert route.call_count == 2


@respx.mock
async def test_post_persistent_protocol_error_raises_provider_error(
    gateway: OllamaGateway,
) -> None:
    route = respx.post(f"{BASE_URL}/api/generate").mock(
        side_effect=httpx.RemoteProtocolError("server disconnected")
    )

    with pytest.raises(ModelProviderError, match="unreachable"):
        await gateway.generate_structured("question", {})

    assert route.call_count == 3


@respx.mock
async def test_embed_many_exhausted_batch_aborts_remaining_batches(
    sleeps: list[float],
) -> None:
    async def no_sleep(delay: float) -> None:
        sleeps.append(delay)

    gw = OllamaGateway(
        base_url=BASE_URL,
        chat_model="test",
        embed_model="test",
        batch_size=1,
        sleep=no_sleep,
    )
    await gw.start()
    route = respx.post(f"{BASE_URL}/api/embed").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(ModelProviderError):
        await gw.embed_many(["a", "b", "c"])
    await gw.stop()

    assert route.call_count == 3  # first batch's attempts only


def test_init_zero_max_attempts_raises_value_error() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        OllamaGateway(
            base_url=BASE_URL,
            chat_model="test",
            embed_model="test",
            max_attempts=0,
        )


@respx.mock
async def test_ping_running_server_returns_none(
    gateway: OllamaGateway,
) -> None:
    respx.get(f"{BASE_URL}/api/version").mock(
        return_value=httpx.Response(200, json={"version": "0.12.3"})
    )

    assert await gateway.ping() is None


@respx.mock
async def test_ping_unreachable_server_raises_without_retry(
    gateway: OllamaGateway, sleeps: list[float]
) -> None:
    respx.get(f"{BASE_URL}/api/version").mock(
        side_effect=httpx.ConnectError("refused")
    )

    with pytest.raises(ModelProviderError, match="unreachable"):
        await gateway.ping()
    assert sleeps == []
