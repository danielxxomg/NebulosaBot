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
from bot.views.tickets import TicketIntakeModal

# ---------------------------------------------------------------------------
# i18n autouse fixture — load real locales so t() resolves correctly
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_real_locales() -> None:
    """Load real locale files so t() resolves ticket keys."""
    from pathlib import Path

    from bot.core import i18n as i18n_mod
    from bot.core.i18n import load_locales, set_guild_language

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    locale_dir = Path("bot/locales")
    if locale_dir.exists():
        load_locales(locale_dir)
        # Default test guild uses English
        set_guild_language("123456789", "en")


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
    bot.ticket_service.close_ticket_full = AsyncMock(return_value=None)
    bot.ticket_service.claim_ticket = AsyncMock()
    bot.ticket_service.get_stale_tickets = AsyncMock()
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=False)
    bot.ticket_service.sync_channel_cache = MagicMock()
    bot.ticket_service.create_ticket_channel = AsyncMock()
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

    async def test_category_select_sends_modal(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Category selection → modal sent as first response (no defer)."""
        ticket_interaction.client = ticket_bot

        select = _CategorySelect(options=[], guild=ticket_guild, categories=[])
        select._values = ["cat-uuid-001"]

        ticket_interaction.response.send_modal = AsyncMock()

        await select.callback(ticket_interaction)

        ticket_interaction.response.send_modal.assert_awaited_once()
        ticket_interaction.response.defer.assert_not_awaited()

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
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))

        select = _CategorySelect(options=[], guild=ticket_guild, categories=[])
        select._values = ["cat-uuid-001"]

        ticket_interaction.response.send_modal = AsyncMock()

        await select.callback(ticket_interaction)

        # Modal is sent, not a direct embed.
        ticket_interaction.response.send_modal.assert_awaited_once()


class TestTicketIntakeModal:
    """Tests for TicketIntakeModal — the intake form shown after category select."""

    async def test_category_select_sends_modal_not_defer(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Category selection MUST send_modal as first response (no defer)."""
        ticket_interaction.client = ticket_bot

        select = _CategorySelect(options=[], guild=ticket_guild, categories=[])
        select._values = ["cat-uuid-001"]

        # Patch send_modal so we can verify it was called instead of defer.
        ticket_interaction.response.send_modal = AsyncMock()

        await select.callback(ticket_interaction)

        # send_modal called — NOT defer.
        ticket_interaction.response.send_modal.assert_awaited_once()
        ticket_interaction.response.defer.assert_not_awaited()

    async def test_modal_submit_defers_then_creates_channel(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Modal submit → defer(ephemeral) → create_ticket_channel → send+pin → success."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        # Build a mock modal interaction.
        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        # Simulate user filling in the modal fields.
        modal.title_input = MagicMock(value="Login broken")
        modal.description_input = MagicMock(value="Cannot access since Monday")

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        # 1. Defer was called first.
        modal_interaction.response.defer.assert_awaited_once_with(ephemeral=True)

        # 2. Channel created with subject and description.
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["subject"] == "Login broken"
        assert call_kwargs["description"] == "Cannot access since Monday"

    async def test_modal_submit_empty_title_shows_error(
        self,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Modal submit with empty title → ephemeral error, no channel created."""
        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.send_message = AsyncMock()
        modal_interaction.response.defer = AsyncMock()

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        # Simulate empty title.
        modal.title_input = MagicMock(value="")
        modal.description_input = MagicMock(value="Some description")

        await modal.on_submit(modal_interaction)

        # Error sent, no defer, no channel creation.
        modal_interaction.response.send_message.assert_awaited_once()
        modal_interaction.response.defer.assert_not_awaited()
        ticket_bot.ticket_service.create_ticket_channel.assert_not_awaited()

    async def test_welcome_embed_is_pinned(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """After sending welcome embed, the message MUST be pinned."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        # Mock the sent message so we can verify pin() was called.
        sent_message = AsyncMock()
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Login broken")
        modal.description_input = MagicMock(value="")

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        # Message was sent then pinned.
        mock_ticket_channel.send.assert_awaited_once()
        sent_message.pin.assert_awaited_once()

    async def test_modal_submit_title_only_description_persists_none(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Title-only submit (blank description) → description=None forwarded and persisted."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Help me")
        modal.description_input = MagicMock(value="   ")  # blank/whitespace

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        # description=None forwarded to service.
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["subject"] == "Help me"
        assert call_kwargs["description"] is None

    async def test_modal_title_includes_category_name(
        self,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Modal title MUST include the selected category name."""
        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Report",
        )

        assert "Report" in modal.title

    async def test_pin_failure_does_not_abort_ticket_creation(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """When message.pin() raises HTTPException, ticket creation still succeeds."""
        ticket_interaction.client = ticket_bot

        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        # Mock pin to raise HTTPException.
        sent_message = AsyncMock()
        sent_message.pin = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Pin failed"))
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Help")
        modal.description_input = MagicMock(value="")

        with patch("bot.views.tickets.TicketActionsView"), patch("bot.views.tickets.logger") as mock_logger:
            await modal.on_submit(modal_interaction)

        # Ticket creation succeeds despite pin failure.
        modal_interaction.followup.send.assert_awaited_once()
        success_call_kwargs = modal_interaction.followup.send.call_args.kwargs
        assert success_call_kwargs.get("ephemeral") is True
        embed = success_call_kwargs.get("embed")
        assert embed is not None
        # Warning was logged for the pin failure.
        mock_logger.warning.assert_called()


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
        # PR2: Claim button is mod-gated — make the clicker a mod (admin fallback).
        ticket_interaction.user.guild_permissions.administrator = True
        ticket_bot._guild_mod_role_cache = {}
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
        # PR2: Claim is mod-gated — make the clicker a mod so we reach the
        # "Already Claimed" branch instead of the mod-deny branch.
        ticket_interaction.user.guild_permissions.administrator = True
        ticket_bot._guild_mod_role_cache = {}
        ticket_row = _ticket_row(status="claimed")
        ticket_row["claimedBy"] = "999999999"
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        call_kwargs = ticket_interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert embed.title is not None

    async def test_close_button_generates_transcript(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Close button → close_ticket_full called (handles transcript + DB + delete)."""
        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel

        ticket_row = _ticket_row(status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        ticket_bot.ticket_service.close_ticket_full = AsyncMock(return_value="https://example.com/transcript.html")

        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        ticket_bot.ticket_service.close_ticket_full.assert_awaited_once()
        call_args = ticket_bot.ticket_service.close_ticket_full.call_args
        assert call_args.args[0] == mock_ticket_channel  # channel
        assert call_args.args[2] == "111111111"  # closer_id
        assert call_args.kwargs["bot"] == ticket_bot


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

        await tickets_cog.auto_close_stale_tickets()

        ticket_bot.ticket_service.close_ticket_full.assert_called_once()

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
        embed = _build_ticket_embed(ticket, guild_id="123456789")
        assert embed.title is not None
        assert embed.color is not None

    def test_claimed_ticket_embed(self) -> None:
        """Claimed ticket embed shows claimed status."""
        ticket = Ticket.from_db_row(_ticket_row(status="claimed"))
        claimed_by = MagicMock()
        claimed_by.mention = "<@999999>"
        embed = _build_ticket_embed(ticket, claimed_by=claimed_by, guild_id="123456789")
        assert embed.title is not None

    def test_embed_from_dict_row(self) -> None:
        """_build_ticket_embed handles raw dict (not Ticket model)."""
        row = _ticket_row(status="open")
        embed = _build_ticket_embed(row, guild_id="123456789")
        assert embed.title is not None


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
        # PR2: pass the mod gate so the "not a ticket channel" branch is reached.
        ticket_interaction.user.guild_permissions.administrator = True
        ticket_bot._guild_mod_role_cache = {}
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_interaction.response.send_message.assert_awaited_once()
        embed = ticket_interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert embed.title is not None


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
        assert "Server Only" in embed.title or "Solo Servidores" in embed.title

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
        assert "Wrong Guild" in embed.title or "Servidor Incorrecto" in embed.title

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
        mock_ticket_channel: MagicMock,
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
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, subticket))

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
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
        assert "Server Only" in embed.title or "Solo Servidores" in embed.title

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
        mock_ticket_channel: MagicMock,
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
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(side_effect=ValueError("Parent ticket not found"))

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # Channel cleanup is now handled inside create_ticket_channel;
        # the cog surfaces the error embed.
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
        assert "Server Only" in embed.title or "Solo Servidores" in embed.title

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
        assert "Server Only" in embed.title or "Solo Servidores" in embed.title


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
        slash_ctx.author.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot DM user"))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        # Error embed to channel — no note content leaked.
        slash_ctx.send.assert_awaited_once()
        chan_embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert chan_embed is not None
        assert "Secret staff note" not in (chan_embed.description or "")
        mock_exc.assert_called_once()

    async def test_note_list_empty_slash_is_ephemeral(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B1: empty notes via slash → ephemeral 'No Notes' embed (no channel leak).

        The empty-state ('ticket has no staff notes') is private state and
        MUST NOT be broadcast to the channel. Slash replies ephemerally.
        """
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=[])

        slash_ctx.interaction = MagicMock()
        slash_ctx.author.send = AsyncMock()

        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        # Slash MUST reply ephemerally — the empty-state is private.
        slash_ctx.send.assert_awaited_once()
        call_kwargs = slash_ctx.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "No" in (embed.title or "") or "no staff notes" in (embed.description or "").lower()
        # No DM needed for slash — the ephemeral reply suffices.
        slash_ctx.author.send.assert_not_awaited()

    async def test_note_list_empty_prefix_dms_author(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B1: empty notes via prefix → DM 'No Notes' to author, channel gets confirmation-only.

        The channel confirmation MUST NOT disclose that the ticket has no
        staff notes (that state leak is the B1 bug). The author receives
        the empty-state privately via DM; the channel sees only the same
        generic 'Notes Sent' confirmation used by the non-empty path.
        """
        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row())
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=[])

        slash_ctx.interaction = None
        slash_ctx.author.send = AsyncMock()

        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        # The empty-state ('No Notes') is DM'd privately to the author.
        slash_ctx.author.send.assert_awaited_once()
        dm_embed = slash_ctx.author.send.call_args.kwargs.get("embed")
        assert dm_embed is not None
        assert "No" in (dm_embed.title or "") or "no staff notes" in (dm_embed.description or "").lower()

        # Channel gets a confirmation-only embed — MUST NOT leak the
        # empty-state wording ('No Notes' / 'no staff notes yet').
        slash_ctx.send.assert_awaited_once()
        chan_embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert chan_embed is not None
        chan_text = f"{chan_embed.title or ''} {chan_embed.description or ''}".lower()
        assert "no staff notes yet" not in chan_text
        assert "no notes" not in chan_text


# ===========================================================================
# B2 — /reopen status guard (service ValueError + cog error embed)
# ===========================================================================


class TestReopenStatusGuard:
    """B2: /reopen MUST reject non-closed tickets with the actual status.

    Spec (ticket-subsidiados): "MUST reject non-closed with error embed
    showing actual status." Defense-in-depth: the cog has NO pre-service
    status guard — it delegates to the service, which raises ValueError
    with the actual status. The cog catches that ValueError and surfaces
    a localized message via t(), NOT the service's raw exception text.
    """

    @pytest.mark.parametrize("status", ["open", "claimed"])
    async def test_reopen_non_closed_sends_localized_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        status: str,
    ) -> None:
        """/reopen on an open/claimed ticket → cog catches service ValueError, surfaces localized error."""
        non_closed_row = {**_ticket_row(status=status)}
        mock_db.get_ticket_by_channel = AsyncMock(return_value=non_closed_row)
        # The service guard raises ValueError — the cog now translates it
        # via t() instead of surfacing str(e) verbatim.
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            side_effect=ValueError(f"Solo se pueden reabrir tickets cerrados. Estado actual: {status}")
        )

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)

        # Service IS called — the cog relies on the service guard, not a
        # redundant pre-service status check.
        ticket_bot.ticket_service.reopen_ticket.assert_awaited_once()
        # Error embed surfaces a LOCALIZED message (EN guild), not the
        # service's raw Spanish text.
        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        # Guild is EN — must see English localized text
        assert "Only closed tickets can be reopened" in (embed.description or "")
        assert status in (embed.description or "")
        # Must NOT surface the service's raw Spanish text
        assert "Solo se pueden" not in (embed.description or "")


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
    def _wire_subticket_base(slash_ctx, ticket_bot, mock_db, parent_author_id: str, mock_ticket_channel=None):
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

        subticket = Ticket.from_db_row({**_ticket_row(ticket_number=6), "parentId": parent_row["id"]})
        ticket_bot.ticket_service.create_subticket = AsyncMock(return_value=subticket)
        if mock_ticket_channel is not None:
            ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, subticket))
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
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222", mock_ticket_channel)
        slash_ctx.guild.get_member = MagicMock(return_value=parent_owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_args = ticket_bot.ticket_service.create_ticket_channel.call_args
        # The parent_owner is passed as the `author` argument to create_ticket_channel.
        assert call_args.args[2] == parent_owner  # author

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
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222", mock_ticket_channel)
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
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "111111111", mock_ticket_channel)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_args = ticket_bot.ticket_service.create_ticket_channel.call_args
        # Invoker (= parent owner) is passed as the `author` argument.
        assert call_args.args[2] == slash_ctx.author  # author
        # No fetch needed when invoker is the parent owner.
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
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222", mock_ticket_channel)
        slash_ctx.guild.get_member = MagicMock(return_value=None)
        slash_ctx.guild.fetch_member = AsyncMock(return_value=parent_owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.guild.fetch_member.assert_awaited_once_with(222222222)
        call_args = ticket_bot.ticket_service.create_ticket_channel.call_args
        # Parent owner is passed as the `author` argument.
        assert call_args.args[2] == parent_owner

    async def test_parent_owner_unresolvable_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """B3 triangulation: parent owner cannot be resolved → error, no channel."""
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, "222222222", mock_ticket_channel)
        slash_ctx.guild.get_member = MagicMock(return_value=None)
        slash_ctx.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Member not found"))

        with patch("bot.cogs.tickets.logger.exception"):
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # No channel created when the owner cannot be resolved.
        ticket_bot.ticket_service.create_ticket_channel.assert_not_awaited()
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
        ticket_bot.ticket_service.get_notes = AsyncMock(side_effect=Exception("DB down"))

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
        mock_db.get_ticket_by_channel = AsyncMock(side_effect=Exception("DB down"))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # Channel not created when the parent lookup fails.
        ticket_bot.ticket_service.create_ticket_channel.assert_not_awaited()
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
        mock_db.get_ticket_by_channel = AsyncMock(side_effect=Exception("DB down"))
        ticket_bot.ticket_service.reopen_ticket = AsyncMock()

        with patch("bot.utils.ticket_helpers.logger.exception") as mock_exc:
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
        mock_db.get_ticket_by_channel = AsyncMock(side_effect=Exception("DB down"))
        ticket_bot.ticket_service.transfer_ticket = AsyncMock()

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.transfer.callback(tickets_cog, slash_ctx, member=MagicMock(spec=discord.Member))

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
        mock_db.get_ticket_by_channel = AsyncMock(side_effect=Exception("DB down"))
        ticket_bot.ticket_service.create_note = AsyncMock()

        with patch("bot.utils.ticket_helpers.logger.exception") as mock_exc:
            await tickets_cog.note_add.callback(tickets_cog, slash_ctx, content="a note")

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
        slash_ctx.guild.get_member = MagicMock(return_value=_parent_owner_member(111111111))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_not_awaited()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()


