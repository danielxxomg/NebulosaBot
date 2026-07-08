"""DatabaseBase — shared state and lifecycle for the Database facade.

Owns ``__slots__``, connection lifecycle (``connect`` / ``health_check``),
and the ``_unwrap`` helper used by every domain mixin.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from supabase import AsyncClientOptions, acreate_client

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Postgrest response wrapper
# ------------------------------------------------------------------


def _unwrap(response: Any) -> list[dict]:
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

        Uses ``acreate_client`` (async factory) so the underlying HTTP
        adapter is created without blocking the event loop.
        """
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
        """Ping the database by selecting 1 row from the guild table.

        Returns ``True`` if the query succeeds, ``False`` otherwise.
        """
        if self._client is None:
            logger.error("health_check called before connect()")
            return False

        try:
            # Lightweight probe — reads at most one row.
            response = await self._client.table("guild").select("id").limit(1).execute()
            _unwrap(response)  # drain so we don't leak a cursor
            return True
        except Exception:
            logger.exception("Supabase health check query failed")
            return False
