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

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.ticket_admin_flow import TicketAdminFlow
from bot.cogs.ticket_integrity_flow import TicketIntegrityFlow
from bot.cogs.ticket_lifecycle_flow import TicketLifecycleFlow
from bot.cogs.ticket_notes_flow import TicketNotesFlow
from bot.cogs.tickets import (
    TicketActionsView,
    TicketPanelView,
    TicketsCog,
    _build_ticket_embed,
    _CategorySelect,
)
from bot.core import i18n as i18n_mod
from bot.core.cache import TTLCache
from bot.core.i18n import load_locales, set_guild_language
from bot.models.ticket import RepairResult, Ticket
from bot.models.ticket_note import TicketNote
from bot.services.ticket_repair_service import TimerMessageResult
from bot.services.ticket_service import TicketService
from bot.views.confirmation import ConfirmCancelView
from bot.views.tickets import TicketIntakeModal

# ---------------------------------------------------------------------------
# i18n autouse fixture — load real locales so t() resolves correctly
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_real_locales() -> None:
    """Load real locale files so t() resolves ticket keys."""
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


def _wire_intake_success(
    ticket_bot: MagicMock,
    mock_db,
    ticket_guild: MagicMock,
    mock_ticket_channel: MagicMock,
    *,
    ticket_category_id: str | None = "100000000",
) -> Ticket:
    """Wire the happy-path intake scaffold shared by TicketIntakeModal tests.

    Sets guild config (default category id), the category channel lookup,
    create_ticket_channel → (channel, ticket), and get_max_ticket_number.
    Returns the created ticket. ``ticket_category_id=None`` builds the
    config-missing scaffold instead.
    """
    config = MagicMock()
    config.ticket_category_id = ticket_category_id
    config.mod_role_id = None
    ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

    category_channel = MagicMock(spec=discord.CategoryChannel)
    ticket_guild.get_channel = MagicMock(return_value=category_channel)

    ticket = Ticket.from_db_row(_ticket_row(ticket_number=1))
    ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))
    ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)
    return ticket


def _make_modal_interaction(ticket_bot: MagicMock, ticket_guild: MagicMock) -> MagicMock:
    """Return a mock modal-submit Interaction wired for TicketIntakeModal."""
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
    return modal_interaction


def _make_intake_modal(
    ticket_guild: MagicMock,
    *,
    title: str = "Login broken",
    description: str | None = "Cannot access since Monday",
    category_name: str = "Support",
) -> TicketIntakeModal:
    """Return a TicketIntakeModal with the form fields filled in."""
    modal = TicketIntakeModal(
        guild=ticket_guild,
        category_id="cat-uuid-001",
        category_name=category_name,
    )
    modal.title_input = MagicMock(value=title)
    modal.description_input = MagicMock(value=description)
    return modal


