"""aiohttp webhook server for dashboard-triggered cache invalidation.

Exposes :func:`create_webhook_app` — an application factory wiring the
``POST /webhook/sync`` route — and :func:`start_webhook_server` /
:func:`stop_webhook_server` for lifecycle management from
``NebulosaBot.setup_hook``.

The handler verifies the HMAC-SHA256 signature over the raw body, parses
the payload, and invalidates the full guild cache entry. Invalid requests
return 401 (bad signature) or 400 (malformed payload); valid requests
return 200 and are idempotent.
"""

from __future__ import annotations

import logging

from aiohttp import web

from bot.core.cache import TTLCache
from bot.webhook.auth import SIGNATURE_HEADER, verify_signature
from bot.webhook.models import WebhookSyncPayload

logger = logging.getLogger(__name__)

_WEBHOOK_PATH = "/webhook/sync"

# Typed AppKeys (aiohttp 3.14+ best practice — avoids NotAppKeyWarning).
_WEBHOOK_CACHE_KEY = web.AppKey("webhook_cache", TTLCache)
_WEBHOOK_SECRET_KEY = web.AppKey("webhook_secret", str)


async def handle_sync(request: web.Request) -> web.Response:
    """POST /webhook/sync — verify signature, invalidate guild cache.

    Args:
        request: The aiohttp request. ``request.app`` carries the shared
            ``cache`` and ``secret`` set by :func:`create_webhook_app`.

    Returns:
        200 on success, 401 on bad/missing signature, 400 on malformed payload.
    """
    cache: TTLCache = request.app[_WEBHOOK_CACHE_KEY]
    secret: str = request.app[_WEBHOOK_SECRET_KEY]

    raw = await request.read()

    signature = request.headers.get(SIGNATURE_HEADER)
    if not verify_signature(raw, signature, secret):
        logger.warning("Webhook /webhook/sync rejected: invalid signature")
        return web.json_response({"error": "invalid signature"}, status=401)

    try:
        payload = WebhookSyncPayload.from_json_bytes(raw)
    except ValueError:
        logger.warning("Webhook /webhook/sync rejected: malformed payload")
        return web.json_response({"error": "malformed payload"}, status=400)

    cache.invalidate_guild(payload.guild_id)
    logger.info("Webhook invalidated cache for guild_id=%s entity=%s", payload.guild_id, payload.entity)

    return web.json_response({"ok": True}, status=200)


def create_webhook_app(cache: TTLCache, secret: str) -> web.Application:
    """Build the aiohttp Application exposing the sync webhook endpoint.

    Args:
        cache: The bot TTLCache whose guild entries are invalidated.
        secret: The shared HMAC secret used for signature verification.

    Returns:
        A configured :class:`aiohttp.web.Application` ready to run.
    """
    app = web.Application()
    app[_WEBHOOK_CACHE_KEY] = cache
    app[_WEBHOOK_SECRET_KEY] = secret
    app.router.add_post(_WEBHOOK_PATH, handle_sync)
    return app


async def start_webhook_server(
    host: str,
    port: int,
    cache: TTLCache,
    secret: str,
) -> web.AppRunner | None:
    """Start the webhook aiohttp server on the Discord event loop.

    Per the spec, if ``secret`` is empty the server MUST NOT start. If the
    port is unavailable (``OSError``) or startup fails unexpectedly, the
    error is logged and ``None`` is returned so the bot continues in
    degraded TTL-only mode.

    Args:
        host: Bind address (e.g. ``127.0.0.1`` or ``0.0.0.0`` on Pterodactyl).
        port: Bind port.
        cache: The bot TTLCache passed to the app factory.
        secret: Shared HMAC secret. Empty -> server does not start.

    Returns:
        The started :class:`~aiohttp.web.AppRunner` (call
        :func:`stop_webhook_server` on shutdown), or ``None`` in degraded mode.
    """
    if not secret:
        logger.warning("WEBHOOK_SECRET not set — webhook server not started")
        return None

    app = create_webhook_app(cache, secret)
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
    except OSError:
        logger.error(
            "Webhook server failed to bind %s:%s — degraded mode (stale cache until TTL)",
            host,
            port,
            exc_info=True,
        )
        await runner.cleanup()
        return None
    except Exception:
        logger.exception("Unexpected webhook server startup error — degraded mode")
        await runner.cleanup()
        return None

    logger.info("Webhook server listening on %s:%s", host, port)
    return runner


async def stop_webhook_server(runner: web.AppRunner | None) -> None:
    """Gracefully stop the webhook server if it was started.

    Args:
        runner: The runner returned by :func:`start_webhook_server`, or
            ``None`` when the server never started (no-op).
    """
    if runner is not None:
        await runner.cleanup()
        logger.info("Webhook server stopped")
