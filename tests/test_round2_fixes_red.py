# ruff: noqa: S311
"""RED tests for NebulosaBot quick-wins ROUND 2 — 3 GGA blockers.

Strict TDD: these tests MUST FAIL before the fixes are applied, then pass.

Covers:
- Fix 1 — can_check prefix deny MUST raise commands.CheckFailure (not
  app_commands.CheckFailure), so discord.py routes the denial to
  on_command_error and the user gets a message. The slash path keeps
  raising app_commands.CheckFailure.
- Fix 2 — scheduled-close field clears MUST NOT silently swallow DB
  write failures via contextlib.suppress(Exception); a warning/error
  MUST be logged while keeping the close flow intact (best-effort).
  Sites: ticket_lifecycle_service.close_ticket (both branches),
  ticket_repair_service.close_ticket_full, tickets cog
  _close_due_scheduled_ticket, and _fetch_active_ticket_row fallback miss.
- Fix 3 — OcioService.get_random_banana pool glob MUST run off the event
  loop via asyncio.to_thread (sorted for determinism).
"""

from __future__ import annotations

import inspect
import logging
import operator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.models.ticket import Ticket
from bot.services.ticket_lifecycle_service import TicketLifecycleService
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService
from bot.utils.checks import can_check

# ===========================================================================
# Fix 1 — can_check prefix predicate raises the WRONG exception type
# ===========================================================================


def _make_member_with_roles(
    guild_id: int,
    role_ids: list[int],
    *,
    administrator: bool = False,
) -> MagicMock:
    """Build a discord.Member mock for can_check predicate tests."""
    m = MagicMock(spec=discord.Member)
    m.__class__ = discord.Member
    m.guild_permissions.administrator = administrator
    m.id = 111222333
    m.guild = MagicMock()
    m.guild.id = guild_id
    roles = []
    for rid in role_ids:
        r = MagicMock(spec=discord.Role)
        r.id = rid
        roles.append(r)
    m.roles = roles
    return m


def _make_ctx(guild: MagicMock | None, member: MagicMock) -> MagicMock:
    """Build a commands.Context mock for can_check prefix tests."""
    ctx = MagicMock(spec=commands.Context)
    ctx.guild = guild
    ctx.author = member
    ctx.bot = MagicMock()
    ctx.bot._guild_mod_role_cache = {}
    return ctx


@pytest.mark.asyncio
async def test_can_check_prefix_deny_raises_commands_check_failure() -> None:
    """Fix 1 RED: can_check prefix deny MUST raise commands.CheckFailure.

    app_commands.CheckFailure does NOT derive from commands.CommandError, so
    discord.py's Bot.invoke never routes it to on_command_error — the denied
    prefix user gets no message plus a raw traceback. The prefix path MUST
    raise commands.CheckFailure (sibling is_mod() uses _commands.* exceptions).
    """
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    member = _make_member_with_roles(guild.id, [123])  # no grant
    ctx = _make_ctx(guild, member)

    cfg = MagicMock(permission_matrix={"moderation.ban": ["9999"]}, mod_role_id="777")
    with patch("bot.utils.checks._get_guild_service") as gs_mock:
        gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
        prefix_predicate = can_check("moderation.ban").prefix_predicate
        with pytest.raises(commands.CheckFailure) as exc:
            await prefix_predicate(ctx)

    # CRITICAL — the raised exception MUST be commands.CheckFailure, NOT
    # app_commands.CheckFailure. commands.CheckFailure is NOT a subclass of
    # app_commands.CheckFailure, so this assertion documents the fix.
    assert isinstance(exc.value, commands.CheckFailure)
    assert not isinstance(exc.value, app_commands.CheckFailure), (
        "prefix deny MUST raise commands.CheckFailure, not app_commands.CheckFailure"
    )
    assert "Missing permission: moderation.ban" in str(exc.value)


