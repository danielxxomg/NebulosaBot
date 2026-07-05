"""Unit tests for bot.cogs.tickets.TicketsCog.

Covers ticket panel, lifecycle, and background tasks:
    - TicketPanelView.open_ticket_button — category selection → channel creation
    - _CategorySelect callback — channel creation with correct permissions
    - TicketActionsView.claim_button — ticket claiming
    - TicketActionsView.close_button — transcript generation + channel deletion
    - auto_close_stale_tickets — stale ticket detection and closure
    - _build_ticket_embed — embed construction

TDD cycle: RED → GREEN — tests specify expected behavior of existing code.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.tickets import (
    TicketActionsView,
    TicketPanelView,
    TicketsCog,
    _build_ticket_embed,
    _CategorySelect,
)
from bot.models.ticket import Ticket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ticket_row(ticket_number: int = 1, status: str = "open", channel_id: str = "444444444") -> dict:
    """Return a sample ticket DB row."""
    return {
        "id": f"ticket-uuid-{ticket_number:04d}",
        "ticketNumber": ticket_number,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": channel_id,
        "categoryId": "cat-uuid-001",
        "status": status,
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": datetime.now(UTC),
        "closedAt": None,
        "lastActivity": datetime.now(UTC),
    }


def _category_row() -> dict:
    """Return a sample ticket category DB row."""
    return {
        "id": "cat-uuid-001",
        "guildId": "123456789",
        "name": "Support",
        "emoji": "🎫",
        "description": "General support",
        "position": 1,
        "active": True,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ticket_bot(mock_db) -> MagicMock:
    """Return a mock NebulosaBot for tickets tests."""
    bot = MagicMock()
    bot.db = mock_db
    bot.ticket_service = MagicMock()
    bot.ticket_service.create_ticket = AsyncMock()
    bot.ticket_service.close_ticket = AsyncMock()
    bot.ticket_service.claim_ticket = AsyncMock()
    bot.ticket_service.get_stale_tickets = AsyncMock()
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=False)
    bot.ticket_service.sync_channel_cache = MagicMock()
    bot.transcript_service = MagicMock()
    bot.transcript_service.generate = AsyncMock()
    bot.transcript_service.upload = AsyncMock()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock()
    bot.guilds = []
    return bot


@pytest.fixture
def tickets_cog(ticket_bot) -> TicketsCog:
    """Return a TicketsCog wired to the mock bot."""
    return TicketsCog(bot=ticket_bot)


@pytest.fixture
def mock_ticket_channel() -> MagicMock:
    """Return a mock TextChannel for ticket operations."""
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 444444444
    ch.name = "ticket-0001"
    ch.mention = "<#444444444>"
    ch.send = AsyncMock()
    ch.delete = AsyncMock()
    ch.edit = AsyncMock()
    return ch


@pytest.fixture
def ticket_guild(mock_ticket_channel) -> MagicMock:
    """Return a mock guild configured for ticket creation."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.create_text_channel = AsyncMock(return_value=mock_ticket_channel)
    guild.get_channel = MagicMock(return_value=mock_ticket_channel)
    guild.get_role = MagicMock(return_value=None)
    return guild


@pytest.fixture
def ticket_interaction(ticket_guild, mock_member, ticket_bot) -> MagicMock:
    """Return a mock interaction for ticket button clicks."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = ticket_guild
    interaction.user = mock_member
    interaction.user.id = 111111111
    interaction.client = ticket_bot
    interaction.guild_id = ticket_guild.id
    interaction.channel_id = 444444444
    interaction.channel = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# 3.9 — TicketPanelView + open ticket
# ---------------------------------------------------------------------------


class TestTicketPanelView:
    """Tests for TicketPanelView.open_ticket_button."""

    async def test_open_ticket_button_no_categories_shows_error(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """No categories configured → error embed sent."""
        mock_db.get_ticket_categories = AsyncMock(return_value=[])
        ticket_interaction.client = ticket_bot

        view = TicketPanelView()
        await view.open_ticket_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        call_kwargs = ticket_interaction.response.send_message.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True


class TestCategorySelect:
    """Tests for _CategorySelect callback."""

    async def test_category_select_creates_channel(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Category selection → channel created with correct permissions."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket = AsyncMock(return_value=ticket)

        select = _CategorySelect(options=[], guild=ticket_guild)
        select._values = ["cat-uuid-001"]

        with patch("bot.cogs.tickets.TicketActionsView"):
            await select.callback(ticket_interaction)

        ticket_guild.create_text_channel.assert_awaited_once()
        call_kwargs = ticket_guild.create_text_channel.call_args
        overwrites = call_kwargs.kwargs.get("overwrites")
        assert overwrites is not None

        # @everyone cannot see.
        everyone_overwrite = overwrites.get(ticket_guild.default_role)
        assert everyone_overwrite.read_messages is False

        # User can send.
        user_overwrite = overwrites.get(ticket_interaction.user)
        assert user_overwrite.read_messages is True
        assert user_overwrite.send_messages is True

    async def test_open_ticket_sends_initial_embed(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """After channel creation, initial embed sent in new channel."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket = AsyncMock(return_value=ticket)

        select = _CategorySelect(options=[], guild=ticket_guild)
        select._values = ["cat-uuid-001"]

        with patch("bot.cogs.tickets.TicketActionsView"):
            await select.callback(ticket_interaction)

        # Initial embed sent in new channel.
        mock_ticket_channel.send.assert_awaited_once()
        send_call = mock_ticket_channel.send.call_args
        assert send_call.kwargs.get("embed") is not None


