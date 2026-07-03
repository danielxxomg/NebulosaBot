"""Unit tests for bot.core.cache.TTLCache.

Covers the cache-layer spec scenarios:
    - get/set round-trip
    - cache miss on unknown key
    - TTL expiry eviction
    - single-key invalidation
    - guild-scoped invalidation
    - guild isolation (guild A keys do not affect guild B)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bot.core.cache import DEFAULT_TTL, TTLCache

# ---------------------------------------------------------------------------
# get / set round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_set_round_trip(cache: TTLCache) -> None:
    """A value stored via set() MUST be retrievable via get()."""
    cache.set("foo", "bar")
    assert cache.get("foo") == "bar"


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(cache: TTLCache) -> None:
    """get() on an unknown key MUST return None."""
    assert cache.get("nonexistent") is None


@pytest.mark.asyncio
async def test_set_then_overwrite(cache: TTLCache) -> None:
    """set() on an existing key MUST overwrite the previous value."""
    cache.set("key", "old")
    cache.set("key", "new")
    assert cache.get("key") == "new"


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ttl_expiry_evicts_on_read(cache: TTLCache) -> None:
    """After TTL seconds elapse, get() MUST return None and evict the entry."""
    fake_now = 1000.0

    with patch("bot.core.cache.time.monotonic", return_value=fake_now):
        cache.set("ephemeral", "data", ttl=10)
        # Entry exists before expiry.
        assert cache.get("ephemeral") == "data"

    # Advance time past the TTL window.
    with patch("bot.core.cache.time.monotonic", return_value=fake_now + 11):
        assert cache.get("ephemeral") is None


@pytest.mark.asyncio
async def test_zero_ttl_expires_immediately(cache: TTLCache) -> None:
    """A TTL of 0 MUST cause the entry to expire on the very next get()."""
    cache.set("transient", "value", ttl=0)
    # Even with the same monotonic timestamp the entry expires because
    # monotonic has moved forward at least a tick.
    assert cache.get("transient") is None


@pytest.mark.asyncio
async def test_default_ttl_is_300(cache: TTLCache) -> None:
    """When no ttl is passed, the default of 300 seconds MUST be used."""
    # Verify the constant.
    assert DEFAULT_TTL == 300

    fake_now = 500.0

    with patch("bot.core.cache.time.monotonic", return_value=fake_now):
        cache.set("persistent", "data")
        assert cache.get("persistent") == "data"

    # Still valid inside the window.
    with patch("bot.core.cache.time.monotonic", return_value=fake_now + 299):
        assert cache.get("persistent") == "data"

    # Expired after 301 seconds.
    with patch("bot.core.cache.time.monotonic", return_value=fake_now + 301):
        assert cache.get("persistent") is None


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_removes_key(cache: TTLCache) -> None:
    """invalidate() MUST remove the entry so a subsequent get() returns None."""
    cache.set("target", "value")
    cache.invalidate("target")
    assert cache.get("target") is None


@pytest.mark.asyncio
async def test_invalidate_missing_key_noop(cache: TTLCache) -> None:
    """invalidate() on a non-existent key MUST be a no-op (no error)."""
    cache.invalidate("does-not-exist")  # Must not raise.


# ---------------------------------------------------------------------------
# Guild-scoped invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_guild_removes_all_guild_keys(cache: TTLCache) -> None:
    """invalidate_guild() MUST remove every key starting with ``{guild_id}:``."""
    guild_id = "111222333"

    cache.set(f"{guild_id}:config", "cfg")
    cache.set(f"{guild_id}:mod_role", "role")
    cache.set("global:setting", "val")  # unrelated key

    cache.invalidate_guild(guild_id)

    assert cache.get(f"{guild_id}:config") is None
    assert cache.get(f"{guild_id}:mod_role") is None
    assert cache.get("global:setting") == "val"  # untouched


@pytest.mark.asyncio
async def test_invalidate_guild_empty_noop(cache: TTLCache) -> None:
    """invalidate_guild() with no matching keys MUST be a no-op."""
    cache.set("other:key", "value")
    cache.invalidate_guild("999")
    assert cache.get("other:key") == "value"


# ---------------------------------------------------------------------------
# Guild isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guild_isolation(cache: TTLCache) -> None:
    """Keys from guild A MUST NOT affect guild B keys and vice versa."""
    guild_a = "111"
    guild_b = "222"

    cache.set(f"{guild_a}:config", "A-cfg")
    cache.set(f"{guild_b}:config", "B-cfg")

    # Each guild retrieves its own value.
    assert cache.get(f"{guild_a}:config") == "A-cfg"
    assert cache.get(f"{guild_b}:config") == "B-cfg"

    # Invalidating guild A must not touch guild B.
    cache.invalidate_guild(guild_a)

    assert cache.get(f"{guild_a}:config") is None
    assert cache.get(f"{guild_b}:config") == "B-cfg"