# ===========================================================================
# PR2 — button permission gates + /reopen ticket_ref
# ===========================================================================


class TestPR2ButtonPermissionGates:
    """Inline is_mod_check() gates on claim/close buttons (design.md L33-44)."""

    async def test_claim_button_denies_non_mod(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """3.11/3.12: a non-mod clicking Claim MUST get an ephemeral deny (no claim)."""
        ticket_interaction.client = ticket_bot
        # Non-admin, no mod role configured → is_mod_check returns False.
        ticket_interaction.user.guild_permissions.administrator = False
        ticket_interaction.user.roles = []
        ticket_bot._guild_mod_role_cache = {}

        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row(status="open"))

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_bot.ticket_service.claim_ticket.assert_not_awaited()
        ticket_interaction.response.send_message.assert_awaited_once()
        kwargs = ticket_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None  # user-facing error embed

    async def test_claim_button_allows_mod(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_db,
    ) -> None:
        """A mod (configured role) clicking Claim MUST proceed to claim."""
        ticket_interaction.client = ticket_bot
        mod_role_id = 987654321
        ticket_interaction.user.guild_permissions.administrator = False
        ticket_bot._guild_mod_role_cache = {123456789: str(mod_role_id)}
        role = MagicMock(spec=discord.Role)
        role.id = mod_role_id
        ticket_interaction.user.roles = [role]

        ticket_row = _ticket_row(status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)
        claimed = Ticket.from_db_row({**ticket_row, "status": "claimed", "claimedBy": "111111111"})
        ticket_bot.ticket_service.claim_ticket = AsyncMock(return_value=claimed)

        view = TicketActionsView()
        await view.claim_button.callback(ticket_interaction)

        ticket_bot.ticket_service.claim_ticket.assert_awaited_once()

    async def test_close_button_denies_non_author_non_mod(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """3.13/3.14: a non-author non-mod clicking Close MUST get an ephemeral deny."""
        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel
        # A user who is NOT the author (author is 111111111) and NOT a mod.
        ticket_interaction.user.id = 222222222
        ticket_interaction.user.guild_permissions.administrator = False
        ticket_interaction.user.roles = []
        ticket_bot._guild_mod_role_cache = {}

        mock_db.get_ticket_by_channel = AsyncMock(return_value=_ticket_row(status="open"))

        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        ticket_bot.ticket_service.close_ticket.assert_not_awaited()
        ticket_interaction.response.send_message.assert_awaited_once()
        kwargs = ticket_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True


class TestReopenByTicketRef:
    """/reopen ticket_ref resolution by number / UUID (TI-029, TI-037)."""

    async def test_reopen_by_ticket_number(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/reopen ticket:#0003 resolves ticket #3 via get_ticket_by_number."""
        closed_row = _ticket_row(ticket_number=3, status="closed")
        mock_db.get_ticket_by_number = AsyncMock(return_value=closed_row)
        reopened = Ticket.from_db_row({**closed_row, "status": "open"})
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(return_value=reopened)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref="#0003")

        mock_db.get_ticket_by_number.assert_awaited_once_with("123456789", 3)
        ticket_bot.ticket_service.reopen_ticket.assert_awaited_once()
        args = ticket_bot.ticket_service.reopen_ticket.call_args.args
        assert args[0] == closed_row["id"]

    async def test_reopen_by_ticket_number_with_prefix(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """The literal guidance 'ticket:#0003' parses to number 3."""
        closed_row = _ticket_row(ticket_number=3, status="closed")
        mock_db.get_ticket_by_number = AsyncMock(return_value=closed_row)
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            return_value=Ticket.from_db_row({**closed_row, "status": "open"})
        )

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref="ticket:#0003")

        mock_db.get_ticket_by_number.assert_awaited_once_with("123456789", 3)

    async def test_reopen_by_uuid(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """A UUID ref resolves via get_ticket (with guild-scope check)."""
        uuid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        closed_row = {**_ticket_row(ticket_number=3, status="closed"), "id": uuid_str}
        mock_db.get_ticket = AsyncMock(return_value=closed_row)
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            return_value=Ticket.from_db_row({**closed_row, "status": "open"})
        )

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref=uuid_str)

        mock_db.get_ticket.assert_awaited_once_with(uuid_str)
        mock_db.get_ticket_by_number.assert_not_awaited()
        ticket_bot.ticket_service.reopen_ticket.assert_awaited_once()

    async def test_reopen_bad_ref_shows_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """An unparseable ticket_ref MUST surface an error_embed (no reopen)."""
        mock_db.get_ticket_by_number = AsyncMock(return_value=None)
        mock_db.get_ticket = AsyncMock(return_value=None)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref="not-a-ticket")

        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None

    async def test_reopen_missing_ticket_shows_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """A valid number that matches no ticket MUST surface an error_embed."""
        mock_db.get_ticket_by_number = AsyncMock(return_value=None)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref="#9999")

        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None

    async def test_reopen_wrong_guild_denied(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """A UUID ref belonging to a different guild MUST be denied."""
        uuid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        # Ticket found but belongs to a DIFFERENT guild.
        other_guild_row = {**_ticket_row(status="closed"), "id": uuid_str, "guildId": "999000999"}
        mock_db.get_ticket = AsyncMock(return_value=other_guild_row)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref=uuid_str)

        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None

    async def test_reopen_no_arg_legacy_channel_lookup(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """TI-037: with no ticket_ref, /reopen falls back to channel lookup."""
        closed_row = _ticket_row(status="closed")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=closed_row)
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            return_value=Ticket.from_db_row({**closed_row, "status": "open"})
        )

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx)  # no ticket_ref

        mock_db.get_ticket_by_channel.assert_awaited_once()
        mock_db.get_ticket_by_number.assert_not_awaited()


