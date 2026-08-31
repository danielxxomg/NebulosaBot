"""TTLCache — dict-based in-memory cache with per-key TTL expiration.

Keys follow the convention ``{guild_id}:{entity}`` to enable guild-scoped
invalidation via ``invalidate_guild()``.

Default TTL is 300 seconds (5 minutes), matching the cache desync window
defined in the architecture decisions.

Realtime-invalidated entities: guild, greeting_config, ticket, ticket_note, member, economy_config
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300  # seconds — guild / greeting config window (design)
CACHE_TTL = DEFAULT_TTL  # alias for backwards-compat imports
GUILD_TTL = DEFAULT_TTL
GUILD_CONFIG_TTL = DEFAULT_TTL
GREETING_TTL = DEFAULT_TTL
GREETING_CONFIG_TTL = DEFAULT_TTL
ECONOMY_CONFIG_TTL = DEFAULT_TTL
LEADERBOARD_TTL = 30  # seconds — accepted staleness window (cache-layer spec)
LEADERBOARD_CACHE_TTL = LEADERBOARD_TTL  # alias for economy_service compat


def cache_key(guild_id: str | int, entity: str) -> str:
    """Build a guild-scoped cache key ``{guild_id}:{entity}``.

    Centralizes the ``{guild_id}:{entity}`` convention so callers (services,
    realtime CDC, tests) remain DRY and guild isolation is auditable.

    Examples:
        cache_key("123", "config") -> "123:config"
        cache_key(456, "greeting_config") -> "456:greeting_config"
    """
    return f"{guild_id}:{entity}"


class TTLCache:
    """Dict-based cache with per-key timestamp tracking.

    Each entry is stored as ``(value, expires_at)`` where ``expires_at`` is
    a monotonic timestamp after which the entry is considered stale.
    """

    __slots__ = ("_store",)

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Return the number of entries currently in the cache (including expired)."""
        return len(self._store)

    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` if missing/expired.

        Expired entries are evicted on read so stale data is never returned.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            logger.debug("Cache key %r expired — evicted", key)
            return None

        logger.debug("Cache HIT for key %r", key)
        return value

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        """Store *value* under *key* with the given *ttl* in seconds.

        A *ttl* of 0 or negative still stores the entry but it will be
        evicted on the very next ``get()`` call.
        """
        expires_at = time.monotonic() + max(ttl, 0)
        self._store[key] = (value, expires_at)
        logger.debug("Cache SET key=%r ttl=%ds", key, ttl)

    def invalidate(self, key: str) -> None:
        """Remove a single key from the cache (no-op if missing)."""
        if key in self._store:
            del self._store[key]
            logger.debug("Cache INVALIDATE key=%r", key)

    def invalidate_guild(self, guild_id: str) -> None:
        """Remove every key that starts with ``{guild_id}:``."""
        prefix = f"{guild_id}:"
        to_remove = [k for k in self._store if k.startswith(prefix)]
        for key in to_remove:
            del self._store[key]
        if to_remove:
            logger.debug(
                "Cache INVALIDATE guild=%s — removed %d keys",
                guild_id,
                len(to_remove),
            )
