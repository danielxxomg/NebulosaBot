"""Integration tests for bot.webhook.server — POST /webhook/sync endpoint.

Covers the cache-sync-webhook spec scenarios via aiohttp's TestClient:
    - HMAC signature verification (valid/missing/tampered)
    - Payload validation (malformed/missing guild_id)
    - Idempotent invalidation (duplicate replay, unknown guild_id)
    - Cache invalidation effect (keys evicted on valid request)

Uses a real TTLCache (behavioural assertions — no mock call counts) and
mocks nothing: the cache is in-memory and the TestClient does not bind a
real port.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.core.cache import TTLCache
from bot.webhook.auth import compute_signature
from bot.webhook.server import create_webhook_app, start_webhook_server, stop_webhook_server

if TYPE_CHECKING:
    from aiohttp.web import Application

SECRET = "test-webhook-secret"
GUILD_ID = 123456789
CACHE_KEY = f"{GUILD_ID}:config"


def _signed_body(payload: dict, secret: str = SECRET) -> tuple[bytes, dict[str, str]]:
    """Return (raw_body_bytes, headers_with_signature) for *payload*."""
    raw = json.dumps(payload).encode()
    headers = {"X-Webhook-Signature": compute_signature(raw, secret)}
    return raw, headers


@pytest.fixture
def webhook_cache() -> TTLCache:
    """A TTLCache pre-populated with a guild config entry to invalidate."""
    cache = TTLCache()
    cache.set(CACHE_KEY, {"prefix": "!"}, ttl=300)
    return cache


@pytest.fixture
async def client(webhook_cache: TTLCache) -> TestClient:
    """A started TestClient backed by the webhook app (no real port bind)."""
    app: Application = create_webhook_app(webhook_cache, SECRET)
    server = TestServer(app)
    test_client = TestClient(server)
    await test_client.start_server()
    yield test_client
    await test_client.close()


# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    """Spec: HMAC signature verification."""

    async def test_valid_signature_returns_200_and_invalidates(
        self, client: TestClient, webhook_cache: TTLCache
    ) -> None:
        """Valid signature -> 200 and the guild cache key is evicted."""
        assert webhook_cache.get(CACHE_KEY) is not None  # precondition: present

        raw, headers = _signed_body({"guild_id": GUILD_ID, "entity": "guild_config"})
        resp = await client.post("/webhook/sync", data=raw, headers=headers)

        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert webhook_cache.get(CACHE_KEY) is None  # invalidated

    async def test_missing_signature_returns_401_no_invalidation(
        self, client: TestClient, webhook_cache: TTLCache
    ) -> None:
        """Spec: missing signature header -> 401, cache untouched."""
        raw = json.dumps({"guild_id": GUILD_ID}).encode()

        resp = await client.post("/webhook/sync", data=raw)

        assert resp.status == 401
        assert webhook_cache.get(CACHE_KEY) is not None  # NOT invalidated

    async def test_tampered_signature_returns_401_no_invalidation(
        self, client: TestClient, webhook_cache: TTLCache
    ) -> None:
        """Spec: wrong/tampered signature -> 401, cache untouched."""
        raw = json.dumps({"guild_id": GUILD_ID}).encode()
        valid_sig = compute_signature(raw, SECRET)
        tampered = valid_sig[:-2] + "00"
        headers = {"X-Webhook-Signature": tampered}

        resp = await client.post("/webhook/sync", data=raw, headers=headers)

        assert resp.status == 401
        assert webhook_cache.get(CACHE_KEY) is not None  # NOT invalidated


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    """Spec: payload validation."""

    async def test_malformed_json_returns_400_no_invalidation(
        self, client: TestClient, webhook_cache: TTLCache
    ) -> None:
        """Spec: malformed JSON body -> 400, no invalidation."""
        raw = b"{not valid json"
        headers = {"X-Webhook-Signature": compute_signature(raw, SECRET)}

        resp = await client.post("/webhook/sync", data=raw, headers=headers)

        assert resp.status == 400
        assert webhook_cache.get(CACHE_KEY) is not None  # NOT invalidated

    async def test_missing_guild_id_returns_400_no_invalidation(
        self, client: TestClient, webhook_cache: TTLCache
    ) -> None:
        """Spec: signed body without guild_id -> 400."""
        raw, headers = _signed_body({"entity": "guild_config"})

        resp = await client.post("/webhook/sync", data=raw, headers=headers)

        assert resp.status == 400
        assert webhook_cache.get(CACHE_KEY) is not None  # NOT invalidated


# ---------------------------------------------------------------------------
# Idempotent invalidation
# ---------------------------------------------------------------------------


class TestIdempotentInvalidation:
    """Spec: idempotent invalidation."""

    async def test_duplicate_delivery_returns_200_both_times(self, client: TestClient, webhook_cache: TTLCache) -> None:
        """Spec: replay of the same payload -> 200 both times, idempotent."""
        raw, headers = _signed_body({"guild_id": GUILD_ID})

        first = await client.post("/webhook/sync", data=raw, headers=headers)
        second = await client.post("/webhook/sync", data=raw, headers=headers)

        assert first.status == 200
        assert second.status == 200
        assert webhook_cache.get(CACHE_KEY) is None  # evicted (idempotent)

    async def test_unknown_guild_id_returns_200(self, client: TestClient, webhook_cache: TTLCache) -> None:
        """Spec: valid payload for an unknown guild_id -> 200 (idempotent no-op)."""
        raw, headers = _signed_body({"guild_id": 999999999})

        resp = await client.post("/webhook/sync", data=raw, headers=headers)

        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True


# ---------------------------------------------------------------------------
# Server lifecycle — start_webhook_server / stop_webhook_server
# ---------------------------------------------------------------------------


class TestServerLifecycle:
    """Spec: server lifecycle — graceful degraded mode on port conflict."""

    async def test_start_returns_runner_when_secret_present(self, webhook_cache: TTLCache) -> None:
        """Spec: server starts on connect when a secret is configured."""
        with patch("bot.webhook.server.web.TCPSite") as mock_tcpsite:
            mock_tcpsite.return_value.start = AsyncMock()
            runner = await start_webhook_server("127.0.0.1", 8080, webhook_cache, SECRET)

        assert runner is not None
        await runner.cleanup()

    async def test_start_returns_none_when_no_secret(self, webhook_cache: TTLCache) -> None:
        """Spec: no server without secret — empty secret -> None (server not started)."""
        runner = await start_webhook_server("127.0.0.1", 8080, webhook_cache, "")

        assert runner is None

    async def test_start_returns_none_on_port_conflict(self, webhook_cache: TTLCache) -> None:
        """Spec: port conflict degraded mode — OSError on bind -> None, bot continues."""
        with patch("bot.webhook.server.web.TCPSite") as mock_tcpsite:
            mock_tcpsite.return_value.start = AsyncMock(side_effect=OSError("Address already in use"))
            runner = await start_webhook_server("127.0.0.1", 8080, webhook_cache, SECRET)

        assert runner is None

    async def test_stop_cleans_up_runner(self) -> None:
        """stop_webhook_server MUST call runner.cleanup()."""
        runner = MagicMock(spec=web.AppRunner)
        runner.cleanup = AsyncMock()

        await stop_webhook_server(runner)

        runner.cleanup.assert_awaited_once()

    async def test_stop_with_none_is_noop(self) -> None:
        """stop_webhook_server(None) MUST NOT raise."""
        await stop_webhook_server(None)  # no exception