# ---------------------------------------------------------------------------
# 3.10 — claim / close / auto-close
# ---------------------------------------------------------------------------


class TestTicketActionsView:
    """Tests for TicketActionsView buttons."""

    async def test_claim_button(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """Claim button → ticket claimed, interaction response sent."""
        ticket_interaction.client = ticket_bot
        ticket_row = _ticket_row(status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        ticket = Ticket.from_db_row({**ticket_row, "status": "claimed", "claimedBy": "111111111"})
        ticket_bot.ticket_service.claim_ticket = AsyncMock(return_value=ticket)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_bot.ticket_service.claim_ticket.assert_awaited_once()
        ticket_interaction.response.edit_message.assert_awaited_once()

    async def test_claim_already_claimed(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """Already claimed ticket → error embed."""
        ticket_interaction.client = ticket_bot
        ticket_row = _ticket_row(status="claimed")
        ticket_row["claimedBy"] = "999999999"
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        call_kwargs = ticket_interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert "Already Claimed" in embed.title

    async def test_close_button_generates_transcript(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Close button → transcript generated, channel deleted."""
        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel

        ticket_row = _ticket_row(status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        transcript_file = discord.File(io.BytesIO(b"<html>transcript</html>"), filename="transcript.html")
        ticket_bot.transcript_service.generate = AsyncMock(return_value=transcript_file)

        config = MagicMock()
        config.log_channel_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        ticket_bot.ticket_service.close_ticket = AsyncMock(
            return_value=Ticket.from_db_row({**ticket_row, "status": "closed"})
        )

        view = TicketActionsView()
        with patch("bot.cogs.tickets.asyncio.sleep", new_callable=AsyncMock):
            await view.close_button.callback(ticket_interaction)

        ticket_bot.transcript_service.generate.assert_awaited_once()
        ticket_bot.ticket_service.close_ticket.assert_awaited_once()
        mock_ticket_channel.delete.assert_awaited_once()


class TestAutoCloseStaleTickets:
    """Tests for auto_close_stale_tickets task."""

    async def test_auto_close_closes_stale_tickets(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """Stale tickets are closed, fresh tickets untouched."""
        ticket_bot.guilds = [ticket_guild]

        stale_ticket = MagicMock()
        stale_ticket.id = "ticket-uuid-001"
        stale_ticket.channel_id = "444444444"

        ticket_bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[stale_ticket])
        ticket_bot.get_channel = MagicMock(return_value=mock_ticket_channel)

        config = MagicMock()
        config.log_channel_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        with patch("bot.cogs.tickets.asyncio.sleep", new_callable=AsyncMock):
            await tickets_cog.auto_close_stale_tickets()

        ticket_bot.ticket_service.close_ticket.assert_awaited_once()
        mock_ticket_channel.delete.assert_awaited_once()

    async def test_auto_close_ignores_fresh_tickets(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Fresh tickets (not stale) are not closed."""
        ticket_bot.guilds = [ticket_guild]

        # No stale tickets.
        ticket_bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[])

        config = MagicMock()
        config.log_channel_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        await tickets_cog.auto_close_stale_tickets()

        ticket_bot.ticket_service.close_ticket.assert_not_awaited()


class TestBuildTicketEmbed:
    """Tests for _build_ticket_embed helper."""

    def test_open_ticket_embed(self) -> None:
        """Open ticket embed has correct title and color."""
        ticket = Ticket.from_db_row(_ticket_row(status="open"))
        embed = _build_ticket_embed(ticket)
        assert "Ticket" in embed.title
        assert embed.color is not None

    def test_claimed_ticket_embed(self) -> None:
        """Claimed ticket embed shows claimed status."""
        ticket = Ticket.from_db_row(_ticket_row(status="claimed"))
        claimed_by = MagicMock()
        claimed_by.mention = "<@999999>"
        embed = _build_ticket_embed(ticket, claimed_by=claimed_by)
        assert "Claimed" in embed.title

    def test_embed_from_dict_row(self) -> None:
        """_build_ticket_embed handles raw dict (not Ticket model)."""
        row = _ticket_row(status="open")
        embed = _build_ticket_embed(row)
        assert "Ticket" in embed.title


# ---------------------------------------------------------------------------
# Additional coverage — edge cases and slash commands
# ---------------------------------------------------------------------------


class TestTicketPanelViewEdgeCases:
    """Edge cases for TicketPanelView."""

    async def test_open_ticket_no_guild_shows_error(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """open_ticket_button with no guild → error embed."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.client = ticket_bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        view = TicketPanelView()
        await view.open_ticket_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True


class TestClaimEdgeCases:
    """Edge cases for claim button."""

    async def test_claim_no_ticket(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """Claim on non-ticket channel → error embed."""
        ticket_interaction.client = ticket_bot
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        embed = ticket_interaction.response.send_message.call_args.kwargs.get("embed")
        assert "Claim Failed" in embed.title


class TestCloseEdgeCases:
    """Edge cases for close button."""

    async def test_close_no_ticket(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """Close on non-ticket channel → error embed."""
        ticket_interaction.client = ticket_bot
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        embed = ticket_interaction.response.send_message.call_args.kwargs.get("embed")
        assert "Close Failed" in embed.title

    async def test_close_already_closed(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """Close already-closed ticket → error embed."""
        ticket_interaction.client = ticket_bot
        row = _ticket_row(status="closed")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=row)

        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        embed = ticket_interaction.response.send_message.call_args.kwargs.get("embed")
        assert "Close Failed" in embed.title


class TestOnMessageListener:
    """Tests for the on_message ticket activity listener."""

    async def test_on_message_skips_bot_messages(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """Bot messages are ignored."""
        message = MagicMock()
        message.author.bot = True
        await tickets_cog.on_message(message)
        # No DB call expected.

    async def test_on_message_skips_non_ticket_channels(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Messages in non-ticket channels are ignored."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.channel.id = 999999

        ticket_bot.ticket_service.is_ticket_channel = MagicMock(return_value=False)

        await tickets_cog.on_message(message)
        mock_db.update_ticket_last_activity.assert_not_awaited()

    async def test_on_message_updates_ticket_activity(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Messages in ticket channels update lastActivity."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.channel.id = 444444444

        ticket_bot.ticket_service.is_ticket_channel = MagicMock(return_value=True)
        mock_db.update_ticket_last_activity = AsyncMock()

        await tickets_cog.on_message(message)
        mock_db.update_ticket_last_activity.assert_awaited_once_with("444444444")


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_syncs_cache(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """cog_load syncs channel cache and starts auto-close task."""
        ticket_bot.guilds = []
        ticket_bot.db.get_open_ticket_channel_ids = AsyncMock(return_value=[])

        # Mock the task so we don't actually start a loop.
        tickets_cog.auto_close_stale_tickets = MagicMock()
        tickets_cog.auto_close_stale_tickets.is_running = MagicMock(return_value=False)
        tickets_cog.auto_close_stale_tickets.start = MagicMock()

        await tickets_cog.cog_load()

        ticket_bot.ticket_service.sync_channel_cache.assert_called_once()

    async def test_cog_unload_cancels_task(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """cog_unload cancels the auto-close task."""
        tickets_cog.auto_close_stale_tickets = MagicMock()
        tickets_cog.auto_close_stale_tickets.is_running = MagicMock(return_value=True)
        tickets_cog.auto_close_stale_tickets.cancel = MagicMock()

        await tickets_cog.cog_unload()
        tickets_cog.auto_close_stale_tickets.cancel.assert_called_once()


class TestSlashCommands:
    """Tests for ticket slash commands."""

    async def test_ticket_panel_deploys_panel(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """ticket_panel command deploys panel embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()

        mock_message = MagicMock()
        mock_message.id = 777777777
        mock_message.channel = MagicMock()
        mock_message.channel.id = 888888888
        ctx.send = AsyncMock(return_value=mock_message)
        mock_db.update_guild_panel = AsyncMock()

        await tickets_cog.ticket_panel.callback(tickets_cog, ctx)

        ctx.send.assert_awaited()
        mock_db.update_guild_panel.assert_awaited_once()

    async def test_ticket_panel_no_guild(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """ticket_panel in DM → error embed."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.send = AsyncMock()

        await tickets_cog.ticket_panel.callback(tickets_cog, ctx)

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Server Only" in embed.title

    async def test_list_categories_shows_categories(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """list_categories shows configured categories."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()

        mock_db.get_ticket_categories = AsyncMock(return_value=[_category_row()])

        await tickets_cog.list_categories.callback(tickets_cog, ctx)

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Categories" in embed.title

    async def test_list_categories_empty(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """list_categories with no categories → info embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()

        mock_db.get_ticket_categories = AsyncMock(return_value=[])

        await tickets_cog.list_categories.callback(tickets_cog, ctx)

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "No Categories" in embed.title

    async def test_create_category_creates(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """create_category creates a new category."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()

        mock_db.get_ticket_categories = AsyncMock(return_value=[])
        mock_db.insert_ticket_category = AsyncMock(return_value=_category_row())

        await tickets_cog.create_category.callback(tickets_cog, ctx, name="Support")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Created" in embed.title

    async def test_create_category_duplicate_name(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """create_category with duplicate name → error embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()

        mock_db.get_ticket_categories = AsyncMock(return_value=[_category_row()])

        await tickets_cog.create_category.callback(tickets_cog, ctx, name="Support")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Duplicate" in embed.title

    async def test_delete_category_not_found(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with invalid ID → error embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 123456789
        ctx.send = AsyncMock()

        mock_db.get_ticket_category = AsyncMock(return_value=None)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="nonexistent")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Not Found" in embed.title

    async def test_delete_category_wrong_guild(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category for category in another guild → error embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = "999999999"
        ctx.send = AsyncMock()

        row = _category_row()  # guildId = "123456789"
        mock_db.get_ticket_category = AsyncMock(return_value=row)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Wrong Guild" in embed.title

    async def test_delete_category_in_use(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with open tickets → error embed."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = "123456789"
        ctx.send = AsyncMock()

        row = _category_row()
        mock_db.get_ticket_category = AsyncMock(return_value=row)
        mock_db.count_open_tickets_by_category = AsyncMock(return_value=3)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "In Use" in embed.title

    async def test_delete_category_success(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with valid ID and no open tickets → success."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = "123456789"
        ctx.send = AsyncMock()

        row = _category_row()
        mock_db.get_ticket_category = AsyncMock(return_value=row)
        mock_db.count_open_tickets_by_category = AsyncMock(return_value=0)
        mock_db.delete_ticket_category = AsyncMock()

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args.kwargs.get("embed")
        assert "Deleted" in embed.title


# ===========================================================================
# Subsidiados commands — /subticket create, /reopen, /transfer, /note * (slice 2)
# ===========================================================================
#
# All six commands MUST be gated by @is_mod(). They resolve the target ticket
# from the current channel (ctx.channel) via db.get_ticket_by_channel, then
# delegate to the matching TicketService method.


def _note_row_cog(
    note_id: str = "note-uuid-001",
    author_id: str = "111111111",
    content: str = "Customer escalated",
) -> dict:
    """Return a sample ticket_note DB row for cog tests."""
    return {
        "id": note_id,
        "ticketId": "ticket-uuid-003",
        "authorId": author_id,
        "content": content,
        "createdAt": "2026-07-04T12:00:00+00:00",
    }


@pytest.fixture
def slash_ctx(ticket_bot: MagicMock, mock_member: MagicMock, mock_ticket_channel: MagicMock) -> MagicMock:
    """Return a mock commands.Context wired to the ticket bot + a guild."""
    ctx = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.get_channel = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    guild.get_member = MagicMock(return_value=None)
    guild.create_text_channel = AsyncMock(return_value=mock_ticket_channel)
    ctx.bot = ticket_bot
    ctx.guild = guild
    mock_member.id = 111111111
    ctx.author = mock_member
    ctx.channel = mock_ticket_channel
    ctx.channel.id = 444444444
    ctx.send = AsyncMock()
    ctx.subcommand_passed = None
    return ctx


class TestSubticketCreate:
    """Tests for /subticket create."""

    async def test_subticket_create_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Valid invocation → create_subticket called with the parent id."""
        parent_row = _ticket_row(ticket_number=5)
        mock_db.get_ticket_by_channel = AsyncMock(return_value=parent_row)
        mock_db.get_max_ticket_number = AsyncMock(return_value=5)

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)

        subticket = Ticket.from_db_row({**_ticket_row(ticket_number=6), "parentId": parent_row["id"]})
        ticket_bot.ticket_service.create_subticket = AsyncMock(return_value=subticket)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_subticket.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_subticket.call_args.kwargs
        assert call_kwargs["parent_id"] == parent_row["id"]
        assert call_kwargs["guild_id"] == "123456789"
        slash_ctx.send.assert_awaited()

    async def test_subticket_create_no_guild(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
    ) -> None:
        """/subticket create in DM → error embed."""
        slash_ctx.guild = None
        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Server Only" in embed.title

    async def test_subticket_create_not_a_ticket_channel(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Current channel is not a ticket → error embed."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)
        ticket_bot.ticket_service.create_subticket = AsyncMock()

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_subticket.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Ticket" in embed.title  # "Not a Ticket" style message

    async def test_subticket_create_service_error_cleans_up(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """When create_subticket raises, the orphan channel is deleted."""
        parent_row = _ticket_row(ticket_number=5)
        mock_db.get_ticket_by_channel = AsyncMock(return_value=parent_row)
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)
        ticket_bot.ticket_service.create_subticket = AsyncMock(side_effect=ValueError("Parent ticket not found"))

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # Orphan channel deleted.
        slash_ctx.guild.create_text_channel.assert_awaited_once()
        mock_ticket_channel = slash_ctx.guild.create_text_channel.return_value
        mock_ticket_channel.delete.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Failed" in embed.title


class TestReopenCommand:
    """Tests for /reopen."""

    async def test_reopen_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/reopen → reopen_ticket called with the channel's ticket id."""
        closed_row = _ticket_row(status="closed")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=closed_row)
        reopened = Ticket.from_db_row({**closed_row, "status": "open"})
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(return_value=reopened)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.reopen_ticket.assert_awaited_once()
        call_args = ticket_bot.ticket_service.reopen_ticket.call_args
        assert call_args.args[0] == closed_row["id"]
        assert call_args.kwargs["guild"] is slash_ctx.guild
        slash_ctx.send.assert_awaited()

    async def test_reopen_no_guild(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
    ) -> None:
        """/reopen in DM → error embed."""
        slash_ctx.guild = None
        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Server Only" in embed.title

    async def test_reopen_not_a_ticket_channel(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """Current channel is not a ticket → error embed."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)
        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Ticket" in embed.title

    async def test_reopen_service_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """reopen_ticket raises → error embed."""
        closed_row = _ticket_row(status="closed")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=closed_row)
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(side_effect=ValueError("No ticket category configured"))
        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Failed" in embed.title


class TestTransferCommand:
    """Tests for /transfer @staff."""

    async def test_transfer_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/transfer @user → transfer_ticket called with new claimedBy."""
        claimed_row = _ticket_row(status="claimed")
        claimed_row["claimedBy"] = "999999999"
        mock_db.get_ticket_by_channel = AsyncMock(return_value=claimed_row)

        target = MagicMock(spec=discord.Member)
        target.id = 222222222
        slash_ctx.guild.get_member = MagicMock(return_value=MagicMock())
        ticket_bot.logging_service = MagicMock()
        transferred = Ticket.from_db_row({**claimed_row, "claimedBy": "222222222"})
        ticket_bot.ticket_service.transfer_ticket = AsyncMock(return_value=transferred)

        await tickets_cog.transfer.callback(tickets_cog, slash_ctx, member=target)

        ticket_bot.ticket_service.transfer_ticket.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.transfer_ticket.call_args.kwargs
        assert call_kwargs["new_claimed_by"] == "222222222"
        assert call_kwargs["actor_id"] == "111111111"
        assert call_kwargs["guild"] is slash_ctx.guild
        slash_ctx.send.assert_awaited()

    async def test_transfer_no_guild(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
    ) -> None:
        """/transfer in DM → error embed."""
        slash_ctx.guild = None
        target = MagicMock(spec=discord.Member)
        await tickets_cog.transfer.callback(tickets_cog, slash_ctx, member=target)
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Server Only" in embed.title


class TestNoteCommands:
    """Tests for /note add, /note list, /note delete."""

    async def test_note_add_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/note add → create_note called with author + content."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        from bot.models.ticket_note import TicketNote

        note = TicketNote.from_db_row(_note_row_cog())
        ticket_bot.ticket_service.create_note = AsyncMock(return_value=note)

        await tickets_cog.note_add.callback(tickets_cog, slash_ctx, content="Customer escalated")

        ticket_bot.ticket_service.create_note.assert_awaited_once()
        call_args = ticket_bot.ticket_service.create_note.call_args.args
        assert call_args[1] == "111111111"  # author_id = ctx.author.id
        assert call_args[2] == "Customer escalated"
        slash_ctx.send.assert_awaited()

    async def test_note_add_cap_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """create_note raises (cap) → error embed."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.create_note = AsyncMock(side_effect=ValueError("Note limit reached"))
        await tickets_cog.note_add.callback(tickets_cog, slash_ctx, content="one too many")
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Failed" in embed.title or "limit" in (embed.description or "").lower()

    async def test_note_list_shows_notes(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/note list → embed with notes."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        from bot.models.ticket_note import TicketNote

        notes = [TicketNote.from_db_row(_note_row_cog(note_id=f"n-{i}")) for i in range(3)]
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=notes)

        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.get_notes.assert_awaited_once()
        slash_ctx.send.assert_awaited_once()

    async def test_note_list_empty(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/note list with no notes → info embed."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=[])
        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "No" in embed.title or "no" in (embed.description or "").lower()

    async def test_note_delete_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/note delete → delete_note called with note id + author."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.delete_note = AsyncMock()
        await tickets_cog.note_delete.callback(tickets_cog, slash_ctx, note_id="note-uuid-001")
        ticket_bot.ticket_service.delete_note.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.delete_note.call_args.kwargs
        assert call_kwargs["note_id"] == "note-uuid-001"
        assert call_kwargs["author_id"] == "111111111"

    async def test_note_delete_not_owner(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """delete_note raises (ownership) → error embed."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.delete_note = AsyncMock(
            side_effect=ValueError("Only the note author may delete this note")
        )
        await tickets_cog.note_delete.callback(tickets_cog, slash_ctx, note_id="note-uuid-001")
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Failed" in embed.title or "author" in (embed.description or "").lower()


class TestSubsidiadosPermissions:
    """Verify every subsidiaries command is gated by @is_mod().

    For discord.py hybrid commands, ``@is_mod()`` (an ``app_commands.check``)
    registers on ``app_command.checks`` — the same place the existing
    ``ticket_panel`` / ``create_category`` commands carry their check
    (verified empirically: ``checks=[]``, ``app_command.checks=[1]``).
    """

    @staticmethod
    def _is_mod_gated(cmd) -> bool:
        return bool(cmd.checks) or (hasattr(cmd, "app_command") and bool(cmd.app_command.checks))

    def test_subticket_create_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.subticket_create), "/subticket create MUST be gated by @is_mod()"

    def test_reopen_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.reopen), "/reopen MUST be gated by @is_mod()"

    def test_transfer_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.transfer), "/transfer MUST be gated by @is_mod()"

    def test_note_add_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.note_add), "/note add MUST be gated by @is_mod()"

    def test_note_list_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.note_list), "/note list MUST be gated by @is_mod()"

    def test_note_delete_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.note_delete), "/note delete MUST be gated by @is_mod()"