@pytest.mark.asyncio
async def test_can_check_slash_deny_still_raises_app_commands_check_failure() -> None:
    """Fix 1 RED: can_check slash path MUST keep raising app_commands.CheckFailure.

    The fix is prefix-only; the slash path is correct as-is and must not regress.
    """
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.guild_id = guild.id
    interaction.user = _make_member_with_roles(guild.id, [123])
    interaction.client = MagicMock()
    interaction.client._guild_mod_role_cache = {}

    cfg = MagicMock(permission_matrix={"moderation.ban": ["9999"]}, mod_role_id="777")
    with patch("bot.utils.checks._get_guild_service") as gs_mock:
        gs_mock.return_value.get_config = AsyncMock(return_value=cfg)
        app_predicate = can_check("moderation.ban").predicate
        with pytest.raises(app_commands.CheckFailure) as exc:
            await app_predicate(interaction)

    assert isinstance(exc.value, app_commands.CheckFailure)
    assert "Missing permission: moderation.ban" in str(exc.value)


# ===========================================================================
# Fix 2 — contextlib.suppress(Exception) silently swallows DB-write failures
# ===========================================================================


def _closed_row(row: dict) -> dict:
    return {**row, "status": "closed", "closedAt": "2026-08-22T12:00:00+00:00"}


def _open_row() -> dict:
    return {
        "id": "lifecycle-uuid-0001",
        "ticketNumber": 7,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
    }


def _lifecycle(mock_db: AsyncMock) -> TicketLifecycleService:
    return TicketLifecycleService(db=mock_db, query=MagicMock(spec=TicketQueryService))


def _repair(mock_db: AsyncMock, lifecycle: TicketLifecycleService) -> TicketRepairService:
    return TicketRepairService(db=mock_db, query=MagicMock(spec=TicketQueryService), lifecycle=lifecycle)


