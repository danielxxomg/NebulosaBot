"""RED for PR2 2.1-2.2 expired-scan DB queries (strict TDD — must fail before GREEN)."""

from __future__ import annotations

import pytest

from bot.core.database import Database
from tests.test_database import FakeQueryBuilder, FakeSupabaseClient

# ------------------------------------------------------------------
# 2.1 get_expired_warns
# ------------------------------------------------------------------


class TestGetExpiredWarnsRed:
    @pytest.mark.asyncio
    async def test_get_expired_warns_exists_and_filters(self, monkeypatch) -> None:
        """2.1: get_expired_warns(guild_id) returns only WARN active createdAt<NOW()-30d guild-scoped."""
        # Ensure lte/lt exist on FakeQueryBuilder for this test file too (patched if missing)

        if not hasattr(FakeQueryBuilder, "lte"):

            def _lte(self, column, value):
                self._filters.append(("lte", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "lte", _lte, raising=False)
        if not hasattr(FakeQueryBuilder, "not_"):
            # Mirrors postgrest-py: ``not_`` is a property namespace exposing
            # ``is_()``; on this fake the same recorder serves both.
            _not_ns = property(lambda self: self)

            monkeypatch.setattr(FakeQueryBuilder, "not_", _not_ns, raising=False)
        if not hasattr(FakeQueryBuilder, "is_"):

            def _is(self, column, value):
                self._filters.append(("not.is", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "is_", _is, raising=False)
        fake = FakeSupabaseClient()
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        # Must exist
        assert hasattr(db, "get_expired_warns"), "InfractionDBMixin.get_expired_warns must exist"
        # Call and prove guild-scoped filter + type WARN + active True + lt createdAt
        fake.set_table_data(
            "infraction",
            [
                {
                    "id": "old1",
                    "guildId": "g1",
                    "type": "WARN",
                    "active": True,
                    "createdAt": "2024-01-01T00:00:00+00:00",
                },
            ],
        )
        result = await db.get_expired_warns("g1")
        assert isinstance(result, list)
        filters = fake.get_table_filters("infraction")
        assert ("eq", "guildId", "g1") in filters, f"guild-scoped eq failed: {filters}"
        assert ("eq", "type", "WARN") in filters
        assert ("eq", "active", True) in filters
        # Must filter by createdAt < cutoff (lt)
        assert any(f[0] == "lt" and f[1] == "createdAt" for f in filters), f"missing lt createdAt: {filters}"
        # Must use explicit cols, not select("*")
        # We cannot easily capture select arg via Fake, but ensure method exists and filters above
        assert len(result) == 1
        assert result[0]["id"] == "old1"

    @pytest.mark.asyncio
    async def test_get_expired_warns_future_not_returned_via_filters(self, monkeypatch) -> None:
        """Future WARN must be excluded by lt cutoff — proven via filter, not data."""

        if not hasattr(FakeQueryBuilder, "lte"):

            def _lte(self, column, value):
                self._filters.append(("lte", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "lte", _lte, raising=False)
        fake = FakeSupabaseClient()
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        assert hasattr(db, "get_expired_warns")
        fake.set_table_data("infraction", [])
        await db.get_expired_warns("g1")
        filters = fake.get_table_filters("infraction")
        assert any(f[0] == "lt" for f in filters)

    @pytest.mark.asyncio
    async def test_get_expired_warns_raises_without_connect(self) -> None:
        db = Database(url="https://test.supabase.co", key="test-key")
        with pytest.raises(RuntimeError, match="connect"):
            await db.get_expired_warns("g1")


# ------------------------------------------------------------------
# 2.2 get_expired_tempbans
# ------------------------------------------------------------------


class TestGetExpiredTempbansRed:
    @pytest.mark.asyncio
    async def test_get_expired_tempbans_exists_and_filters(self, monkeypatch) -> None:
        """2.2: get_expired_tempbans returns only BAN active expiresAt<=NOW guild-scoped."""

        if not hasattr(FakeQueryBuilder, "lte"):

            def _lte(self, column, value):
                self._filters.append(("lte", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "lte", _lte, raising=False)
        if not hasattr(FakeQueryBuilder, "not_"):
            # Mirrors postgrest-py: ``not_`` is a property namespace exposing
            # ``is_()``; on this fake the same recorder serves both.
            _not_ns = property(lambda self: self)

            monkeypatch.setattr(FakeQueryBuilder, "not_", _not_ns, raising=False)
        if not hasattr(FakeQueryBuilder, "is_"):

            def _is(self, column, value):
                self._filters.append(("not.is", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "is_", _is, raising=False)
        fake = FakeSupabaseClient()
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        assert hasattr(db, "get_expired_tempbans"), "InfractionDBMixin.get_expired_tempbans must exist"
        fake.set_table_data(
            "infraction",
            [
                {
                    "id": "ban-old",
                    "guildId": "g1",
                    "type": "BAN",
                    "active": True,
                    "expiresAt": "2024-01-01T00:00:00+00:00",
                },
            ],
        )
        result = await db.get_expired_tempbans("g1")
        assert isinstance(result, list)
        filters = fake.get_table_filters("infraction")
        assert ("eq", "guildId", "g1") in filters
        assert ("eq", "type", "BAN") in filters
        assert ("eq", "active", True) in filters
        # expiresAt <= NOW  → lte (with lt fallback tolerated)
        assert any(f[0] in ("lte", "lt") and f[1] == "expiresAt" for f in filters), (
            f"missing lte/lt expiresAt: {filters}"
        )
        # clean-1.0 S0.2: permanent bans excluded via null-safe not.is — the
        # old neq(None) serialized into PostgREST 22007 and MUST NOT return.
        assert ("not.is", "expiresAt", "null") in filters, f"missing null-safe not.is filter: {filters}"
        assert all(f[0] != "neq" for f in filters), f"invalid neq filter present: {filters}"
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_expired_tempbans_future_excluded(self, monkeypatch) -> None:

        if not hasattr(FakeQueryBuilder, "lte"):

            def _lte(self, column, value):
                self._filters.append(("lte", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "lte", _lte, raising=False)
        if not hasattr(FakeQueryBuilder, "not_"):
            # Mirrors postgrest-py: ``not_`` is a property namespace exposing
            # ``is_()``; on this fake the same recorder serves both.
            _not_ns = property(lambda self: self)

            monkeypatch.setattr(FakeQueryBuilder, "not_", _not_ns, raising=False)
        if not hasattr(FakeQueryBuilder, "is_"):

            def _is(self, column, value):
                self._filters.append(("not.is", column, value))
                return self

            monkeypatch.setattr(FakeQueryBuilder, "is_", _is, raising=False)
        fake = FakeSupabaseClient()
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        assert hasattr(db, "get_expired_tempbans")
        fake.set_table_data("infraction", [])
        await db.get_expired_tempbans("g1")
        filters = fake.get_table_filters("infraction")
        assert any(f[1] == "expiresAt" for f in filters), f"must filter expiresAt, got {filters}"
        # clean-1.0 S0.2: future/permanent exclusion uses the null-safe wire format.
        assert ("not.is", "expiresAt", "null") in filters, f"missing null-safe not.is filter: {filters}"

    @pytest.mark.asyncio
    async def test_get_expired_tempbans_raises_without_connect(self) -> None:
        db = Database(url="https://test.supabase.co", key="test-key")
        with pytest.raises(RuntimeError, match="connect"):
            await db.get_expired_tempbans("g1")
