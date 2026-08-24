"""RED: TicketsCog facade over 4 flow modules (S3.4A) — Strict TDD."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.cogs.tickets import TicketsCog


@pytest.fixture
def cog_bot(mock_db) -> MagicMock:
    bot = MagicMock()
    bot.db = mock_db
    bot.db.get_ticket_by_channel = AsyncMock(return_value=None)
    bot.db.get_ticket = AsyncMock(return_value=None)
    bot.db.get_ticket_category = AsyncMock(return_value=None)
    bot.db.get_ticket_categories = AsyncMock(return_value=[])
    bot.ticket_service = MagicMock()
    bot.ticket_service.create_ticket_channel = AsyncMock()
    bot.ticket_service.reopen_ticket = AsyncMock()
    bot.ticket_service.transfer_ticket = AsyncMock()
    bot.ticket_service.unclaim_ticket = AsyncMock()
    bot.ticket_service.create_note = AsyncMock()
    bot.ticket_service.get_notes = AsyncMock(return_value=[])
    bot.ticket_service.delete_note = AsyncMock()
    bot.ticket_service.sweep_integrity = AsyncMock(return_value=[])
    bot.ticket_service.repair_ticket_by_ref = AsyncMock(return_value=None)
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(ticket_category_id="1", mod_role_id=None))
    bot.guilds = []
    return bot


def test_cog_imports_four_flow_modules() -> None:
    """TicketsCog facade MUST import 4 flow modules (admin/lifecycle/notes/integrity)."""
    # Each flow module must be importable as bot.cogs.ticket_*_flow
    import bot.cogs.ticket_admin_flow as m1
    import bot.cogs.ticket_integrity_flow as m4
    import bot.cogs.ticket_lifecycle_flow as m2
    import bot.cogs.ticket_notes_flow as m3

    for mod in (m1, m2, m3, m4):
        assert mod is not None
    # Each must expose its flow class
    assert hasattr(m1, "TicketAdminFlow")
    assert hasattr(m2, "TicketLifecycleFlow")
    assert hasattr(m3, "TicketNotesFlow")
    assert hasattr(m4, "TicketIntegrityFlow")


def test_cog_facade_has_four_flow_attributes(cog_bot: MagicMock) -> None:
    """TicketsCog MUST expose 4 flow attributes via composition."""
    cog = TicketsCog(cog_bot)
    assert hasattr(cog, "_admin_flow")
    assert hasattr(cog, "_lifecycle_flow")
    assert hasattr(cog, "_notes_flow")
    assert hasattr(cog, "_integrity_flow")
    from bot.cogs.ticket_admin_flow import TicketAdminFlow
    from bot.cogs.ticket_integrity_flow import TicketIntegrityFlow
    from bot.cogs.ticket_lifecycle_flow import TicketLifecycleFlow
    from bot.cogs.ticket_notes_flow import TicketNotesFlow

    assert isinstance(cog._admin_flow, TicketAdminFlow)
    assert isinstance(cog._lifecycle_flow, TicketLifecycleFlow)
    assert isinstance(cog._notes_flow, TicketNotesFlow)
    assert isinstance(cog._integrity_flow, TicketIntegrityFlow)


def test_cog_preserves_async_setup() -> None:
    """setup(bot) MUST remain async def setup(bot) and register TicketsCog once."""
    from bot.cogs.tickets import setup

    assert inspect.iscoroutinefunction(setup)
    assert "async def setup" in inspect.getsource(setup)
    assert "add_cog" in inspect.getsource(setup)


def test_cog_preserves_hybrid_command_names(cog_bot: MagicMock) -> None:
    """Hybrid command names MUST survive extraction (ticket_panel, create_category, etc)."""
    cog = TicketsCog(cog_bot)
    # Top-level hybrid commands/groups via cog.__cog_commands__ and walk
    names = {cmd.name for cmd in cog.__cog_commands__}
    # discord.py stores hybrid commands in __cog_commands__ and app_commands
    # Also check via cog.walk_commands()
    all_names = {c.name for c in cog.walk_commands()}
    # Also check directly via cog's app_commands
    app_names = {c.name for c in cog.get_app_commands() if hasattr(c, "name")}
    combined = names | all_names | app_names
    for expected in (
        "ticket_panel",
        "create_category",
        "list_categories",
        "delete_category",
        "configure_fields",
        "subticket",
        "reopen",
        "transfer",
        "unclaim",
        "note",
        "sweep_integrity",
        "repair_ticket",
    ):
        assert expected in combined, f"missing command {expected} — got {combined}"
    # Subcommands
    # configure_fields -> set, subticket -> create, note -> add/list/delete
    assert "set" in combined or any("set" in n for n in combined)
    # Check children via walk
    child_names = set()
    for cmd in cog.walk_commands():
        child_names.add(cmd.name)
        if hasattr(cmd, "commands"):
            for sub in cmd.commands:  # type: ignore[attr-defined]
                child_names.add(sub.name)
    for sub in ("create", "add", "list", "delete", "set"):
        assert sub in child_names, f"missing subcommand {sub}"


@pytest.mark.asyncio
async def test_facade_ticket_panel_delegates_once(cog_bot: MagicMock) -> None:
    """ticket_panel MUST delegate exactly once to admin flow."""
    cog = TicketsCog(cog_bot)
    mock_admin = MagicMock()
    mock_admin.ticket_panel = AsyncMock()
    cog._admin_flow = mock_admin
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.ticket_panel.callback(cog, ctx, title=None, description_text=None)
    mock_admin.ticket_panel.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_create_category_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_admin = MagicMock()
    mock_admin.create_category = AsyncMock()
    cog._admin_flow = mock_admin
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.create_category.callback(cog, ctx, name="Support")
    mock_admin.create_category.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_subticket_create_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_lc = MagicMock()
    mock_lc.subticket_create = AsyncMock()
    cog._lifecycle_flow = mock_lc
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.subticket_create.callback(cog, ctx, parent_id=None)
    mock_lc.subticket_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_reopen_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_lc = MagicMock()
    mock_lc.reopen = AsyncMock()
    cog._lifecycle_flow = mock_lc
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.reopen.callback(cog, ctx, ticket_ref=None)
    mock_lc.reopen.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_transfer_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_lc = MagicMock()
    mock_lc.transfer = AsyncMock()
    cog._lifecycle_flow = mock_lc
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    member = MagicMock(spec=discord.Member)
    await cog.transfer.callback(cog, ctx, member=member)
    mock_lc.transfer.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_unclaim_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_lc = MagicMock()
    mock_lc.unclaim = AsyncMock()
    cog._lifecycle_flow = mock_lc
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.unclaim.callback(cog, ctx)
    mock_lc.unclaim.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_note_add_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_notes = MagicMock()
    mock_notes.note_add = AsyncMock()
    cog._notes_flow = mock_notes
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.note_add.callback(cog, ctx, content="hello")
    mock_notes.note_add.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_sweep_integrity_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_int = MagicMock()
    mock_int.sweep_integrity = AsyncMock()
    cog._integrity_flow = mock_int
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.sweep_integrity.callback(cog, ctx)
    mock_int.sweep_integrity.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_repair_ticket_delegates_once(cog_bot: MagicMock) -> None:
    cog = TicketsCog(cog_bot)
    mock_int = MagicMock()
    mock_int.repair_ticket = AsyncMock()
    cog._integrity_flow = mock_int
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    await cog.repair_ticket.callback(cog, ctx, ticket_ref="#0001")
    mock_int.repair_ticket.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifecycle_guild_scoping_568_cross_guild_denied(cog_bot: MagicMock) -> None:
    """568/685/722: cross-guild channel lookup MUST be denied (guild_id scoped)."""
    # This tests the real flow implementation, not the mock delegation path
    # Use the real lifecycle flow without mocking
    cog = TicketsCog(cog_bot)
    # For 568,685,722 the code path is via get_ticket_by_channel with guild_id=gid
    # The lifecycle flow's subticket_create should call get_ticket_by_channel with correct gid
    # We test the helper resolve path via transfer which does guild-scoped lookup
    cog_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)
    # Use transfer flow: it looks up by channel with gid; if row is None -> not_ticket
    ctx = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    ctx.guild = guild
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 111111111
    ctx.channel = MagicMock()
    ctx.channel.id = 444444444
    ctx.send = AsyncMock()
    member = MagicMock(spec=discord.Member)
    # transfer with no ticket should return not_ticket, not mutate
    await cog._lifecycle_flow.transfer(ctx, member=member)
    cog_bot.db.get_ticket_by_channel.assert_awaited()
    call_kwargs = cog_bot.db.get_ticket_by_channel.call_args
    # must be called with guild_id scoped to invoking guild
    assert call_kwargs is not None
    args, kwargs = call_kwargs
    assert kwargs.get("guild_id") == "123456789" or (len(args) > 1 and args[1] == "123456789")
