"""Database — Supabase client wrapper for NebulosaBot.

Provides async access to the Supabase Postgres instance with health-check,
guild-config read/write, and connection lifecycle management.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import ClientOptions, create_client

from bot.models.guild import GuildConfig

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Postgrest response wrapper — adapts sync API for async callers
# ------------------------------------------------------------------


def _unwrap(response: Any) -> list[dict]:
    """Extract ``.data`` from a Postgrest sync response.

    Supabase-py's sync API returns objects with ``.data`` (list[dict]).
    """
    if response is None:
        return []
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------


class Database:
    """Async wrapper around a Supabase Python client.

    Instantiate with the project URL and API key (anon or service_role).
    Call ``connect()`` before any data-access methods.
    """

    __slots__ = ("_url", "_key", "_client")

    def __init__(self, url: str, key: str) -> None:
        self._url = url
        self._key = key
        self._client: Any = None

    # -- lifecycle ----------------------------------------------------

    async def connect(self) -> None:
        """Create the Supabase client and verify connectivity.

        The client is built via the sync ``create_client`` factory because
        supabase-py auto-negotiates the underlying HTTP adapter. This call
        is lightweight — real I/O happens on the first query.
        """
        logger.info("Connecting to Supabase at %s ...", self._url)
        self._client = create_client(
            self._url,
            self._key,
            ClientOptions(schema="public"),
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
            response = self._client.table("guild").select("id").limit(1).execute()
            _unwrap(response)  # drain so we don't leak a cursor
            return True
        except Exception:
            logger.exception("Supabase health check query failed")
            return False

    # -- guild --------------------------------------------------------

    async def get_guild(self, guild_id: str) -> dict | None:
        """Fetch a guild row by its Discord snowflake *guild_id*.

        Returns the raw camelCase row dict, or ``None`` if the guild has
        never been configured.
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB get_guild(%r)", guild_id)
        response = self._client.table("guild").select("*").eq("id", guild_id).execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def upsert_guild(self, config: GuildConfig) -> None:
        """Insert or update a guild configuration row.

        Uses Supabase ``upsert`` so the same method handles both ``INSERT``
        (new guild) and ``UPDATE`` (changed prefix, language, etc.).
        """
        if self._client is None:
            raise RuntimeError("Database.connect() must be called first")

        logger.debug("DB upsert_guild(%r)", config.id)
        self._client.table("guild").upsert(config.to_db_dict()).execute()