# ===========================================================================
# B1 — /note list privacy (slash ephemeral + prefix DM)
# ===========================================================================


class TestNoteListPrivacy:
    """B1: /note list MUST be private — slash ephemeral, prefix DM to author.

    Spec (ticket-subsidiados): "Note content MUST NOT appear in channel
    ctx.send()". Slash → ephemeral reply. Prefix → DM notes to author +
    channel confirmation-only embed.
    """

    @staticmethod
    def _notes_with(content: str = "Secret staff note") -> list:
        from bot.models.ticket_note import TicketNote

        return [TicketNote.from_db_row(_note_row_cog(note_id="n-1", content=content))]

    async def test_note_list_slash_is_ephemeral(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Slash invocation → ctx.send(embed=..., ephemeral=True) with notes."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=self._notes_with())

        # Slash: ctx.interaction is not None.
        slash_ctx.interaction = MagicMock()

        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        slash_ctx.send.assert_awaited_once()
        call_kwargs = slash_ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs.get("embed")
        assert embed is not None
        # Notes content present in the ephemeral embed.
        assert "Secret staff note" in (embed.description or "")

    async def test_note_list_prefix_dms_author(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Prefix invocation → notes DM'd to author, channel gets confirmation only."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=self._notes_with())

        # Prefix: ctx.interaction is None.
        slash_ctx.interaction = None
        slash_ctx.author.send = AsyncMock()

        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        # Notes DM'd to author.
        slash_ctx.author.send.assert_awaited_once()
        dm_embed = slash_ctx.author.send.call_args.kwargs.get("embed")
        assert dm_embed is not None
        assert "Secret staff note" in (dm_embed.description or "")

        # Channel confirmation does NOT contain note content.
        slash_ctx.send.assert_awaited_once()
        chan_embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert chan_embed is not None
        assert "Secret staff note" not in (chan_embed.description or "")

    async def test_note_list_prefix_dm_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Prefix DM failure (discord.Forbidden) → error embed to channel, no leak."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=self._notes_with())

        slash_ctx.interaction = None
        slash_ctx.author.send = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Cannot DM user")
        )

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        # Error embed to channel — no note content leaked.
        slash_ctx.send.assert_awaited_once()
        chan_embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert chan_embed is not None
        assert "Secret staff note" not in (chan_embed.description or "")
        mock_exc.assert_called_once()


# ===========================================================================
# B2 — /reopen status guard (service ValueError + cog error embed)
# ===========================================================================


class TestReopenStatusGuard:
    """B2: /reopen MUST reject non-closed tickets with the actual status.

    Spec (ticket-subsidiados): "MUST reject non-closed with error embed
    showing actual status." The cog checks the channel's ticket row before
    calling the service; the service raises ValueError as defense-in-depth.
    """

    @pytest.mark.parametrize("status", ["open", "claimed"])
    async def test_reopen_non_closed_sends_spanish_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        status: str,
    ) -> None:
        """/reopen on an open/claimed ticket → error embed with exact Spanish text."""
        non_closed_row = {**_ticket_row(status=status)}
        mock_db.get_ticket_by_channel = AsyncMock(return_value=non_closed_row)
        ticket_bot.ticket_service.reopen_ticket = AsyncMock()

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)

        # Service MUST NOT be called — guard stops before it.
        ticket_bot.ticket_service.reopen_ticket.assert_not_awaited()
        # Error embed with the exact Spanish text and the actual status.
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "Solo se pueden reabrir tickets cerrados" in embed.description
        assert f"Estado actual: {status}" in embed.description


