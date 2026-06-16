"""TTLCache — dict-based in-memory cache with per-key TTL expiration.

Keys follow the convention ``{guild_id}:{entity}`` to enable guild-scoped
invalidation via ``invalidate_guild()``.

Default TTL is 300 seconds (5 minutes), matching the cache desync window
defined in the architecture decisions.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300  # seconds


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
