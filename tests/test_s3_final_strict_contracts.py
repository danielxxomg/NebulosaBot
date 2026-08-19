"""S3 final remediation strict contracts — guild-scope + probe + JWT."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _StrictDB(AsyncMock):
    def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
        super().__init__(*a, **kw)
        self.get_ticket = AsyncMock(side_effect=self._gt)
        self.get_ticket_by_channel = AsyncMock(side_effect=self._gtc)
        self.update_ticket = AsyncMock(side_effect=self._ut)
        self.get_ticket_notes = AsyncMock(return_value=[])
        self.insert_ticket_note = AsyncMock(return_value={"id": "n1"})
        self.delete_ticket_note = AsyncMock(return_value=None)
        self.get_recent_notes_for_dedup = AsyncMock(return_value=[])
        self.insert_audit_row = AsyncMock(return_value={})
        self.count_user_open_tickets_in_category = AsyncMock(return_value=0)
        self.transition_ticket_to_closed = AsyncMock(return_value=None)

    async def _gt(self, tid: str, guild_id: str | None = None, **_: object):  # type: ignore[no-untyped-def]
        if guild_id is None:
            raise ValueError("guild_id required")
        return

    async def _gtc(self, cid: str, guild_id: str | None = None, **_: object):  # type: ignore[no-untyped-def]
        if guild_id is None:
            raise ValueError("guild_id required")
        return

    async def _ut(self, tid: str, **kw):  # type: ignore[no-untyped-def]
        if kw.get("guild_id") is None:
            raise ValueError("guild_id required")
        return


class TestGuildScopeStrict:
    @pytest.mark.asyncio
    async def test_create_note_requires_guild_id(self) -> None:
        from bot.services.ticket_lifecycle_service import TicketLifecycleService
        from bot.services.ticket_query_service import TicketQueryService

        db = _StrictDB()
        svc = TicketLifecycleService(db=db, query=TicketQueryService(db))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="guild_id required"):
            await svc.create_note("t1", "u1", "hello")
        with pytest.raises(ValueError, match="not found"):
            await svc.create_note("t1", "u1", "hello", guild_id="g1")

    @pytest.mark.asyncio
    async def test_get_notes_and_transfer_require_guild_id(self) -> None:
        from bot.services.ticket_lifecycle_service import TicketLifecycleService
        from bot.services.ticket_query_service import TicketQueryService

        db = _StrictDB()
        svc = TicketLifecycleService(db=db, query=TicketQueryService(db))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="guild_id required"):
            await svc.get_notes("t1")
        assert await svc.get_notes("t1", guild_id="g1") == []
        with pytest.raises(ValueError, match="guild_id required"):
            await svc.transfer_ticket("t1", new_claimed_by="u2", actor_id="u1")

    def test_view_callers_thread_guild_id(self) -> None:
        assert (
            "claim_ticket(ticket_id, staff_id, guild_id=guild_id)"
            in pathlib.Path("bot/views/ticket_actions.py").read_text()
        )
        assert "guild_id=guild_id" in pathlib.Path("bot/views/ticket_category_select.py").read_text()
        assert "guild_id=ticket.guild_id" in pathlib.Path("bot/services/ticket_repair_service.py").read_text()


class TestProbeAndJWT:
    @pytest.mark.asyncio
    async def test_probe_false_clears_client(self) -> None:
        from bot.config import ServiceRoleValidationError
        from bot.core.database import Database

        db = Database(url="https://test.supabase.co", key="sb_secret_invalid_probe")
        fail = MagicMock()
        fail.select.return_value.limit.return_value.execute = AsyncMock(side_effect=Exception("denied"))
        client = MagicMock()
        client.table.side_effect = lambda _n: fail
        with patch("bot.core.db.base.acreate_client", return_value=client), pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    def test_payload_only_rejected_sb_secret_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import base64
        import json

        from bot.config import ServiceRoleValidationError, validate_supabase_key

        def _fake(role: str) -> str:
            h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
            p = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
            return f"{h}.{p}.sig"

        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        with pytest.raises(ServiceRoleValidationError, match="signing source"):
            validate_supabase_key(_fake("service_role"))
        validate_supabase_key("sb_secret_D7RbNvrMzqq0GReF5vKIpA_test_probe_ok_12345678")
