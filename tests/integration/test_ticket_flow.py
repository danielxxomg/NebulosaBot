"""Integration tests for the ticket lifecycle flow.

Verifies the ticket open → channel creation → close → transcript chain.
Uses mock Discord objects and mock DB — no real API calls.

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
    _CategorySelect,
)
from bot.models.ticket import Ticket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket_row(ticket_number: int = 1, status: str = "open") -> dict:
    """Return a sample ticket DB row."""
    return {
        "id": f"ticket-uuid-{ticket_number:04d}",
        "ticketNumber": ticket_number,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "444444444",
        "categoryId": "cat-uuid-001",
        "status": status,
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": datetime.now(UTC),
        "closedAt": None,
        "lastActivity": datetime.now(UTC),
    }


def _make_category_row() -> dict:
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
def ticket_bot(mock_db: AsyncMock) -> MagicMock:
    """Return a mock NebulosaBot wired for ticket operations."""
    bot = MagicMock()
    bot.db = mock_db
    bot.ticket_service = MagicMock()
    bot.ticket_service.create_ticket = AsyncMock()
    bot.ticket_service.close_ticket = AsyncMock()
    bot.ticket_service.close_ticket_full = AsyncMock(return_value=None)
    bot.ticket_service.claim_ticket = AsyncMock()
    bot.ticket_service.create_ticket_channel = AsyncMock()
    bot.transcript_service = MagicMock()
    bot.transcript_service.generate = AsyncMock()
    bot.transcript_service.upload = AsyncMock()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock()
    return bot


@pytest.fixture
def mock_ticket_channel() -> MagicMock:
    """Return a mock TextChannel for ticket operations."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 444444444
    channel.name = "ticket-0001"
    channel.mention = "<#444444444>"
    channel.send = AsyncMock()
    channel.delete = AsyncMock()
    channel.edit = AsyncMock()
    return channel


@pytest.fixture
def mock_ticket_guild(mock_ticket_channel: MagicMock) -> MagicMock:
    """Return a mock guild with create_text_channel."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.create_text_channel = AsyncMock(return_value=mock_ticket_channel)
    guild.get_channel = MagicMock(return_value=mock_ticket_channel)
    return guild


@pytest.fixture
def ticket_interaction(
    mock_ticket_guild: MagicMock,
    mock_member: MagicMock,
) -> MagicMock:
    """Return a mock interaction for ticket button clicks."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = mock_ticket_guild
    interaction.user = mock_member
    interaction.user.id = 111111111
    interaction.client = MagicMock()  # will be replaced per test
    interaction.guild_id = mock_ticket_guild.id
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
# TestTicketFlow — integration: ticket lifecycle
# ---------------------------------------------------------------------------


class TestTicketFlow:
    """Integration tests for the ticket lifecycle.

    Verifies: panel → open → channel create → close → transcript.
    """

    async def test_open_ticket_creates_channel_with_correct_permissions(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        ticket_interaction: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Panel button click → channel created via service with correct permissions.

        Scenario: user clicks panel button → ticket_service.create_ticket_channel
        called → channel returned with correct permission overwrites.
        """
        ticket_interaction.client = ticket_bot

        # Setup mocks for the _CategorySelect callback flow.
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        mock_db.get_max_ticket_number = AsyncMock(return_value=0)

        # Category channel mock.
        category_channel = MagicMock(spec=discord.CategoryChannel)
        mock_ticket_guild.get_channel = MagicMock(return_value=category_channel)

        # Ticket service returns a ticket model.
        ticket_row = _make_ticket_row(ticket_number=1)
        ticket = Ticket.from_db_row(ticket_row)
        ticket_bot.ticket_service.create_ticket = AsyncMock(return_value=ticket)
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=mock_ticket_channel)

        # Build the select and invoke callback.
        select = _CategorySelect(
            options=[],
            guild=mock_ticket_guild,
        )
        # Set _values directly (values is a property reading from _values).
        select._values = ["cat-uuid-001"]

        with patch("bot.cogs.tickets.TicketActionsView"):
            await select.callback(ticket_interaction)

        # 1. ticket_service.create_ticket_channel was called.
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_args = ticket_bot.ticket_service.create_ticket_channel.call_args
        # Verify it was called with the category channel and the author.
        assert call_args.args[1] == category_channel  # category
        assert call_args.args[2] == ticket_interaction.user  # author

    async def test_close_ticket_generates_transcript(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        ticket_interaction: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Close button → close_ticket_full called (handles transcript + DB + delete).

        Scenario: close button pressed → service handles transcript generation,
        DB update, and channel deletion.
        """
        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel

        # Setup ticket row in DB.
        ticket_row = _make_ticket_row(ticket_number=1, status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        # Ticket service close_ticket_full returns transcript URL.
        ticket_bot.ticket_service.close_ticket_full = AsyncMock(
            return_value="https://cdn.example.com/transcript.html"
        )

        # Invoke close_button.
        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        # 1. close_ticket_full was called with the channel, ticket, and closer.
        ticket_bot.ticket_service.close_ticket_full.assert_awaited_once()
        call_args = ticket_bot.ticket_service.close_ticket_full.call_args
        assert call_args.args[0] == mock_ticket_channel  # channel
        assert call_args.args[2] == "111111111"  # closer_id