@pytest.mark.asyncio
async def test_close_ticket_logs_when_scheduled_clear_fails(
    caplog: pytest.LogCaptureFixture, mock_db: AsyncMock
) -> None:
    """Fix 2 RED: lifecycle close_ticket MUST log when the scheduled-close
    field clear raises (was silently suppressed).

    The close flow MUST still succeed (best-effort cleanup) — the ticket
    is closed and returned — but the failure MUST be visible in logs.
    """
    row = _open_row()
    closed = _closed_row(row)
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)
    mock_db.insert_audit_row = AsyncMock(return_value=None)
    mock_db.update_ticket = AsyncMock(side_effect=RuntimeError("scheduled clear db down"))

    svc = _lifecycle(mock_db)
    with caplog.at_level(logging.ERROR, logger="bot.services.ticket_lifecycle_service"):
        ticket = await svc.close_ticket(row["id"], closed_by="999999999", guild_id=row["guildId"])

    # Close succeeded — best-effort clear MUST NOT break the flow.
    assert ticket.status == "closed"
    # The failure MUST be logged (was swallowed by suppress(Exception)).
    assert any("scheduled" in r.message.lower() or "clear" in r.message.lower() for r in caplog.records), (
        f"expected a scheduled-clear failure log, got: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_close_ticket_no_guild_id_logs_when_scheduled_clear_fails(
    caplog: pytest.LogCaptureFixture, mock_db: AsyncMock
) -> None:
    """Fix 2 RED: lifecycle close_ticket (no-guild_id fallback branch) MUST
    also log when the scheduled-close clear raises.
    """
    row = _open_row()
    closed = _closed_row(row)
    mock_db.get_ticket = AsyncMock(return_value=row)
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)
    mock_db.insert_audit_row = AsyncMock(return_value=None)
    mock_db.update_ticket = AsyncMock(side_effect=RuntimeError("scheduled clear db down"))

    svc = _lifecycle(mock_db)
    with caplog.at_level(logging.ERROR, logger="bot.services.ticket_lifecycle_service"):
        await svc.close_ticket(row["id"], closed_by="999999999")

    assert any("scheduled" in r.message.lower() or "clear" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_close_ticket_full_logs_when_scheduled_clear_fails(
    caplog: pytest.LogCaptureFixture, mock_db: AsyncMock
) -> None:
    """Fix 2 RED: repair close_ticket_full MUST log when the scheduled-close
    field clear raises (was silently suppressed).
    """
    row = _open_row()
    closed = _closed_row(row)
    mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed)
    mock_db.insert_audit_row = AsyncMock(return_value=None)
    mock_db.update_ticket = AsyncMock(side_effect=RuntimeError("scheduled clear db down"))

    # Use a real lifecycle so its close_ticket runs (TicketLifecycleService
    # uses __slots__, so we cannot stub the method). The lifecycle close will
    # also hit update_ticket on its own scheduled-clear branch — that logged
    # error is fine; the repair-path clear is the one under test here.
    lifecycle = _lifecycle(mock_db)
    repair = _repair(mock_db, lifecycle)

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 888888888
    channel.guild = MagicMock()
    channel.guild.id = 123456789
    channel.delete = AsyncMock()
    bot = MagicMock()
    bot.transcript_service = None
    bot.guild_service = None

    ticket = Ticket.from_db_row(row)
    with caplog.at_level(logging.ERROR, logger="bot.services.ticket_repair_service"):
        # manual=False avoids the 5s countdown (silent delete path).
        await repair.close_ticket_full(channel, ticket, "closer:1", bot=bot, manual=False)

    # The repair service MUST log its own scheduled-close clear failure.
    assert any(
        r.name == "bot.services.ticket_repair_service"
        and ("scheduled" in r.message.lower() or "clear" in r.message.lower())
        for r in caplog.records
    ), f"expected repair-service scheduled-clear failure log, got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_close_due_scheduled_ticket_logs_when_stale_clear_fails(
    caplog: pytest.LogCaptureFixture, mock_db: AsyncMock
) -> None:
    """Fix 2 RED: tickets cog _close_due_scheduled_ticket MUST log when the
    stale scheduled-field clear raises (was silently suppressed).

    The already-closed branch clears stale scheduled fields via the DB.
    """
    from bot.cogs.tickets import TicketsCog

    bot = MagicMock()
    bot.db = mock_db
    bot.ticket_service = MagicMock()

    closed_row = {**_open_row(), "status": "closed", "closedAt": "2026-08-22T12:00:00+00:00"}
    mock_db.get_ticket = AsyncMock(return_value=closed_row)
    mock_db.update_ticket = AsyncMock(side_effect=RuntimeError("stale clear db down"))

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 888888888
    bot.get_channel = MagicMock(return_value=channel)

    cog = TicketsCog(bot=bot)
    gid = "123456789"
    row = {"id": "sched-uuid-0001", "channelId": "888888888"}

    with caplog.at_level(logging.ERROR, logger="bot.cogs.tickets"):
        await cog._close_due_scheduled_ticket(gid, row)

    assert any("scheduled" in r.message.lower() or "clear" in r.message.lower() for r in caplog.records), (
        f"expected a scheduled-clear failure log, got: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_fetch_active_ticket_row_logs_when_fallback_misses(
    caplog: pytest.LogCaptureFixture, mock_db: AsyncMock
) -> None:
    """Fix 2 RED: _fetch_active_ticket_row fallback miss MUST log a warning.

    The channel-only fallback (get_active_ticket_by_channel) currently
    swallows its exception and returns None with NO logging — leaving
    the operator blind to why the timer path silently no-ops.
    """
    from bot.cogs.tickets import TicketsCog

    bot = MagicMock()
    bot.db = mock_db

    channel_id = 888888888
    gid = "123456789"
    # Primary lookup returns None, fallback raises.
    mock_db.get_ticket_by_channel = AsyncMock(return_value=None)
    mock_db.get_active_ticket_by_channel = AsyncMock(side_effect=RuntimeError("active lookup db down"))

    cog = TicketsCog(bot=bot)
    with caplog.at_level(logging.WARNING, logger="bot.cogs.tickets"):
        result = await cog._fetch_active_ticket_row(channel_id, gid)

    assert result is None
    assert any(
        "active" in r.message.lower() or "fetch" in r.message.lower() or "ticket" in r.message.lower()
        for r in caplog.records
    ), f"expected a fallback-miss warning, got: {[r.message for r in caplog.records]}"


