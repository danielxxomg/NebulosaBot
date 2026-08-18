"""DatabaseBase — shared state and lifecycle for the Database facade.

Owns ``__slots__``, connection lifecycle (``connect`` / ``health_check``),
and the ``_unwrap`` helper used by every domain mixin.

RLS contract: Supabase tables are RLS-enabled with no policies, so only a
``service_role`` JWT or modern ``sb_secret_`` server key may obtain data.
``connect()`` fail-closes when the configured key is not service_role nor
sb_secret_ before any network call. ``health_check()`` proves ``sb_secret_``
via a read-only RLS SELECT probe on ``guild``/``ticket``.
Validation lives in :mod:`bot.config` — this module re-exports it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from supabase import AsyncClientOptions, acreate_client

from bot.config import ServiceRoleValidationError, validate_supabase_key

logger = logging.getLogger(__name__)

# Backwards-compat alias: older tests may import from base.
validate_service_role_key = validate_supabase_key
_decode_jwt_role = None  # not used from this module; canonical impl is in config

__all__ = ["ServiceRoleValidationError", "validate_service_role_key", "validate_supabase_key"]


# ------------------------------------------------------------------
# Postgrest response wrapper
# ------------------------------------------------------------------


def _unwrap(response: Any) -> list[dict[str, Any]]:
    """Extract ``.data`` from a Postgrest response.

    Supabase-py returns objects with ``.data`` (list[dict]).
    """
    if response is None:
        return []
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


# ------------------------------------------------------------------
# DatabaseBase
# ------------------------------------------------------------------


class DatabaseBase:
    """Shared state and lifecycle for the Supabase wrapper.

    Domain mixins inherit from this to access ``self._client``,
    ``self._url``, ``self._key``, and ``self._on_write``.
    """

    __slots__ = ("_client", "_key", "_on_write", "_url")

    def __init__(self, url: str, key: str) -> None:
        self._url = url
        self._key = key
        self._client: Any = None
        # Optional callback wired by RealtimeCacheSubscriber for self-echo
        # filtering.  Signature: async (table: str, identifier: str) -> None
        self._on_write: Callable[[str, str], Awaitable[None]] | None = None

    # -- lifecycle ----------------------------------------------------

    async def connect(self) -> None:
        """Create the async Supabase client and verify connectivity.

        Validates ``service_role`` before any network call (fail-closed) so
        anon/publishable credentials never obtain a client. Uses
        ``acreate_client`` (async factory) so the underlying HTTP adapter is
        created without blocking the event loop.
        """
        validate_service_role_key(self._key)
        logger.info("Connecting to Supabase at %s ...", self._url)
        self._client = await acreate_client(
            self._url,
            self._key,
            AsyncClientOptions(schema="public"),
        )
        healthy = await self.health_check()
        if not healthy:
            logger.warning("Supabase health check failed — continuing anyway")
        else:
            logger.info("Supabase connection verified")

    async def health_check(self) -> bool:
        """Ping the database and prove ``sb_secret_`` via RLS on guild+ticket.

        Delegates to :meth:`health_probe` so both ``guild`` and ``ticket`` are
        read — a credential that can only read one table fails closed. No mutation.
        """
        return await self.health_probe()

    async def health_probe(self) -> bool:
        """Read-only probe proving ``sb_secret_`` can read RLS tables via guild+ticket.

        Separate from :meth:`health_check` so S3.1 can assert the modern
        credential path explicitly exercises two RLS tables. Returns True
        only when both SELECTs succeed; otherwise False (fail-closed, no DDL).
        """

        if self._client is None:
            logger.error("health_probe called before connect()")
            return False

        try:
            guild_resp = await self._client.table("guild").select("id").limit(1).execute()
            _unwrap(guild_resp)
            ticket_resp = await self._client.table("ticket").select("id").limit(1).execute()
            _unwrap(ticket_resp)
            return True
        except Exception:
            logger.exception("Supabase health probe (guild+ticket) failed")
            return False
