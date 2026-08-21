"""RED tests for greeting_db explicit cols + 23505 handling (PR1 task 6.1).

Asserts:
- ``get_greeting_config`` uses an explicit column list, not ``select("*")``.
- ``upsert_greeting_config`` resolves a 23505 (unique_violation) race by
  treating the duplicate write as a no-op / re-read (no traceback to caller).
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from bot.core.database import Database
from bot.models.greeting_config import GreetingConfig
from tests.test_database import FakeQueryBuilder, FakeSupabaseClient


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def db(fake_client: FakeSupabaseClient) -> Database:
    database = Database(url="https://test.supabase.co", key="test-key")
    database._client = fake_client
    return database


class TestGreetingDbExplicitColumns:
    """6.1 — get_greeting_config must not use select('*')."""

    def test_get_greeting_config_uses_explicit_columns(self) -> None:
        from bot.core.db import greeting_db

        src = inspect.getsource(greeting_db.GreetingDBMixin.get_greeting_config)
        # The select() call must NOT be select("*").
        assert 'select("*")' not in src and "select('*')" not in src, (
            "get_greeting_config must use an explicit column list, not select('*')"
        )
        # Must reference a real column (guildId) explicitly.
        assert "guildId" in src


class TestUpsert23505Idempotent:
    """6.1 — 23505 on upsert is handled, not raised to caller."""

    @pytest.mark.asyncio
    async def test_upsert_23505_is_swallowed_and_reread(self, db: Database) -> None:
        """A 23505 unique_violation on upsert must not propagate as a traceback.

        The handler treats it as a concurrent-writer race: the row exists with
        the same key, so the upsert is effectively a no-op and the caller sees
        no exception.
        """
        cfg = GreetingConfig(guild_id="g1", welcome_enabled=True)

        # Build a fake client whose upsert().execute() raises 23505 once.
        class _RaisingExecuteBuilder(FakeQueryBuilder):
            def __init__(self) -> None:
                super().__init__()
                self._raised = False

            async def execute(self) -> MagicMock:
                if not self._raised:
                    self._raised = True
                    # supabase-py raises PostgrestAPIError; emulate via exception carrying .code
                    raise _make_23505_error()
                resp = MagicMock()
                resp.data = [{"guildId": "g1", "welcomeEnabled": True}]
                return resp

        fake = FakeSupabaseClient()
        fake._tables["greeting_config"] = _RaisingExecuteBuilder()
        db._client = fake

        # Should not raise.
        await db.upsert_greeting_config("g1", cfg)

    @pytest.mark.asyncio
    async def test_upsert_non_23505_error_propagates(self, db: Database) -> None:
        """A non-23505 error must still propagate to the caller."""
        cfg = GreetingConfig(guild_id="g1", welcome_enabled=True)

        class _RaisingExecuteBuilder(FakeQueryBuilder):
            async def execute(self) -> MagicMock:
                raise RuntimeError("some other db error")

        fake = FakeSupabaseClient()
        fake._tables["greeting_config"] = _RaisingExecuteBuilder()
        db._client = fake

        with pytest.raises(RuntimeError, match="some other db error"):
            await db.upsert_greeting_config("g1", cfg)


def _make_23505_error() -> Exception:
    """Build an exception that mimics supabase-py's PostgrestAPIError with code 23505."""
    # supabase-py raises PostgrestAPIError; we emulate with a generic exception
    # carrying the code attribute the handler inspects.
    err = RuntimeError("duplicate key value violates unique constraint")
    err.code = "23505"  # type: ignore[attr-defined]
    return err