# ===========================================================================
# Fix 3 — blocking directory glob on the event loop
# ===========================================================================


@pytest.mark.asyncio
async def test_get_random_banana_glob_runs_off_loop_thread() -> None:
    """Fix 3 RED: the pool glob MUST run off the event loop via asyncio.to_thread.

    The current code calls ``list(self._banana_dir.glob("*.webp"))`` directly
    in the async method while sibling read_bytes calls correctly use
    asyncio.to_thread. The glob is blocking filesystem I/O on the loop.

    We record the thread id on which Path.glob is invoked and assert it is
    NOT the event loop's thread — proving the glob ran inside a worker
    thread dispatched by asyncio.to_thread, not inline on the loop.
    """
    import threading

    from bot.services.ocio_service import OcioService

    svc = OcioService(banana_dir=Path("assets/images/banana"))
    loop_thread_id = threading.get_ident()

    glob_thread_ids: list[int] = []
    fake_paths = [Path(f"assets/images/banana/banana_{i:02d}.webp") for i in range(5)]

    def _glob_spy(*_args: Any, **_kwargs: Any) -> list[Path]:
        glob_thread_ids.append(threading.get_ident())
        return fake_paths

    with (
        patch("bot.services.ocio_service.random.random", return_value=0.5),
        patch("bot.services.ocio_service.random.choice", side_effect=operator.itemgetter(0)),
        patch("bot.services.ocio_service.random.randint", return_value=12),
        patch.object(Path, "glob", side_effect=_glob_spy),
        patch.object(Path, "read_bytes", return_value=b"\x00\x01\x02fake-webp"),
    ):
        data, _filename, _cm = await svc.get_random_banana()

    assert len(data) > 0
    # The glob MUST have been invoked at least once.
    assert glob_thread_ids, "glob MUST be called to build the pool"
    # The glob MUST have run in a different thread than the event loop —
    # i.e. wrapped in asyncio.to_thread, not called inline on the loop.
    assert all(tid != loop_thread_id for tid in glob_thread_ids), (
        f"glob MUST run off the event loop thread (got loop={loop_thread_id}, glob ran on={glob_thread_ids})"
    )


def test_get_random_banana_glob_uses_to_thread_in_source() -> None:
    """Fix 3 RED (source guard): get_random_banana source MUST wrap the pool
    glob in asyncio.to_thread (sorted for deterministic order).

    A bare ``list(self._banana_dir.glob(...))`` in the method body is a
    blocking call on the event loop and violates AGENTS.md
    'No blocking I/O in event loop'.
    """
    import bot.services.ocio_service as mod

    src = inspect.getsource(mod.OcioService.get_random_banana)
    # The pool-glob line MUST be wrapped in asyncio.to_thread — i.e. the
    # glob expression MUST appear inside a to_thread(...) call, not as a
    # bare ``pool = list(self._banana_dir.glob(...))`` statement.
    # Find the bare-glob antipattern: a line assigning pool via list(...glob...)
    # that is NOT preceded on the same logical block by asyncio.to_thread.
    bare_glob = "pool = list(self._banana_dir.glob"
    bare_sorted_glob = "pool = await asyncio.to_thread(lambda: sorted(self._banana_dir.glob"
    assert bare_sorted_glob in src, (
        "pool glob MUST be wrapped as `pool = await asyncio.to_thread(lambda: sorted(self._banana_dir.glob('*.webp')))`"
    )
    # Ensure no bare (non-to_thread) glob assignment remains.
    assert bare_glob not in src or bare_sorted_glob in src