# ===========================================================================
# B3 — /subticket create parent-owner access grant
# ===========================================================================


def _parent_owner_member(member_id: int = 222222222) -> MagicMock:
    """Return a mock Member representing the parent ticket author."""
    owner = MagicMock(spec=discord.Member)
    owner.id = member_id
    owner.mention = f"<@{member_id}>"
    return owner


class TestSubticketParentOwnerAccess:
    """B3: /subticket create grants access to the parent ticket author.

    Spec (ticket-subsidiados): "Parent author (parent_owner) MUST get
    read_messages+send_messages overwrites and be mentioned. Invoker MUST
    NOT get extra overwrites — mod role suffices."
    """

    @staticmethod
    def _wire_subticket_base(slash_ctx, ticket_bot, mock_db, parent_author_id: str):
        """Wire config + parent row + max number for a subticket create call."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)

        parent_row = {**_ticket_row(ticket_number=5), "authorId": parent_author_id}
        mock_db.get_ticket_by_channel = AsyncMock(return_value=parent_row)
        mock_db.get_max_ticket_number = AsyncMock(return_value=5)

        subticket = Ticket.from_db_row(
            {**_ticket_row(ticket_number=6), "parentId": parent_row["id"]}
        )
        ticket_bot.ticket_service.create_subticket = AsyncMock(return_value=subticket)
        return parent_row

    async def test_overwrites_grant_parent_owner_not_invoker(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3.1: overwrites include parent owner (read+send), NOT invoker."""
        parent_owner = _parent_owner_member(222222222)
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222")
        slash_ctx.guild.get_member = MagicMock(return_value=parent_owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.guild.create_text_channel.assert_awaited_once()
        overwrites = slash_ctx.guild.create_text_channel.call_args.kwargs.get("overwrites")
        assert overwrites is not None
        # Parent owner gets read + send.
        assert parent_owner in overwrites
        assert overwrites[parent_owner].read_messages is True
        assert overwrites[parent_owner].send_messages is True
        # Invoker (author, id 111111111) does NOT get a separate overwrite.
        assert slash_ctx.author not in overwrites

    async def test_channel_send_mentions_parent_owner(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3.2: the new channel's initial message mentions the parent owner."""
        parent_owner = _parent_owner_member(222222222)
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222")
        slash_ctx.guild.get_member = MagicMock(return_value=parent_owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        mock_ticket_channel.send.assert_awaited_once()
        content = mock_ticket_channel.send.call_args.kwargs.get("content")
        assert content == parent_owner.mention
        assert content != slash_ctx.author.mention

    async def test_invoker_is_parent_owner_keeps_access(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3.3: when invoker IS the parent owner, access is granted once (no duplicate)."""
        # parent_author_id == invoker id (111111111).
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "111111111")

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.guild.create_text_channel.assert_awaited_once()
        overwrites = slash_ctx.guild.create_text_channel.call_args.kwargs.get("overwrites")
        assert overwrites is not None
        # Invoker (= parent owner) gets read + send.
        assert slash_ctx.author in overwrites
        assert overwrites[slash_ctx.author].read_messages is True
        assert overwrites[slash_ctx.author].send_messages is True
        # No fetch needed when invoker is the parent owner.
        slash_ctx.guild.get_member.assert_not_called()
        # Mention is the author (who is the parent owner).
        mock_ticket_channel.send.assert_awaited_once()
        assert mock_ticket_channel.send.call_args.kwargs.get("content") == slash_ctx.author.mention

    async def test_offline_parent_owner_fetch_fallback(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3 triangulation: offline parent owner resolved via fetch_member."""
        parent_owner = _parent_owner_member(222222222)
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222")
        slash_ctx.guild.get_member = MagicMock(return_value=None)
        slash_ctx.guild.fetch_member = AsyncMock(return_value=parent_owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.guild.fetch_member.assert_awaited_once_with(222222222)
        overwrites = slash_ctx.guild.create_text_channel.call_args.kwargs.get("overwrites")
        assert parent_owner in overwrites
        assert overwrites[parent_owner].read_messages is True

    async def test_parent_owner_unresolvable_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3 triangulation: parent owner cannot be resolved → error, no channel."""
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222")
        slash_ctx.guild.get_member = MagicMock(return_value=None)
        slash_ctx.guild.fetch_member = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Member not found")
        )

        with patch("bot.cogs.tickets.logger.exception"):
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # No channel created when the owner cannot be resolved.
        slash_ctx.guild.create_text_channel.assert_not_awaited()
        ticket_bot.ticket_service.create_subticket.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "Failed" in embed.title or "Not Found" in embed.title


# ===========================================================================
# B4 — scoped DB error handling in the new commands
# ===========================================================================


class TestDBErrorHandling:
    """B4: critical DB/service failures MUST NOT surface raw tracebacks.

    Spec (ticket-subsidiados): "On exception: error_embed() +
    logging.exception(). No raw tracebacks." Each critical DB call is
    wrapped in a tight try/except — never a bare ``except:``.
    """

    async def test_note_list_get_notes_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4.1: get_notes raises → error_embed + logger.exception, no leak."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(
            side_effect=Exception("DB down")
        )

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        assert "Traceback" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_subticket_create_db_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4.2: get_ticket_by_channel raises in /subticket create → error_embed."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)
        mock_db.get_ticket_by_channel = AsyncMock(
            side_effect=Exception("DB down")
        )

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # Channel not created when the parent lookup fails.
        slash_ctx.guild.create_text_channel.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_reopen_db_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4.3: get_ticket_by_channel raises in /reopen → error_embed."""
        mock_db.get_ticket_by_channel = AsyncMock(
            side_effect=Exception("DB down")
        )
        ticket_bot.ticket_service.reopen_ticket = AsyncMock()

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.reopen.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.reopen_ticket.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_transfer_db_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4 triangulation: get_ticket_by_channel raises in /transfer → error_embed."""
        mock_db.get_ticket_by_channel = AsyncMock(
            side_effect=Exception("DB down")
        )
        ticket_bot.ticket_service.transfer_ticket = AsyncMock()

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.transfer.callback(
                tickets_cog, slash_ctx, member=MagicMock(spec=discord.Member)
            )

        ticket_bot.ticket_service.transfer_ticket.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_note_add_db_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4 triangulation: get_ticket_by_channel raises in /note add → error_embed."""
        mock_db.get_ticket_by_channel = AsyncMock(
            side_effect=Exception("DB down")
        )
        ticket_bot.ticket_service.create_note = AsyncMock()

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.note_add.callback(
                tickets_cog, slash_ctx, content="a note"
            )

        ticket_bot.ticket_service.create_note.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_subticket_create_max_number_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4 triangulation: get_max_ticket_number raises in /subticket create → error_embed."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        category_channel = MagicMock(spec=discord.CategoryChannel)
        slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row(ticket_number=5))
        mock_db.get_max_ticket_number = AsyncMock(side_effect=Exception("DB down"))
        slash_ctx.guild.get_member = MagicMock(
            return_value=_parent_owner_member(111111111)
        )

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.guild.create_text_channel.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()
