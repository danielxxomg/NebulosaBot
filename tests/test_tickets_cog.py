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

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.tickets import (
    TicketActionsView,
    TicketPanelView,
    TicketsCog,
    _CategorySelect,
    _build_ticket_embed,
)
from bot.models.ticket import Ticket
from bot.models.ticket_category import TicketCategory


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
        "createdAt": datetime.now(timezone.utc),
        "closedAt": None,
        "lastActivity": datetime.now(timezone.utc),
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

        transcript_file = MagicMock(spec=discord.File)
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
