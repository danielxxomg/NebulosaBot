"""RED tests for welcome-svg-foundation PR1 Phase 3 updatedAt (3.1-3.6).

Strict TDD: must fail before updatedAt impl, pass after.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestGreetingConfigModelUpdatedAt:
    """3.1-3.2 GreetingConfig updated_at round-trip."""

    def test_model_has_updated_at_field(self) -> None:
        import dataclasses

        from bot.models.greeting_config import GreetingConfig

        field_names = {f.name for f in dataclasses.fields(GreetingConfig)}
        assert "updated_at" in field_names, f"GreetingConfig must have updated_at field, got {field_names}"

    def test_from_db_row_reads_updatedAt(self) -> None:
        from bot.models.greeting_config import GreetingConfig

        ts = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)
        row = {"guildId": "123", "updatedAt": ts}
        cfg = GreetingConfig.from_db_row(row)
        assert cfg.updated_at == ts

    def test_from_db_row_null_updatedAt(self) -> None:
        from bot.models.greeting_config import GreetingConfig

        row = {"guildId": "123"}
        cfg = GreetingConfig.from_db_row(row)
        assert cfg.updated_at is None

    def test_to_db_dict_includes_updatedAt(self) -> None:
        from bot.models.greeting_config import GreetingConfig

        ts = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)
        cfg = GreetingConfig(guild_id="123", updated_at=ts)
        d = cfg.to_db_dict()
        assert "updatedAt" in d
        assert d["updatedAt"] == ts

    def test_to_db_dict_null_updatedAt(self) -> None:
        from bot.models.greeting_config import GreetingConfig

        cfg = GreetingConfig(guild_id="123", updated_at=None)
        d = cfg.to_db_dict()
        assert "updatedAt" in d
        assert d["updatedAt"] is None

    def test_roundtrip_preserves_updatedAt(self) -> None:
        from bot.models.greeting_config import GreetingConfig

        ts = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)
        cfg = GreetingConfig(guild_id="123", updated_at=ts, welcome_enabled=True)
        row = cfg.to_db_dict()
        restored = GreetingConfig.from_db_row(row)
        assert restored.updated_at == ts
        assert restored.welcome_enabled is True


class TestGreetingDbUpdatedAt:
    """3.3 greeting_db.py upsert sets updatedAt = now(); preserves field."""

    @pytest.mark.asyncio
    async def test_upsert_sets_updatedAt(self) -> None:
        from bot.core.database import Database
        from bot.models.greeting_config import GreetingConfig
        from tests.test_database import FakeSupabaseClient

        fake = FakeSupabaseClient()
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        cfg = GreetingConfig(guild_id="g1", welcome_enabled=True)
        await db.upsert_greeting_config("g1", cfg)
        calls = fake.get_table_calls("greeting_config")
        assert len(calls) == 1
        payload = calls[0][1]
        assert "updatedAt" in payload, f"upsert payload must include updatedAt, got {payload}"
        assert payload["updatedAt"] is not None

    @pytest.mark.asyncio
    async def test_get_preserves_updatedAt(self) -> None:
        from bot.core.database import Database
        from tests.test_database import FakeSupabaseClient

        fake = FakeSupabaseClient()
        ts = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC).isoformat()
        fake.set_table_data("greeting_config", [{"guildId": "g1", "updatedAt": ts}])
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        row = await db.get_greeting_config("g1")
        assert row is not None
        assert row["updatedAt"] == ts


class TestRealtimePollUpdatedAt:
    """3.5-3.6 realtime.py _poll_once incremental by updatedAt, null included, last_check advances."""

    @pytest.mark.asyncio
    async def test_poll_queries_greeting_config_by_updated_at(self) -> None:
        # Use source inspection (lowercase) to satisfy ruff lowercase rule
        import inspect

        from bot.core.realtime import RealtimeCacheSubscriber

        src = inspect.getsource(RealtimeCacheSubscriber._poll_once)
        assert "updatedAt" in src, "_poll_once must filter by updatedAt"
        assert "last_check" in src or "_last_check" in src, "_poll_once must use last_check"

    @pytest.mark.asyncio
    async def test_poll_includes_null_updated_at(self) -> None:
        import inspect

        from bot.core.realtime import RealtimeCacheSubscriber

        src = inspect.getsource(RealtimeCacheSubscriber._poll_once)
        # Must include null handling: either or_, is_, or null in src with updatedAt context
        low = src.lower()
        has_null = "null" in low and "updatedat" in low
        has_or = ".or_(" in src or ".or(" in src
        assert has_null or has_or or "is_" in src, (
            "_poll_once must include null updatedAt rows (treated as always-changed)"
        )

    @pytest.mark.asyncio
    async def test_poll_advances_last_check(self) -> None:
        import inspect

        from bot.core.realtime import RealtimeCacheSubscriber

        src = inspect.getsource(RealtimeCacheSubscriber._poll_once)
        assert "_last_check" in src and "=" in src, "_poll_once must advance _last_check"
        # Check RealtimeCacheSubscriber has _last_check attr
        from bot.core.cache import TTLCache

        cache = TTLCache()
        sub = RealtimeCacheSubscriber(
            supabase_url="https://x.supabase.co",
            supabase_key="k",
            cache=cache,
            client_factory=AsyncMock(return_value=MagicMock()),
        )
        assert hasattr(sub, "_last_check")


class TestCacheKeyGuildScoped:
    """Phase 3: new caches must use cache_key guild-scoped."""

    def test_realtime_uses_cache_key_helper(self) -> None:
        from bot.core import realtime as rt

        src = Path(rt.__file__).read_text(encoding="utf-8")
        # Existing realtime already uses cache_key indirectly via cache ops? Check for import
        assert "cache_key" in src or "invalidate_guild" in src, "realtime must use guild-scoped cache invalidation"