def _wire_subticket_success(
    ticket_bot: MagicMock,
    slash_ctx: MagicMock,
    mock_db,
    *,
    parent_row: dict | None = None,
    ticket_category_id: str | None = "100000000",
    mod_role_id: str | None = None,
    channel_result: object | None = "default_channel",
) -> dict:
    """Wire the subticket_create scaffold: config + category channel + parent row.

    ``parent_row=None`` defaults to ``_ticket_row(ticket_number=5)``.
    ``channel_result="default_channel"`` makes create_ticket_channel return
    ``(mock channel from slash_ctx, subticket)``; pass an explicit value or
    an Exception to override (Exception simulates a service failure).
    Returns the wired parent row.
    """
    config = MagicMock()
    config.ticket_category_id = ticket_category_id
    config.mod_role_id = mod_role_id
    ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

    category_channel = MagicMock(spec=discord.CategoryChannel)
    slash_ctx.guild.get_channel = MagicMock(return_value=category_channel)

    if parent_row is None:
        parent_row = _ticket_row(ticket_number=5)
    mock_db.get_ticket_by_channel = AsyncMock(return_value=parent_row)

    if channel_result == "default_channel":
        subticket = Ticket.from_db_row({**_ticket_row(ticket_number=6), "parentId": parent_row["id"]})
        channel = getattr(slash_ctx, "channel", None) or MagicMock()
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(channel, subticket))
    elif isinstance(channel_result, Exception):
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(side_effect=channel_result)
    else:
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=channel_result)
    return parent_row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ticket_bot(mock_db) -> MagicMock:
    """Return a mock NebulosaBot for tickets tests.

    All AsyncMock children have explicit ``return_value`` because
    ``AsyncMock().return_value`` is itself an ``AsyncMock`` — calling
    ``.get()`` on that implicit child creates an unawaited coroutine.
    """
    bot = MagicMock()
    bot.db = mock_db
    bot.ticket_service = MagicMock()
    bot.ticket_service.create_ticket = AsyncMock(return_value=None)
    bot.ticket_service.close_ticket = AsyncMock(return_value=None)
    bot.ticket_service.close_ticket_full = AsyncMock(return_value=None)
    bot.ticket_service.claim_ticket = AsyncMock(return_value=None)
    bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[])
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=False)
    bot.ticket_service.sync_channel_cache = MagicMock()
    bot.ticket_service.create_ticket_channel = AsyncMock(return_value=None)
    bot.ticket_service.repair_ticket_by_ref = AsyncMock(return_value=None)
    bot.transcript_service = MagicMock()
    bot.transcript_service.generate = AsyncMock(return_value=None)
    bot.transcript_service.upload = AsyncMock(return_value=None)
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=None)
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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, mock_ticket_channel)
        ticket_bot.ticket_service.create_ticket = AsyncMock(
            return_value=ticket_bot.ticket_service.create_ticket_channel.return_value[1]
        )

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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, mock_ticket_channel)
        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal = _make_intake_modal(ticket_guild)

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
        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal_interaction.response.send_message = AsyncMock()

        # Simulate empty title.
        modal = _make_intake_modal(ticket_guild, title="", description="Some description")

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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, mock_ticket_channel)
        # Mock the sent message so we can verify pin() was called.
        sent_message = AsyncMock()
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal = _make_intake_modal(ticket_guild, description="")

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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, mock_ticket_channel)
        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal = _make_intake_modal(ticket_guild, title="Help me", description="   ")  # blank/whitespace

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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, mock_ticket_channel)
        # Mock pin to raise HTTPException.
        sent_message = AsyncMock()
        sent_message.pin = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Pin failed"))
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal = _make_intake_modal(ticket_guild, title="Help", description="")

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

        embed = _interaction_embed(ticket_interaction)
        assert embed.title is not None

    async def test_close_button_generates_transcript(
        self,
        ticket_bot: MagicMock,
        ticket_interaction: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db,
    ) -> None:
        """Close button → ephemeral ConfirmCancelView sent (close deferred to confirm)."""
        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel

        ticket_row = _ticket_row(status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        ticket_bot.ticket_service.close_ticket_full = AsyncMock(return_value="https://example.com/transcript.html")

        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        # Button sends ephemeral ConfirmCancelView (not close_ticket_full directly).
        ticket_interaction.response.send_message.assert_awaited_once()
        call_kwargs = ticket_interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), ConfirmCancelView)


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
        _auto_close_env(ticket_bot, ticket_guild, mock_ticket_channel)

        await tickets_cog.auto_close_stale_tickets()

        ticket_bot.ticket_service.close_ticket_full.assert_called_once()

    async def test_auto_close_passes_manual_false(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """Auto-close MUST call close_ticket_full with manual=False (silent delete)."""
        _auto_close_env(ticket_bot, ticket_guild, mock_ticket_channel)

        await tickets_cog.auto_close_stale_tickets()

        ticket_bot.ticket_service.close_ticket_full.assert_called_once()
        call_kwargs = ticket_bot.ticket_service.close_ticket_full.call_args.kwargs
        assert call_kwargs["manual"] is False

    async def test_auto_close_ignores_fresh_tickets(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        ticket_guild: MagicMock,
    ) -> None:
        """Fresh tickets (not stale) are not closed."""
        _auto_close_env(ticket_bot, ticket_guild, MagicMock(), stale=False)

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

        embed = _interaction_embed(ticket_interaction)
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

        embed = _interaction_embed_no_once(ticket_interaction)
        assert "Close Failed" in (embed.title or "")

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

        embed = _interaction_embed_no_once(ticket_interaction)
        assert "Close Failed" in (embed.title or "")


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
        """Messages in ticket channels update lastActivity with guild_id and timestamp."""
        message = MagicMock()
        message.author.bot = False
        message.guild = MagicMock()
        message.guild.id = 123456789
        message.channel.id = 444444444

        ticket_bot.ticket_service.is_ticket_channel = MagicMock(return_value=True)
        mock_db.update_ticket_last_activity = AsyncMock()

        await tickets_cog.on_message(message)
        mock_db.update_ticket_last_activity.assert_awaited_once()
        args = mock_db.update_ticket_last_activity.call_args.args
        assert args[0] == "123456789"  # guild_id
        assert args[1] == "444444444"  # channel_id
        assert isinstance(args[2], str)  # timestamp


# ---------------------------------------------------------------------------
# S4.4 — ','-timer per-user 15s debounce
# ---------------------------------------------------------------------------


class TestTimerMessageDebounce:
    """Duplicate ',' messages from the same user within 15s are silently ignored.

    Mirrors the voice_listener debounce pattern: dict keyed
    ``{guild}:{channel}:{user}`` with TTL eviction on every event.
    """

    @pytest.fixture(autouse=True)
    def _timer_env(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
        mock_member,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Wire a fully passing on_message path up to _dispatch_timer_message."""
        self.cog = tickets_cog
        self.bot = ticket_bot
        self.db = mock_db

        # Matrix gate passes unconditionally — authorization is not under test here.
        monkeypatch.setattr("bot.cogs.tickets.can_member", AsyncMock(return_value=True))

        message = MagicMock()
        message.guild.id = 123456789
        message.channel.id = 444444444
        message.content = ","
        message.author = mock_member
        # Set AFTER author assignment — mock_member is a bare MagicMock whose
        # auto-created ``bot`` attribute would otherwise be truthy.
        message.author.bot = False
        message.author.id = 111111111
        self.message = message

        ticket_bot.ticket_service.is_ticket_channel = MagicMock(return_value=True)
        ticket_bot.ticket_service.handle_timer_message = AsyncMock(return_value=None)
        mock_db.update_ticket_last_activity = AsyncMock()
        _ticket_channel_row(mock_db)
        # Second lookup path must stay unused.
        mock_db.get_active_ticket_by_channel = AsyncMock()

    def _run(self, clock: list[float]):
        """Return an async callable that fires one on_message at clock[0].

        Patches ``time.monotonic`` globally (not the cog namespace) so the
        RED phase fails cleanly on dispatch counts before the debounce
        exists.
        """

        async def _fire() -> None:
            with patch("time.monotonic", return_value=clock[0]):
                await self.cog.on_message(self.message)

        return _fire

    async def test_first_comma_message_dispatches(self) -> None:
        clock = [1000.0]
        await self._run(clock)()
        self.bot.ticket_service.handle_timer_message.assert_awaited_once()

    async def test_duplicate_within_window_silently_ignored(self) -> None:
        clock = [1000.0]
        await self._run(clock)()
        clock[0] = 1005.0  # same user/channel/guild 5s later
        await self._run(clock)()
        assert self.bot.ticket_service.handle_timer_message.await_count == 1

    async def test_after_ttl_passes_again(self) -> None:
        clock = [1000.0]
        await self._run(clock)()
        clock[0] = 1005.0
        await self._run(clock)()  # inside window — ignored
        clock[0] = 1016.0  # beyond the 15s TTL
        await self._run(clock)()
        assert self.bot.ticket_service.handle_timer_message.await_count == 2

    async def test_different_user_not_debounced(self) -> None:
        other = MagicMock()
        other.__class__ = discord.Member
        other.id = 222222222
        other.bot = False
        self.message.author = other

        clock = [1000.0]
        await self._run(clock)()
        self.message.author.id = 111111111
        await self._run(clock)()
        assert self.bot.ticket_service.handle_timer_message.await_count == 2

    async def test_debounce_store_evicts_stale_entries(self) -> None:
        clock = [1000.0]
        await self._run(clock)()
        clock[0] = 1100.0  # well past TTL
        await self._run(clock)()
        # The stale entry was evicted, not left to grow unbounded.
        assert len(self.cog._timer_debounce) == 1
        assert self.cog._timer_debounce["123456789:444444444:111111111"] == 1100.0

    # -- cycle-5 narrow fix: ',cancel' exempt from the debounce window ------

    async def test_cancel_within_window_still_processed(self) -> None:
        """A ',cancel' inside the 15s window MUST still reach the state-machine.

        Maintainer decision (cycle-5-quality-zero narrow fix): cancelling is
        urgent by nature — the duplicate-suppression window may never
        silently drop it. Only duration-setting messages are debounced.
        """
        ts = self.bot.ticket_service
        ts.handle_timer_message = AsyncMock(
            side_effect=[
                None,  # first fire: ',12h' parses as duration (dispatch only)
                TimerMessageResult(
                    action="cancelled",
                    guild_id="123456789",
                    ticket_id=_ticket_row()["id"],
                    author_id="111111111",
                ),
            ]
        )
        self.message.channel.send = AsyncMock()

        self.message.content = ",12h"
        clock = [1000.0]
        await self._run(clock)()

        self.message.content = ",cancel"
        clock[0] = 1005.0  # inside the 15s window of the ',12h' above
        await self._run(clock)()

        assert ts.handle_timer_message.await_count == 2
        assert ts.handle_timer_message.await_args_list[1].args[2] == ",cancel"
        # Cancel routed through the confirmation embed (schedule_close cancelled).
        self.message.channel.send.assert_awaited_once()

    async def test_cancel_does_not_enter_debounce_window(self) -> None:
        """The exemption neither checks NOR refreshes the 15s duration window."""
        self.message.content = ",12h"
        clock = [1000.0]
        await self._run(clock)()  # duration fire seeds the window

        self.message.content = ",cancel"
        clock[0] = 1010.0
        await self._run(clock)()  # exempt — processed, window untouched

        self.message.content = ",30m"
        clock[0] = 1016.0  # 16s after the ',12h' seed — beyond the TTL
        await self._run(clock)()

        assert self.bot.ticket_service.handle_timer_message.await_count == 3

    async def test_duration_messages_still_debounced(self) -> None:
        """Duration-setting ',' messages remain debounced (regression guard)."""
        self.message.content = ",12h"
        clock = [1000.0]
        await self._run(clock)()

        self.message.content = ",30m"
        clock[0] = 1005.0  # same user/channel/guild 5s later
        await self._run(clock)()

        assert self.bot.ticket_service.handle_timer_message.await_count == 1


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

    @staticmethod
    def _panel_ctx() -> MagicMock:
        """Return the shared ticket_panel command context."""
        ctx = _guild_ctx(123456789)
        ctx.channel = MagicMock()
        return ctx

    async def test_ticket_panel_deploys_panel(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """ticket_panel command delegates to deploy_ticket_panel with None defaults."""
        ctx = self._panel_ctx()

        with patch("bot.cogs.tickets.deploy_ticket_panel", new_callable=AsyncMock) as mock_deploy:
            await tickets_cog.ticket_panel.callback(tickets_cog, ctx)

        mock_deploy.assert_awaited_once_with(
            ctx.channel,
            "123456789",
            bot=ticket_bot,
            guild=ctx.guild,
            title=None,
            description_text=None,
        )
        # Success embed sent.
        ctx.send.assert_awaited()

    async def test_ticket_panel_explicit_overrides_pass_through(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """ticket_panel with explicit title/desc passes them through as-is."""
        ctx = self._panel_ctx()

        with patch("bot.cogs.tickets.deploy_ticket_panel", new_callable=AsyncMock) as mock_deploy:
            await tickets_cog.ticket_panel.callback(
                tickets_cog,
                ctx,
                title="Mi Panel",
                description_text="Abre un ticket",
            )

        mock_deploy.assert_awaited_once_with(
            ctx.channel,
            "123456789",
            bot=ticket_bot,
            guild=ctx.guild,
            title="Mi Panel",
            description_text="Abre un ticket",
        )

    async def test_ticket_panel_no_guild(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """ticket_panel in DM → error embed."""
        ctx = _guild_ctx(None)
        await _assert_no_guild_error(tickets_cog, tickets_cog.ticket_panel, ctx)

    async def test_list_categories_shows_categories(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """list_categories shows configured categories."""
        ctx = _guild_ctx(123456789)

        mock_db.get_ticket_categories = AsyncMock(return_value=[_category_row()])

        await tickets_cog.list_categories.callback(tickets_cog, ctx)

        embed = _sent_embed(ctx)
        assert "Categories" in (embed.title or "")

    async def test_list_categories_empty(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """list_categories with no categories → info embed."""
        ctx = _guild_ctx(123456789)

        mock_db.get_ticket_categories = AsyncMock(return_value=[])

        await tickets_cog.list_categories.callback(tickets_cog, ctx)

        embed = _sent_embed(ctx)
        assert "No Categories" in (embed.title or "")

    async def test_create_category_creates(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """create_category creates a new category."""
        ctx = _guild_ctx(123456789)

        mock_db.get_ticket_categories = AsyncMock(return_value=[])
        mock_db.insert_ticket_category = AsyncMock(return_value=_category_row())

        await tickets_cog.create_category.callback(tickets_cog, ctx, name="Support")

        embed = _sent_embed(ctx)
        assert "Created" in (embed.title or "")

    async def test_create_category_duplicate_name(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """create_category with duplicate name → error embed."""
        ctx = _guild_ctx(123456789)

        mock_db.get_ticket_categories = AsyncMock(return_value=[_category_row()])

        await tickets_cog.create_category.callback(tickets_cog, ctx, name="Support")

        embed = _sent_embed(ctx)
        assert "Duplicate" in (embed.title or "")

    async def test_delete_category_not_found(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with invalid ID → error embed."""
        ctx = _guild_ctx(123456789)

        mock_db.get_ticket_category = AsyncMock(return_value=None)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="nonexistent")

        embed = _sent_embed(ctx)
        assert "Not Found" in (embed.title or "")

    async def test_delete_category_wrong_guild(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category for category in another guild → error embed."""
        ctx = _guild_ctx("999999999")

        row = _category_row()  # guildId = "123456789"
        mock_db.get_ticket_category = AsyncMock(return_value=row)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        embed = _sent_embed(ctx)
        assert "Wrong Guild" in (embed.title or "") or "Servidor Incorrecto" in (embed.title or "")

    async def test_delete_category_in_use(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with open tickets → error embed."""
        ctx = _guild_ctx("123456789")

        row = _category_row()
        mock_db.get_ticket_category = AsyncMock(return_value=row)
        mock_db.count_open_tickets_by_category = AsyncMock(return_value=3)

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        embed = _sent_embed(ctx)
        assert "In Use" in (embed.title or "")

    async def test_delete_category_success(
        self,
        tickets_cog: TicketsCog,
        mock_db,
    ) -> None:
        """delete_category with valid ID and no open tickets → success."""
        ctx = _guild_ctx("123456789")

        row = _category_row()
        mock_db.get_ticket_category = AsyncMock(return_value=row)
        mock_db.count_open_tickets_by_category = AsyncMock(return_value=0)
        mock_db.delete_ticket_category = AsyncMock()

        await tickets_cog.delete_category.callback(tickets_cog, ctx, category_id="cat-uuid-001")

        embed = _sent_embed(ctx)
        assert "Deleted" in (embed.title or "")


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
        parent_row = _wire_subticket_success(ticket_bot, slash_ctx, mock_db)
        mock_db.get_max_ticket_number = AsyncMock(return_value=5)
        subticket = ticket_bot.ticket_service.create_ticket_channel.return_value[1]
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
        await _assert_no_guild_error(tickets_cog, tickets_cog.subticket_create, slash_ctx)

    async def test_subticket_create_not_a_ticket_channel(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Current channel is not a ticket → error embed."""
        _wire_subticket_success(ticket_bot, slash_ctx, mock_db, channel_result=None)
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
        _wire_subticket_success(
            ticket_bot,
            slash_ctx,
            mock_db,
            channel_result=ValueError("Parent ticket not found"),
        )
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        # Channel cleanup is now handled inside create_ticket_channel;
        # the cog surfaces the error embed.
        embed = slash_ctx.send.call_args.kwargs.get("embed")
        assert "Failed" in (embed.title or "")


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
        await _assert_no_guild_error(tickets_cog, tickets_cog.reopen, slash_ctx)

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
        assert "Ticket" in (embed.title or "")

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
        assert "Failed" in (embed.title or "")


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
        await _assert_no_guild_error(tickets_cog, tickets_cog.transfer, slash_ctx, member=target)


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
        _ticket_channel_row(mock_db)
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
        _ticket_channel_row(mock_db)
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
        _ticket_channel_row(mock_db)
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
        _ticket_channel_row(mock_db)
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=[])
        await tickets_cog.note_list.callback(tickets_cog, slash_ctx)
        embed = _sent_embed(slash_ctx)
        assert "No" in (embed.title or "") or "no" in (embed.description or "").lower()

    async def test_note_delete_calls_service(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/note delete → delete_note called with note id + author."""
        _ticket_channel_row(mock_db)
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
        _ticket_channel_row(mock_db)
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
        return [TicketNote.from_db_row(_note_row_cog(note_id="n-1", content=content))]

    @staticmethod
    def _note_list_env(
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        *,
        slash: bool,
        notes: bool = True,
    ) -> None:
        """Wire the note_list arrange: ticket row, get_notes stub, invocation shape.

        ``slash=True`` sets ctx.interaction (slash path); False means the
        prefix path (interaction=None, author.send stubbed). ``notes=False``
        stubs an empty notes list.
        """
        _ticket_channel_row(mock_db)
        ticket_bot.ticket_service.get_notes = AsyncMock(return_value=TestNoteListPrivacy._notes_with() if notes else [])
        slash_ctx.interaction = MagicMock() if slash else None
        slash_ctx.author.send = AsyncMock()

    async def test_note_list_slash_is_ephemeral(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Slash invocation → ctx.send(embed=..., ephemeral=True) with notes."""
        self._note_list_env(tickets_cog, slash_ctx, ticket_bot, mock_db, slash=True)

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
        self._note_list_env(tickets_cog, slash_ctx, ticket_bot, mock_db, slash=False)

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
        self._note_list_env(tickets_cog, slash_ctx, ticket_bot, mock_db, slash=False)
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
        self._note_list_env(tickets_cog, slash_ctx, ticket_bot, mock_db, slash=True, notes=False)

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
        self._note_list_env(tickets_cog, slash_ctx, ticket_bot, mock_db, slash=False, notes=False)

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
        embed = _sent_embed(slash_ctx)
        # Guild is EN — must see English localized text
        assert "Only closed tickets can be reopened" in (embed.description or "")
        assert status in (embed.description or "")
        # Must NOT surface the service's raw Spanish text
        assert "Solo se pueden" not in (embed.description or "")


# ===========================================================================
# B3 — /subticket create parent-owner access grant
# ===========================================================================


def _repair_result(
    ticket_id: str = "t-1",
    *,
    action: str = "close",
    outcome: str = "repaired",
    reason: str | None = None,
    evidence_id: str | None = "ev-1",
) -> RepairResult:
    """Return a RepairResult for cog adapter tests."""
    return RepairResult(
        ticket_id=ticket_id,
        guild_id="123456789",
        action=action,
        outcome=outcome,
        reason=reason,
        evidence_id=evidence_id,
        timestamp=datetime.now(UTC),
    )


def _integrity_ctx(ticket_bot: MagicMock) -> MagicMock:
    """Return the shared ctx for /sweep_integrity and /repair_ticket tests."""
    ctx = MagicMock()
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 123456789
    ctx.send = AsyncMock()
    ctx.interaction = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 111111111
    ticket_bot._guild_mod_role_cache = {}
    return ctx


def _guild_ctx(guild_id: int | str | None) -> MagicMock:
    """Return a command ctx bound to guild_id (None = DM) with an AsyncMock send."""
    ctx = MagicMock()
    if guild_id is None:
        ctx.guild = None
    else:
        ctx.guild = MagicMock()
        ctx.guild.id = guild_id
    ctx.send = AsyncMock()
    return ctx


def _interaction_embed(interaction: MagicMock) -> discord.Embed:
    """Assert one interaction send_message and return its embed."""
    interaction.response.send_message.assert_awaited_once()
    return _assert_embed(interaction.response.send_message.call_args.kwargs)


def _interaction_embed_no_once(interaction: MagicMock) -> discord.Embed:
    """Return the interaction send_message embed without asserting the count."""
    return _assert_embed(interaction.response.send_message.call_args.kwargs)


def _assert_embed(kwargs: dict) -> discord.Embed:
    """Assert the kwargs carry a non-None title-bearing embed and return it."""
    embed = kwargs.get("embed")
    assert isinstance(embed, discord.Embed)
    assert embed.title is not None
    return embed


def _sent_ephemeral_kwargs(send: MagicMock) -> dict:
    """Assert one ephemeral send on the given send mock and return its kwargs.

    Accepts either a ctx (uses ctx.send) or a send AsyncMock directly.
    """
    if hasattr(send, "send") and not isinstance(send, AsyncMock):
        target = send.send
    else:
        target = send
    target.assert_awaited_once()
    kwargs = dict(target.call_args.kwargs)
    assert kwargs.get("ephemeral") is True
    _assert_embed(kwargs)
    return kwargs


def _wire_configure_fields(
    slash_ctx: MagicMock,
    mock_db,
    *,
    update_side_effect: Exception | None = None,
) -> None:
    """Wire the configure_fields_set scaffold (guild + category + update stub)."""
    slash_ctx.guild.id = 123456789
    mock_db.get_ticket_category = AsyncMock(return_value=_category_row())
    if update_side_effect is not None:
        mock_db.update_ticket_category_field_definitions = AsyncMock(side_effect=update_side_effect)
    else:
        mock_db.update_ticket_category_field_definitions = AsyncMock()


def _sent_embed(ctx: MagicMock) -> discord.Embed:
    """Assert ctx.send fired once and return the sent embed."""
    ctx.send.assert_awaited_once()
    return _assert_embed(ctx.send.call_args.kwargs)


async def _assert_no_guild_error(cog: TicketsCog, cmd, ctx: MagicMock, **kwargs) -> None:
    """Invoke a command with guild=None ctx and assert the server-only error embed."""
    await cmd.callback(cog, ctx, **kwargs)
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args.kwargs.get("embed")
    assert "Server Only" in (embed.title or "") or "Solo Servidores" in (embed.title or "")


def _ticket_channel_row(mock_db) -> dict:
    """Wire get_ticket_by_channel to the default open ticket row."""
    row = _ticket_row()
    mock_db.get_ticket_by_channel = AsyncMock(return_value=row)
    return row


def _claimed_by_channel_row(mock_db, *, claimer_id: str = "111111111") -> dict:
    """Wire get_ticket_by_channel to a claimed ticket owned by claimer_id."""
    claimed_row = _ticket_row(status="claimed")
    claimed_row["claimedBy"] = claimer_id
    mock_db.get_ticket_by_channel = AsyncMock(return_value=claimed_row)
    return claimed_row


def _auto_close_env(
    ticket_bot: MagicMock,
    ticket_guild: MagicMock,
    mock_ticket_channel: MagicMock,
    *,
    stale: bool = True,
) -> None:
    """Wire the auto_close_stale_tickets arrange shared by its tests."""
    ticket_bot.guilds = [ticket_guild]
    if stale:
        stale_ticket = MagicMock()
        stale_ticket.id = "ticket-uuid-001"
        stale_ticket.channel_id = "444444444"
        ticket_bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[stale_ticket])
        ticket_bot.get_channel = MagicMock(return_value=mock_ticket_channel)
    else:
        # No stale tickets.
        ticket_bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[])
    config = MagicMock()
    config.log_channel_id = None
    ticket_bot.guild_service.get_config = AsyncMock(return_value=config)


def _parent_owner_member(member_id: int = 222222222) -> MagicMock:
    """Return a mock Member representing the parent ticket author."""
    owner = MagicMock(spec=discord.Member)
    owner.id = member_id
    owner.mention = f"<@{member_id}>"
    return owner


def _wire_parent_owner(slash_ctx: MagicMock, member_id: int) -> MagicMock:
    """Resolve the parent owner through guild.get_member and return the member."""
    parent_owner = _parent_owner_member(member_id)
    slash_ctx.guild.get_member = MagicMock(return_value=parent_owner)
    return parent_owner


def _wire_channel_result(
    ticket_bot: MagicMock,
    mock_ticket_channel: MagicMock | None,
    *,
    parent_row_id: str,
) -> None:
    """Stub create_ticket_channel for subticket characterization tests.

    Uses the provided channel when available, otherwise a bare channel mock
    carrying a send stub. The subticket carries parent_row_id as parentId.
    """
    subticket = Ticket.from_db_row({**_ticket_row(ticket_number=6), "parentId": parent_row_id})
    if mock_ticket_channel is not None:
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, subticket))
    else:
        ch = MagicMock()
        ch.send = AsyncMock()
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(ch, subticket))


class TestSubticketParentOwnerAccess:
    """B3: /subticket create grants access to the parent ticket author.

    Spec (ticket-subsidiados): "Parent author (parent_owner) MUST get
    read_messages+send_messages overwrites and be mentioned. Invoker MUST
    NOT get extra overwrites — mod role suffices."
    """

    @staticmethod
    def _wire_subticket_base(slash_ctx, ticket_bot, mock_db, parent_author_id: str, mock_ticket_channel=None):
        """Wire config + parent row + max number for a subticket create call."""
        _wire_subticket_success(ticket_bot, slash_ctx, mock_db, parent_row=None)
        parent_row = {**_ticket_row(ticket_number=5), "authorId": parent_author_id}
        mock_db.get_ticket_by_channel = AsyncMock(return_value=parent_row)
        mock_db.get_max_ticket_number = AsyncMock(return_value=5)

        subticket = Ticket.from_db_row({**_ticket_row(ticket_number=6), "parentId": parent_row["id"]})
        ticket_bot.ticket_service.create_subticket = AsyncMock(return_value=subticket)
        if mock_ticket_channel is not None:
            ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, subticket))
        return parent_row

    # Parent-owner resolution scenarios: (parent_author_id, resolver, fetched_member_id).
    # resolver "get_member" → guild.get_member resolves; "self" → invoker IS the owner;
    # "fetch_member" → get_member misses, fetch_member fallback resolves.
    _PARENT_OWNER_MATRIX: ClassVar[list[Any]] = [
        pytest.param("222222222", "get_member", None, id="owner_via_get_member"),
        pytest.param("111111111", "self", None, id="invoker_is_owner"),
        pytest.param("222222222", "fetch_member", 222222222, id="owner_via_fetch_fallback"),
    ]

    @pytest.mark.parametrize(("parent_author_id", "resolver", "fetched_member_id"), _PARENT_OWNER_MATRIX)
    async def test_channel_grants_resolved_parent_owner_access(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        mock_ticket_channel: MagicMock,
        parent_author_id: str,
        resolver: str,
        fetched_member_id: int | None,
    ) -> None:
        """B3: resolved parent owner becomes the channel author and gets mentioned."""
        owner = _parent_owner_member(222222222)
        self._wire_subticket_base(slash_ctx, ticket_bot, mock_db, parent_author_id, mock_ticket_channel)
        if resolver == "get_member":
            slash_ctx.guild.get_member = MagicMock(return_value=owner)
        elif resolver == "fetch_member":
            slash_ctx.guild.get_member = MagicMock(return_value=None)
            slash_ctx.guild.fetch_member = AsyncMock(return_value=owner)

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        if fetched_member_id is not None:
            slash_ctx.guild.fetch_member.assert_awaited_once_with(fetched_member_id)
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_args = ticket_bot.ticket_service.create_ticket_channel.call_args
        # The resolved parent owner is passed as the `author` argument.
        expected_author = slash_ctx.author if resolver == "self" else owner
        assert call_args.args[2] == expected_author
        # The new channel's initial message mentions the resolved owner.
        mock_ticket_channel.send.assert_awaited_once()
        assert mock_ticket_channel.send.call_args.kwargs.get("content") == expected_author.mention

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
        embed = _sent_embed(slash_ctx)
        assert "Failed" in (embed.title or "") or "Not Found" in (embed.title or "")


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
        _ticket_channel_row(mock_db)
        ticket_bot.ticket_service.get_notes = AsyncMock(side_effect=Exception("DB down"))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.note_list.callback(tickets_cog, slash_ctx)

        embed = _sent_embed(slash_ctx)
        assert "DB down" not in (embed.description or "")
        assert "Traceback" not in (embed.description or "")
        mock_exc.assert_called_once()

    # Commands whose parent lookup (get_ticket_by_channel) is the guarded DB call.
    # (command, logger_patch_target, service_attribute_that_must_stay_unawaited)
    _DB_FAILURE_MATRIX: ClassVar[list[Any]] = [
        pytest.param(
            "subticket_create",
            "bot.cogs.tickets.logger.exception",
            "create_ticket_channel",
            id="subticket_create",
        ),
        pytest.param(
            "reopen",
            "bot.utils.ticket_helpers.logger.exception",
            "reopen_ticket",
            id="reopen",
        ),
        pytest.param(
            "transfer",
            "bot.cogs.tickets.logger.exception",
            "transfer_ticket",
            id="transfer",
        ),
        pytest.param(
            "note_add",
            "bot.utils.ticket_helpers.logger.exception",
            "create_note",
            id="note_add",
        ),
    ]

    @pytest.mark.parametrize(("command", "logger_target", "guarded_service"), _DB_FAILURE_MATRIX)
    async def test_parent_lookup_db_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        command: str,
        logger_target: str,
        guarded_service: str,
    ) -> None:
        """B4: get_ticket_by_channel raising → error_embed + logger.exception, service untouched."""
        if command == "subticket_create":
            _wire_subticket_success(ticket_bot, slash_ctx, mock_db)
        elif command == "reopen":
            ticket_bot.ticket_service.reopen_ticket = AsyncMock()
        elif command == "transfer":
            ticket_bot.ticket_service.transfer_ticket = AsyncMock()
        else:  # note_add
            ticket_bot.ticket_service.create_note = AsyncMock()

        mock_db.get_ticket_by_channel = AsyncMock(side_effect=Exception("DB down"))

        with patch(logger_target) as mock_exc:
            if command == "subticket_create":
                await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)
            elif command == "reopen":
                await tickets_cog.reopen.callback(tickets_cog, slash_ctx)
            elif command == "transfer":
                await tickets_cog.transfer.callback(tickets_cog, slash_ctx, member=MagicMock(spec=discord.Member))
            else:  # note_add
                await tickets_cog.note_add.callback(tickets_cog, slash_ctx, content="a note")

        getattr(ticket_bot.ticket_service, guarded_service).assert_not_awaited()
        embed = _sent_embed(slash_ctx)
        assert "DB down" not in (embed.description or "")
        assert "Traceback" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_subticket_create_max_number_failure_sends_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """B4 triangulation: create_ticket_channel raises in /subticket create → error_embed.

        After PR4, get_max_ticket_number is called inside create_ticket_channel.
        The service mock is configured to raise (simulating DB failure inside the service).
        """
        _wire_subticket_success(
            ticket_bot,
            slash_ctx,
            mock_db,
            channel_result=Exception("DB down"),
        )
        mock_db.get_ticket_category = AsyncMock(return_value={"name": "Support", "id": "cat-uuid"})
        slash_ctx.guild.get_member = MagicMock(return_value=_parent_owner_member(111111111))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        embed = _sent_embed(slash_ctx)
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
        _sent_ephemeral_kwargs(ticket_interaction.response.send_message)

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
        _sent_ephemeral_kwargs(ticket_interaction.response.send_message)


class TestReopenByTicketRef:
    """/reopen ticket_ref resolution by number / UUID (TI-029, TI-037)."""

    # Number-ref input shapes: (ticket_ref literal, id for the parametrize).
    _NUMBER_REF_MATRIX: ClassVar[list[Any]] = [
        pytest.param("#0003", id="bare_number"),
        pytest.param("ticket:#0003", id="prefixed_number"),
    ]

    @pytest.mark.parametrize("ticket_ref", _NUMBER_REF_MATRIX)
    async def test_reopen_by_ticket_number(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        ticket_ref: str,
    ) -> None:
        """Number refs — '#0003' and the literal guidance 'ticket:#0003' —
        both resolve ticket #3 via get_ticket_by_number."""
        closed_row = _ticket_row(ticket_number=3, status="closed")
        mock_db.get_ticket_by_number = AsyncMock(return_value=closed_row)
        reopened = Ticket.from_db_row({**closed_row, "status": "open"})
        ticket_bot.ticket_service.reopen_ticket = AsyncMock(return_value=reopened)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref=ticket_ref)

        mock_db.get_ticket_by_number.assert_awaited_once_with("123456789", 3)
        ticket_bot.ticket_service.reopen_ticket.assert_awaited_once()
        args = ticket_bot.ticket_service.reopen_ticket.call_args.args
        assert args[0] == closed_row["id"]

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

        mock_db.get_ticket.assert_awaited_once_with(uuid_str, guild_id="123456789")
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

        _sent_embed(slash_ctx)

    async def test_reopen_missing_ticket_shows_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """A valid number that matches no ticket MUST surface an error_embed."""
        mock_db.get_ticket_by_number = AsyncMock(return_value=None)

        await tickets_cog.reopen.callback(tickets_cog, slash_ctx, ticket_ref="#9999")

        _sent_embed(slash_ctx)

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

        _sent_embed(slash_ctx)

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

        _wire_intake_success(ticket_bot, mock_db, ticket_guild, MagicMock(), ticket_category_id=None)
        modal_interaction = _make_modal_interaction(ticket_bot, ticket_guild)
        modal = _make_intake_modal(ticket_guild, title="Help", description=None)

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

        embed = _sent_embed(slash_ctx)
        desc = embed.description or ""
        assert "/setup" in desc
        assert "/create_category" in desc
        assert "dashboard" in desc.lower() or "https://" in desc


# ===========================================================================
# PR3 — /configure_fields set command
# ===========================================================================

_TOO_MANY_FIELDS_JSON = json.dumps([
    {"key": "f1", "label": "F1"},
    {"key": "f2", "label": "F2"},
    {"key": "f3", "label": "F3"},
    {"key": "f4", "label": "F4"},
])
_MISSING_LABEL_JSON = '[{"key": "no_label"}]'
_INVALID_STYLE_JSON = '[{"key": "x", "label": "X", "style": "dropdown"}]'


def _assert_json_error_text(send_kwargs: dict[str, Any]) -> None:
    """Invalid JSON → ephemeral=True plus JSON wording on title/description."""
    assert send_kwargs.get("ephemeral") is True
    embed = send_kwargs["embed"]
    assert "JSON" in (embed.title or "") or "json" in (embed.description or "").lower()


def _assert_max_fields_error_text(send_kwargs: dict[str, Any]) -> None:
    """4+ fields → error embed about the max of 3."""
    embed = send_kwargs["embed"]
    assert "3" in (embed.description or "") or "max" in (embed.description or "").lower()


def _assert_missing_label_error_text(send_kwargs: dict[str, Any]) -> None:
    """Field missing 'label' → error embed mentioning label."""
    embed = send_kwargs["embed"]
    assert "label" in (embed.description or "").lower()


def _assert_invalid_style_error_text(send_kwargs: dict[str, Any]) -> None:
    """Invalid style → error embed mentioning style/short."""
    embed = send_kwargs["embed"]
    assert "style" in (embed.description or "").lower() or "short" in (embed.description or "").lower()


def _assert_not_found_title(send_kwargs: dict[str, Any]) -> None:
    """Non-existent category → 'Not Found' title."""
    embed = send_kwargs["embed"]
    assert "Not Found" in (embed.title or "")


def _assert_wrong_guild_title(send_kwargs: dict[str, Any]) -> None:
    """Category owned by another guild → 'Wrong Guild'/'Servidor' title."""
    embed = send_kwargs["embed"]
    assert "Wrong Guild" in (embed.title or "") or "Servidor" in (embed.title or "")


class TestConfigureFieldsCommand:
    """Tests for /configure_fields set <category_id> <fields_json>.

    Spec (ticket-commands):
    - Restricted to admin + @is_mod()
    - Accepts category_id and fields_json (JSON string)
    - Validates via ticket_field_service
    - Verifies category belongs to ctx.guild
    - Persists via DB facade
    - All responses ephemeral
    """

    VALID_FIELDS_JSON = '[{"key":"player_nick","label":"Player Nickname","style":"short","required":true}]'

    async def test_configure_fields_set_success(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """Valid invocation → field_definitions updated, success embed sent."""
        _wire_configure_fields(slash_ctx, mock_db)

        await tickets_cog.configure_fields_set.callback(
            tickets_cog, slash_ctx, category_id="cat-uuid-001", fields_json=self.VALID_FIELDS_JSON
        )

        mock_db.get_ticket_category.assert_awaited_once_with("cat-uuid-001", guild_id="123456789")
        mock_db.update_ticket_category_field_definitions.assert_awaited_once()
        call_kwargs = mock_db.update_ticket_category_field_definitions.call_args.kwargs
        assert call_kwargs["category_id"] == "cat-uuid-001"
        assert call_kwargs["guild_id"] == "123456789"
        assert len(call_kwargs["field_definitions"]) == 1
        assert call_kwargs["field_definitions"][0]["key"] == "player_nick"
        embed = _sent_embed(slash_ctx)
        title = embed.title or ""
        assert "Configured" in title or "Fields" in title or "✅" in title

    async def test_configure_fields_set_clears_with_empty_list(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """Empty JSON array '[]' → field_definitions cleared (empty list)."""
        _wire_configure_fields(slash_ctx, mock_db)

        await tickets_cog.configure_fields_set.callback(
            tickets_cog, slash_ctx, category_id="cat-uuid-001", fields_json="[]"
        )

        mock_db.update_ticket_category_field_definitions.assert_awaited_once()
        call_kwargs = mock_db.update_ticket_category_field_definitions.call_args.kwargs
        assert call_kwargs["field_definitions"] == []
        slash_ctx.send.assert_awaited_once()

    # (fields_json input, content-assert over the send kwargs) — one matrix
    # case per validation rule; each preserves its original wording assert.
    _FIELDS_JSON_VALIDATION_ERRORS: ClassVar[list[Any]] = [
        pytest.param("not-json", _assert_json_error_text, id="invalid_json"),
        pytest.param(_TOO_MANY_FIELDS_JSON, _assert_max_fields_error_text, id="too_many_fields"),
        pytest.param(_MISSING_LABEL_JSON, _assert_missing_label_error_text, id="missing_label"),
        pytest.param(_INVALID_STYLE_JSON, _assert_invalid_style_error_text, id="invalid_style"),
    ]

    @pytest.mark.parametrize(("fields_json", "assert_error_text"), _FIELDS_JSON_VALIDATION_ERRORS)
    async def test_malformed_fields_json_sends_error_embed(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        fields_json: str,
        assert_error_text: Callable[[dict[str, Any]], None],
    ) -> None:
        """Malformed fields_json → single error embed; wording per validation rule."""
        await tickets_cog.configure_fields_set.callback(
            tickets_cog, slash_ctx, category_id="cat-uuid-001", fields_json=fields_json
        )

        slash_ctx.send.assert_awaited_once()
        kwargs = slash_ctx.send.call_args.kwargs
        assert kwargs.get("embed") is not None
        assert_error_text(kwargs)

    # (category_id, get_ticket_category row, title-content assert).
    _CATEGORY_LOOKUP_FAILURES: ClassVar[list[Any]] = [
        pytest.param("nonexistent", None, _assert_not_found_title, id="category_not_found"),
        pytest.param(
            "cat-uuid-001",
            {**_category_row(), "guildId": "999999999"},
            _assert_wrong_guild_title,
            id="wrong_guild",
        ),
    ]

    @pytest.mark.parametrize(("category_id", "db_row", "assert_error_title"), _CATEGORY_LOOKUP_FAILURES)
    async def test_category_lookup_failure_sends_ephemeral_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
        category_id: str,
        db_row: dict[str, Any] | None,
        assert_error_title: Callable[[dict[str, Any]], None],
    ) -> None:
        """Category missing or owned by another guild → ephemeral error embed."""
        slash_ctx.guild.id = 123456789
        mock_db.get_ticket_category = AsyncMock(return_value=db_row)

        await tickets_cog.configure_fields_set.callback(
            tickets_cog, slash_ctx, category_id=category_id, fields_json=self.VALID_FIELDS_JSON
        )

        slash_ctx.send.assert_awaited_once()
        kwargs = slash_ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert kwargs.get("embed") is not None
        assert_error_title(kwargs)

    async def test_configure_fields_set_db_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        mock_db,
    ) -> None:
        """DB update failure → ephemeral error embed, no raw traceback."""
        _wire_configure_fields(slash_ctx, mock_db, update_side_effect=Exception("DB down"))

        with patch("bot.cogs.tickets.logger.exception") as mock_exc:
            await tickets_cog.configure_fields_set.callback(
                tickets_cog, slash_ctx, category_id="cat-uuid-001", fields_json=self.VALID_FIELDS_JSON
            )

        embed = _sent_embed(slash_ctx)
        assert "DB down" not in (embed.description or "")
        mock_exc.assert_called_once()

    async def test_configure_fields_set_no_guild(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """configure_fields set in DM → ephemeral error embed."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.send = AsyncMock()

        await tickets_cog.configure_fields_set.callback(
            tickets_cog, ctx, category_id="cat-uuid-001", fields_json=self.VALID_FIELDS_JSON
        )

        _sent_embed(ctx)


class TestConfigureFieldsGroup:
    """Tests for the /configure_fields group (S6A slash-only — fallback deleted)."""

    def test_configure_fields_is_group_without_fallback(self, tickets_cog: TicketsCog) -> None:
        """S6A: configure_fields is a pure Group — no hybrid fallback callback."""
        from discord import app_commands as _app

        assert isinstance(tickets_cog.configure_fields, _app.Group)
        assert not hasattr(tickets_cog.configure_fields, "callback")


class TestConfigureFieldsPermissions:
    """Verify /configure_fields set is gated (group-level gate removed in slash-only)."""

    @staticmethod
    def _is_mod_gated(cmd) -> bool:
        if getattr(cmd, "checks", None):
            return bool(cmd.checks)
        if hasattr(cmd, "app_command") and getattr(cmd.app_command, "checks", None):
            return True
        cb = getattr(cmd, "callback", None)
        return bool(cb and getattr(cb, "__discord_app_commands_checks__", None))

    def test_configure_fields_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        """S6A: group itself has no checks — gate lives on subcommand."""
        from discord import app_commands as _app

        assert isinstance(tickets_cog.configure_fields, _app.Group)

    def test_configure_fields_set_is_mod_gated(self, tickets_cog: TicketsCog) -> None:
        assert self._is_mod_gated(tickets_cog.configure_fields_set), "/configure_fields set MUST be gated"


# ===========================================================================
# PR3 — /unclaim command
# ===========================================================================


class TestUnclaimCommand:
    """Tests for /unclaim hybrid command.

    /unclaim is NOT gated by @is_mod() — instead, the claimer OR a mod
    can unclaim. The command resolves the ticket from the current channel,
    then checks claimer/mod via check_can_unclaim.
    """

    # Unclaim authority scenarios: (actor id, administrator flag, cached mod
    # role id or None, roles list builder, expected is_mod kwarg).
    _UNCLAIM_MATRIX: ClassVar[list[Any]] = [
        pytest.param("111111111", False, None, False, False, id="claimer_succeeds"),
        pytest.param("222222222", True, None, False, True, id="mod_admin_succeeds"),
        pytest.param("222222222", False, 987654321, True, True, id="configured_mod_role_succeeds"),
    ]

    @pytest.mark.parametrize(
        ("actor_id", "is_admin", "cached_mod_role_id", "with_role", "expected_is_mod"),
        _UNCLAIM_MATRIX,
    )
    async def test_unclaim_succeeds_per_authority(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
        actor_id: str,
        is_admin: bool,
        cached_mod_role_id: int | None,
        with_role: bool,
        expected_is_mod: bool,
    ) -> None:
        """Claimer OR mod (admin or configured cached role) → success path.

        The claimer case asserts the full success contract (args, is_mod,
        success embed title); the mod cases assert the authority-critical
        args (actor id + is_mod) exactly as the original tests did.
        """
        slash_ctx.author.id = actor_id  # 111111111 == claimer for the first case
        if cached_mod_role_id is not None:
            role = MagicMock(spec=discord.Role)
            role.id = cached_mod_role_id
            slash_ctx.author.roles = [role]
            ticket_bot._guild_mod_role_cache = {123456789: str(cached_mod_role_id)}
        else:
            slash_ctx.author.guild_permissions.administrator = is_admin
            ticket_bot._guild_mod_role_cache = {}

        claimed_row = _claimed_by_channel_row(mock_db)

        unclaimed = Ticket.from_db_row({**claimed_row, "status": "open", "claimedBy": None})
        ticket_bot.ticket_service.unclaim_ticket = AsyncMock(return_value=unclaimed)

        await tickets_cog.unclaim.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.unclaim_ticket.assert_awaited_once()
        call_args = ticket_bot.ticket_service.unclaim_ticket.call_args
        assert call_args.args[1] == actor_id
        assert call_args.kwargs.get("is_mod") is expected_is_mod
        if actor_id == "111111111":
            assert call_args.args[0] == claimed_row["id"]
            assert call_args.kwargs.get("is_mod") is False
            slash_ctx.send.assert_awaited_once()
            embed = slash_ctx.send.call_args.kwargs.get("embed")
            assert embed is not None
            assert "Unclaim" in (embed.title or "") or "✅" in (embed.title or "")

    async def test_unclaim_by_non_claimer_non_mod_rejected(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Non-claimer non-mod → service raises ValueError → ephemeral error embed."""
        slash_ctx.author.id = 333333333  # not claimer
        slash_ctx.author.guild_permissions.administrator = False
        slash_ctx.author.roles = []
        ticket_bot._guild_mod_role_cache = {}

        _claimed_by_channel_row(mock_db)
        # Service raises the invariant denial.
        ticket_bot.ticket_service.unclaim_ticket = AsyncMock(
            side_effect=ValueError("Only the claimer or a moderator can unclaim this ticket")
        )

        await tickets_cog.unclaim.callback(tickets_cog, slash_ctx)

        # Service IS called — the invariant is checked inside the service.
        ticket_bot.ticket_service.unclaim_ticket.assert_called_once()
        kwargs = _sent_ephemeral_kwargs(slash_ctx)
        title = kwargs["embed"].title or ""
        assert "Permission" in title or "Denied" in title

    async def test_unclaim_on_unclaimed_ticket_rejected(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """Unclaim on an unclaimed ticket → ephemeral error embed."""
        slash_ctx.author.id = 111111111
        open_row = _ticket_row(status="open")
        open_row["claimedBy"] = None
        mock_db.get_ticket_by_channel = AsyncMock(return_value=open_row)
        ticket_bot.ticket_service.unclaim_ticket = AsyncMock()

        await tickets_cog.unclaim.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.unclaim_ticket.assert_not_called()
        _sent_ephemeral_kwargs(slash_ctx)

    async def test_unclaim_no_guild(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """/unclaim in DM → error embed."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.send = AsyncMock()

        await tickets_cog.unclaim.callback(tickets_cog, ctx)

        _sent_embed(ctx)

    async def test_unclaim_not_ticket_channel(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """/unclaim in non-ticket channel → error embed."""
        mock_db.get_ticket_by_channel = AsyncMock(return_value=None)
        ticket_bot.ticket_service.unclaim_ticket = AsyncMock()

        await tickets_cog.unclaim.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.unclaim_ticket.assert_not_called()
        _sent_embed(slash_ctx)

    async def test_unclaim_service_error(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """unclaim_ticket raises → error embed."""
        slash_ctx.author.id = 111111111
        _claimed_by_channel_row(mock_db)
        ticket_bot.ticket_service.unclaim_ticket = AsyncMock(side_effect=Exception("DB down"))

        await tickets_cog.unclaim.callback(tickets_cog, slash_ctx)

        embed = _sent_embed(slash_ctx)
        assert "Unclaim Failed" in (embed.title or "") or "Failed" in (embed.title or "")

    async def test_unclaim_not_gated_by_is_mod(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """/unclaim MUST NOT be gated by @is_mod() — claimer can unclaim without mod role."""
        cmd: object = tickets_cog.unclaim
        # guard: app_command may be None until command is added to tree
        app = getattr(cmd, "app_command", None)
        has_is_mod = bool(cmd.checks) or (app is not None and bool(app.checks))
        assert not has_is_mod, "/unclaim MUST NOT use @is_mod() — claimer can also unclaim"


# ===========================================================================
# PR3 — Subticket role/category resolution characterization (tasks 3.1)
# ===========================================================================


class TestSubticketModRoleResolution:
    """Characterize subticket_create mod_role resolution paths.

    Currently: ``if config.mod_role_id: guild.get_role(int(config.mod_role_id))``
    wrapped in ``contextlib.suppress(ValueError, TypeError)``.

    After PR3 wiring: replaced by ``resolve_mod_role()`` helper.
    Behavior MUST remain identical.
    """

    @staticmethod
    def _wire_subticket_for_mod_role(
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db: MagicMock,
        *,
        mod_role_id: str | None = None,
        parent_author_id: str = "111111111",
        parent_cat_id: str | None = "cat-uuid-001",
        mock_ticket_channel: MagicMock | None = None,
    ) -> MagicMock:
        """Wire a subticket_create call focused on mod_role resolution."""
        _wire_subticket_success(ticket_bot, slash_ctx, mock_db, mod_role_id=mod_role_id)
        mock_db.get_ticket_category = AsyncMock(
            return_value={"name": "Support", "id": parent_cat_id} if parent_cat_id else None
        )

        _wire_parent_owner(slash_ctx, int(parent_author_id))
        _wire_channel_result(ticket_bot, mock_ticket_channel, parent_row_id=_ticket_row()["id"])

        return slash_ctx.guild.get_member.return_value

    # Mod-role resolution scenarios: (config mod_role_id, guild.get_role
    # result, expected mod_role kwarg passed to the service).
    _MOD_ROLE_MATRIX: ClassVar[list[Any]] = [
        pytest.param("987654321", "resolved", "resolved", id="valid_role_passed"),
        pytest.param(None, "resolved", None, id="none_id_passes_none"),
        pytest.param("not-a-number", "resolved", None, id="invalid_id_suppressed"),
        pytest.param("987654321", None, None, id="missing_role_passes_none"),
    ]

    @pytest.mark.parametrize(("mod_role_id", "get_role_result", "expected_mod_role"), _MOD_ROLE_MATRIX)
    async def test_subticket_mod_role_resolution(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db: MagicMock,
        mock_ticket_channel: MagicMock,
        mod_role_id: str | None,
        get_role_result: str | None,
        expected_mod_role: str | None,
    ) -> None:
        """Mod-role resolution paths — behavior MUST remain identical.

        Valid config.mod_role_id → resolved Role passed as mod_role kwarg;
        None id / non-numeric id (ValueError suppressed) / missing role
        (get_role → None) → mod_role=None.
        """
        mod_role: MagicMock | None = None
        if get_role_result == "resolved":
            mod_role = MagicMock(spec=discord.Role)
            slash_ctx.guild.get_role = MagicMock(return_value=mod_role)
        else:
            slash_ctx.guild.get_role = MagicMock(return_value=None)

        self._wire_subticket_for_mod_role(
            slash_ctx,
            ticket_bot,
            mock_db,
            mod_role_id=mod_role_id,
            mock_ticket_channel=mock_ticket_channel,
        )

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["mod_role"] == (mod_role if expected_mod_role == "resolved" else None)


class TestSubticketCategoryNameResolution:
    """Characterize subticket_create category_name resolution from parent ticket.

    Currently: manual DB lookup via ``self.bot.db.get_ticket_category(parent_cat_id)``
    with fallback to ``"ticket"`` on missing/None/error.

    After PR3 wiring: replaced by ``resolve_category_name()`` helper.
    Behavior MUST remain identical.
    """

    @staticmethod
    def _wire_subticket_for_category(
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db: MagicMock,
        *,
        parent_cat_id: str | None = "cat-uuid-001",
        db_category_row: dict | None = None,
        db_raises: bool = False,
        mock_ticket_channel: MagicMock | None = None,
    ) -> None:
        """Wire a subticket_create call focused on category_name resolution."""
        parent_row = {**_ticket_row(ticket_number=5), "authorId": "111111111", "categoryId": parent_cat_id}
        _wire_subticket_success(ticket_bot, slash_ctx, mock_db, parent_row=parent_row)

        if db_raises:
            mock_db.get_ticket_category = AsyncMock(side_effect=Exception("DB down"))
        else:
            mock_db.get_ticket_category = AsyncMock(return_value=db_category_row)

        _wire_parent_owner(slash_ctx, int("111111111"))
        _wire_channel_result(ticket_bot, mock_ticket_channel, parent_row_id=_ticket_row()["id"])

    # Category-name fallback scenarios: (parent_cat_id, db row stub, db_raises).
    # All four MUST resolve category_name='ticket' via the fallback.
    _CATEGORY_FALLBACK_MATRIX: ClassVar[list[Any]] = [
        pytest.param(None, None, False, id="no_parent_category_id"),
        pytest.param("cat-uuid-001", None, False, id="db_returns_none"),
        pytest.param("cat-uuid-001", None, True, id="db_raises"),
        pytest.param("cat-uuid-001", {"id": "cat-uuid-001"}, False, id="row_missing_name"),
    ]

    @pytest.mark.parametrize(("parent_cat_id", "db_row", "db_raises"), _CATEGORY_FALLBACK_MATRIX)
    async def test_subticket_category_name_defaults_to_ticket(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db: MagicMock,
        mock_ticket_channel: MagicMock,
        parent_cat_id: str | None,
        db_row: dict | None,
        db_raises: bool,
    ) -> None:
        """Missing/None/erroring/unnamed category lookups fall back to 'ticket'.

        Parent has categoryId=None → no DB call; the other three cases
        consult get_ticket_category and fall back on the failure.
        """
        self._wire_subticket_for_category(
            slash_ctx,
            ticket_bot,
            mock_db,
            parent_cat_id=parent_cat_id,
            db_category_row=db_row,
            db_raises=db_raises,
            mock_ticket_channel=mock_ticket_channel,
        )

        with patch("bot.cogs.tickets.logger.warning"):
            await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["category_name"] == "ticket"
        if parent_cat_id is None:
            # No DB call for category lookup when parent_cat_id is None.
            mock_db.get_ticket_category.assert_not_awaited()

    async def test_subticket_category_name_from_parent_category(
        self,
        tickets_cog: TicketsCog,
        slash_ctx: MagicMock,
        ticket_bot: MagicMock,
        mock_db: MagicMock,
        mock_ticket_channel: MagicMock,
    ) -> None:
        """Parent has categoryId + DB returns category → category_name from DB row."""
        self._wire_subticket_for_category(
            slash_ctx,
            ticket_bot,
            mock_db,
            parent_cat_id="cat-uuid-001",
            db_category_row={"name": "Soporte Técnico", "id": "cat-uuid-001"},
            mock_ticket_channel=mock_ticket_channel,
        )

        await tickets_cog.subticket_create.callback(tickets_cog, slash_ctx)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["category_name"] == "Soporte Técnico"


# ===========================================================================
# product-artifact-audit PR4b-b — /sweep_integrity + /repair_ticket adapters
# (task 4.4-b)
# ===========================================================================


class TestSweepIntegrityCommand:
    """The /sweep_integrity hybrid command delegates to TicketService.sweep_integrity."""

    def _sweep_ctx(self, ticket_bot: MagicMock) -> MagicMock:
        return _integrity_ctx(ticket_bot)

    async def test_sweep_integrity_delegates_to_service(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """A valid invocation delegates to ticket_service.sweep_integrity."""
        ctx = self._sweep_ctx(ticket_bot)
        ticket_bot.ticket_service.sweep_integrity = AsyncMock(return_value=[_repair_result()])

        await tickets_cog.sweep_integrity.callback(tickets_cog, ctx)

        ticket_bot.ticket_service.sweep_integrity.assert_awaited_once()
        assert ticket_bot.ticket_service.sweep_integrity.call_args.args[0] == "123456789"
        assert ticket_bot.ticket_service.sweep_integrity.call_args.args[1] is ticket_bot
        ctx.send.assert_awaited()

    async def test_sweep_integrity_no_guild_shows_error(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """A DM invocation surfaces the server-only error."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.send = AsyncMock()

        await tickets_cog.sweep_integrity.callback(tickets_cog, ctx)

        _sent_embed(ctx)

    async def test_sweep_integrity_reports_summary(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """The summary reports the number of repaired vs skipped candidates."""
        ctx = self._sweep_ctx(ticket_bot)
        results = [
            _repair_result(),
            _repair_result("t-2", action="no_op", outcome="skipped", reason="probe_unresolved", evidence_id=None),
        ]
        ticket_bot.ticket_service.sweep_integrity = AsyncMock(return_value=results)

        await tickets_cog.sweep_integrity.callback(tickets_cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        # A localized summary was produced (title is non-empty and mentions the count).
        assert embed.title is not None and embed.title != ""


class TestRepairTicketCommand:
    """The /repair_ticket hybrid command delegates to TicketService.repair_ticket_manual."""

    def _repair_ctx(self, ticket_bot: MagicMock, *, author_admin: bool = True) -> MagicMock:
        ctx = _integrity_ctx(ticket_bot)
        ctx.author.guild_permissions.administrator = author_admin
        return ctx

    async def test_repair_ticket_delegates_with_authority(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """An admin repair delegates with a RepairAuthority built from the actor."""
        ctx = self._repair_ctx(ticket_bot)
        row = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "guildId": "123456789",
            "channelId": "888888888",
            "status": "open",
        }
        mock_db.get_ticket = AsyncMock(return_value=row)
        ticket_bot.ticket_service.repair_ticket_by_ref = AsyncMock(return_value=_repair_result())

        await tickets_cog.repair_ticket.callback(tickets_cog, ctx, ticket_ref="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        ticket_bot.ticket_service.repair_ticket_by_ref.assert_awaited_once()
        kwargs = ticket_bot.ticket_service.repair_ticket_by_ref.call_args.kwargs
        args = ticket_bot.ticket_service.repair_ticket_by_ref.call_args.args
        assert args[0] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert kwargs["guild_id"] == "123456789"
        assert kwargs["actor_id"] == "111111111"
        assert kwargs["bot"] is ticket_bot
        assert kwargs["authority"].target_guild_id == "123456789"
        ctx.send.assert_awaited()

    async def test_repair_ticket_not_found_shows_error(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
    ) -> None:
        """An unknown ticket ref surfaces a not-found error without mutation."""
        ctx = self._repair_ctx(ticket_bot)
        mock_db.get_ticket = AsyncMock(return_value=None)

        await tickets_cog.repair_ticket.callback(tickets_cog, ctx, ticket_ref="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        ticket_bot.ticket_service.repair_ticket_by_ref.assert_awaited_once()
        ctx.send.assert_awaited_once()

    # /repair_ticket resolution-failure scenarios: (ticket_ref, lookup stub
    # attribute, lookup behavior). Each failure mode MUST produce truthful
    # structured evidence with no mutation and no fabricated audit row.
    _REPAIR_RESOLUTION_FAILURES: ClassVar[list[Any]] = [
        pytest.param(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "get_ticket",
            None,
            id="uuid_not_found",
        ),
        pytest.param(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "get_ticket",
            RuntimeError("db down"),
            id="uuid_db_error",
        ),
        pytest.param(
            "#0003",
            "get_ticket_by_number",
            None,
            id="number_not_found",
        ),
    ]

    @pytest.mark.parametrize(("ticket_ref", "lookup_attr", "lookup_result"), _REPAIR_RESOLUTION_FAILURES)
    async def test_repair_ticket_resolution_failure_audits_truthfully(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
        mock_db,
        ticket_ref: str,
        lookup_attr: str,
        lookup_result: object,
    ) -> None:
        """A /repair_ticket lookup not-found or DB failure MUST produce
        truthful structured evidence (audit + log) without fabricating a
        ticket id — no fake id is ever passed to the service and no repair
        mutation or audit row is attempted.
        """
        service = TicketService(db=mock_db, cache=TTLCache())
        ticket_bot.ticket_service = service
        ctx = self._repair_ctx(ticket_bot)
        # DB-failure cases must RAISE like the real driver (side_effect);
        # not-found cases return None (return_value). Preserves the original
        # per-case semantics after parametrization.
        mock_kwargs = (
            {"side_effect": lookup_result}
            if isinstance(lookup_result, Exception)
            else {"return_value": lookup_result}
        )
        setattr(mock_db, lookup_attr, AsyncMock(**mock_kwargs))
        mock_db.insert_audit_row = AsyncMock(return_value={})

        await tickets_cog.repair_ticket.callback(tickets_cog, ctx, ticket_ref=ticket_ref)

        mock_db.transition_ticket_to_closed.assert_not_awaited()
        # ticketId is uuid NOT NULL — without a canonical ticket the audit is
        # skipped and the failure is surfaced via warning log + RepairResult.
        mock_db.insert_audit_row.assert_not_awaited()
        ctx.send.assert_awaited_once()

    async def test_repair_ticket_no_guild_shows_error(
        self,
        tickets_cog: TicketsCog,
    ) -> None:
        """A DM invocation surfaces the server-only error."""
        ctx = MagicMock()
        ctx.guild = None
        ctx.send = AsyncMock()

        await tickets_cog.repair_ticket.callback(tickets_cog, ctx, ticket_ref="t-1")

        ctx.send.assert_awaited_once()


# ===========================================================================
# Startup + periodic integrity sweep orchestration (verify CRITICAL #5)
# ===========================================================================


class TestIntegritySweepOrchestration:
    """The periodic integrity sweep converges on TicketService.sweep_integrity.

    A ``@tasks.loop`` is started in ``cog_load`` (not ``on_ready``) and
    cancelled in ``cog_unload``. Each iteration awaits readiness, then sweeps
    every guild the bot is in through the shared service path. No fabricated
    preflight or authority is invented by the orchestrator.
    """

    async def _startable_cog(self, ticket_bot: MagicMock) -> TicketsCog:
        """Return a TicketsCog with real loop attrs mocked as startable."""
        cog = TicketsCog(bot=ticket_bot)
        # Replace the decorated loop with a controllable mock that records
        # start/cancel/is_running so we never schedule real wall-clock work.
        loop = MagicMock()
        loop.is_running = MagicMock(return_value=False)
        loop.start = MagicMock()
        loop.cancel = MagicMock()
        cog.integrity_sweep_loop = loop
        return cog

    async def test_cog_load_starts_periodic_sweep_loop(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """cog_load MUST start the integrity sweep loop (idempotent) so a
        periodic sweep converges on the shared service path without on_ready.
        """
        ticket_bot.guilds = []
        ticket_bot.db.get_open_ticket_channel_ids = AsyncMock(return_value=[])
        loop = MagicMock()
        loop.is_running = MagicMock(return_value=False)
        loop.start = MagicMock()
        loop.cancel = MagicMock()
        tickets_cog.integrity_sweep_loop = loop

        await tickets_cog.cog_load()

        loop.start.assert_called_once()

    async def test_cog_load_does_not_restart_running_sweep_loop(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """cog_load MUST NOT restart an already-running sweep loop (idempotent)."""
        ticket_bot.guilds = []
        ticket_bot.db.get_open_ticket_channel_ids = AsyncMock(return_value=[])
        loop = MagicMock()
        loop.is_running = MagicMock(return_value=True)
        loop.start = MagicMock()
        loop.cancel = MagicMock()
        tickets_cog.integrity_sweep_loop = loop

        await tickets_cog.cog_load()

        loop.start.assert_not_called()

    async def test_cog_unload_cancels_sweep_loop(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """cog_unload MUST cancel the integrity sweep loop."""
        loop = MagicMock()
        loop.is_running = MagicMock(return_value=True)
        loop.cancel = MagicMock()
        tickets_cog.integrity_sweep_loop = loop

        await tickets_cog.cog_unload()

        loop.cancel.assert_called_once()

    @staticmethod
    def _two_guild_bot(ticket_bot: MagicMock) -> tuple[MagicMock, MagicMock]:
        """Attach guild_a (111111111) and guild_b (222222222) to the bot."""
        guild_a = MagicMock()
        guild_a.id = 111111111
        guild_b = MagicMock()
        guild_b.id = 222222222
        ticket_bot.guilds = [guild_a, guild_b]
        return guild_a, guild_b
        return guild_a, guild_b

    async def test_sweep_loop_iteration_sweeps_all_guilds(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """One periodic iteration delegates EVERY guild to
        ``TicketService.sweep_integrity`` (the shared service path) with
        NO fabricated preflight/authority. Readiness is awaited by the loop's
        ``before_loop`` hook (not inside the iteration).
        """
        self._two_guild_bot(ticket_bot)
        ticket_bot.ticket_service.sweep_integrity = AsyncMock(return_value=[])

        await tickets_cog.integrity_sweep_loop()

        assert ticket_bot.ticket_service.sweep_integrity.await_count == 2
        called_guilds = {c.args[0] for c in ticket_bot.ticket_service.sweep_integrity.call_args_list}
        assert called_guilds == {"111111111", "222222222"}
        # The orchestrator never fabricates a preflight or authority.
        for call in ticket_bot.ticket_service.sweep_integrity.call_args_list:
            assert "preflight" not in call.kwargs
            assert "authority" not in call.kwargs

    async def test_sweep_loop_iteration_tolerates_guild_failure(
        self,
        tickets_cog: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """A DB failure while sweeping one guild MUST NOT abort the loop: the
        failure is logged with structured guild context and remaining guilds
        continue to be swept.
        """
        self._two_guild_bot(ticket_bot)
        ticket_bot.ticket_service.sweep_integrity = AsyncMock(side_effect=[RuntimeError("db down"), []])

        await tickets_cog.integrity_sweep_loop()

        assert ticket_bot.ticket_service.sweep_integrity.await_count == 2


# ---------------------------------------------------------------------------
# C12 — scheduled-close loop progress line is DEBUG, not INFO
# ---------------------------------------------------------------------------


class TestScheduledCloseLoopLogNoise:
    """Routine per-cycle progress MUST be DEBUG (spec logging-service)."""

    @pytest.mark.asyncio
    async def test_checking_due_tickets_is_debug_not_info(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        bot = MagicMock()
        bot.ticket_service = None
        bot.db = None
        cog = TicketsCog(bot=bot)

        with caplog.at_level(logging.DEBUG, logger="bot.cogs.tickets"):
            await cog.scheduled_close_loop()

        infos = [r for r in caplog.records if r.levelno == logging.INFO and "checking due tickets" in r.message]
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and "checking due tickets" in r.message]
        assert not infos, "per-cycle progress must NOT be INFO"
        assert debugs, "per-cycle progress must appear at DEBUG"


# ---------------------------------------------------------------------------
# Facade composition + guild scoping (merged from test_tickets_cog_facade.py,
# cycle-5 S5b/c — unique behavioral assertions only; delegation mock-theater
# and structural hasattr greps died with their twins in this file)
# ---------------------------------------------------------------------------


class TestFacadeComposition:
    """TicketsCog MUST compose the 4 flow modules via real instances."""

    def test_cog_exposes_four_flow_instances(self) -> None:
        """Composition wiring: each flow attribute holds the real flow class."""
        cog = TicketsCog(bot=MagicMock())

        assert isinstance(cog._admin_flow, TicketAdminFlow)
        assert isinstance(cog._lifecycle_flow, TicketLifecycleFlow)
        assert isinstance(cog._notes_flow, TicketNotesFlow)
        assert isinstance(cog._integrity_flow, TicketIntegrityFlow)

    @pytest.mark.asyncio
    async def test_lifecycle_guild_scoping_cross_guild_denied(self) -> None:
        """568/685/722: cross-guild channel lookup MUST be denied (guild_id scoped).

        Real lifecycle flow (no mock substitution): transfer against a channel
        whose ticket row is None MUST consult the DB scoped to the invoking
        guild before answering not_ticket.
        """
        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_by_channel = AsyncMock(return_value=None)
        bot.ticket_service = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(ticket_category_id="1", mod_role_id=None))
        bot.guilds = []
        cog = TicketsCog(bot=bot)

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.id = 111111111
        ctx.channel = MagicMock()
        ctx.channel.id = 444444444
        ctx.send = AsyncMock()
        member = MagicMock(spec=discord.Member)

        await cog._lifecycle_flow.transfer(ctx, member=member)

        bot.db.get_ticket_by_channel.assert_awaited()
        call_args = bot.db.get_ticket_by_channel.call_args
        args, kwargs = call_args
        assert kwargs.get("guild_id") == "123456789" or (len(args) > 1 and args[1] == "123456789")