# ===========================================================================
# Actionable error messages — config missing flows
# ===========================================================================


class TestConfigMissingErrorMessages:
    """Error embeds when ticket_category_id is None MUST mention /setup,
    /create_category, and the dashboard URL.
    """

    @pytest.fixture(autouse=True)
    def _load_locales(self):
        """Load i18n locales so t() resolves real keys."""
        from pathlib import Path

        from bot.core.i18n import load_locales, set_guild_language

        load_locales(Path("bot/locales"))
        set_guild_language("123456789", "en")
        yield

    async def test_category_select_callback_config_missing_mentions_setup(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        ticket_guild: MagicMock,
        mock_db,
    ) -> None:
        """Modal submit with ticket_category_id=None → actionable error."""
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        config = MagicMock()
        config.ticket_category_id = None
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        from bot.views.tickets import TicketIntakeModal

        modal = TicketIntakeModal(
            guild=ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Help")
        modal.description_input = MagicMock(value=None)

        await modal.on_submit(modal_interaction)

        modal_interaction.followup.send.assert_awaited_once()
        call_kwargs = modal_interaction.followup.send.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        desc = embed.description or ""
        assert "/setup" in desc
        assert "/create_category" in desc
        assert "dashboard" in desc.lower() or "https://" in desc

    async def test_subticket_create_config_missing_mentions_setup(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/subticket create with ticket_category_id=None → actionable error."""
        config = MagicMock()
        config.ticket_category_id = None
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        slash_ctx.send.assert_awaited_once()
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        desc = embed.description or ""
        assert "/setup" in desc
        assert "/create_category" in desc
        assert "dashboard" in desc.lower() or "https://" in desc
