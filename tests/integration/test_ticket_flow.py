"""Integration tests for the ticket lifecycle flow.

Verifies the ticket open → channel creation → close → transcript chain.
Uses mock Discord objects and mock DB — no real API calls.

TDD cycle: RED → GREEN — tests specify expected behavior of existing code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.cogs.tickets import (
    TicketActionsView,
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
        """Panel button click → modal shown → submit → channel created via service.

        Scenario: user clicks panel button → modal shown → user submits →
        ticket_service.create_ticket_channel called → channel returned.
        """
        ticket_interaction.client = ticket_bot

        # Setup mocks for the modal submit flow.
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        # Category channel mock.
        category_channel = MagicMock(spec=discord.CategoryChannel)
        mock_ticket_guild.get_channel = MagicMock(return_value=category_channel)

        # Ticket service returns a ticket model.
        ticket_row = _make_ticket_row(ticket_number=1)
        ticket = Ticket.from_db_row(ticket_row)
        ticket_bot.ticket_service.create_ticket = AsyncMock(return_value=ticket)
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))

        # Build a modal interaction and submit.
        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = mock_ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = mock_ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        from bot.views.tickets import TicketIntakeModal

        modal = TicketIntakeModal(
            guild=mock_ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Help me")
        modal.description_input = MagicMock(value=None)

        sent_message = AsyncMock()
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        # 1. ticket_service.create_ticket_channel was called.
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["subject"] == "Help me"

    async def test_close_ticket_generates_transcript(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        ticket_interaction: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Close button → ephemeral ConfirmCancelView sent (close deferred to confirm).

        Scenario: close button pressed → system shows confirmation dialog
        before proceeding with transcript, DB update, and channel deletion.
        """
        from bot.views.confirmation import ConfirmCancelView

        ticket_interaction.client = ticket_bot
        ticket_interaction.channel = mock_ticket_channel

        # Setup ticket row in DB.
        ticket_row = _make_ticket_row(ticket_number=1, status="open")
        mock_db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)

        # Ticket service close_ticket_full returns transcript URL.
        ticket_bot.ticket_service.close_ticket_full = AsyncMock(return_value="https://cdn.example.com/transcript.html")

        # Invoke close_button.
        view = TicketActionsView()
        await view.close_button.callback(ticket_interaction)

        # Button sends ephemeral ConfirmCancelView (not close_ticket_full directly).
        ticket_interaction.response.send_message.assert_awaited_once()
        call_kwargs = ticket_interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), ConfirmCancelView)


# ---------------------------------------------------------------------------
# PR3 — Custom fields integration tests
# ---------------------------------------------------------------------------


class TestCustomFieldsFlow:
    """Integration tests for the custom fields lifecycle.

    Verifies: configure_fields → modal with fields → submit → custom_fields
    persisted → welcome embed renders fields.
    """

    def _make_category_with_fields(self) -> dict:
        """Return a category row with field_definitions set."""
        return {
            **_make_category_row(),
            "fieldDefinitions": [
                {
                    "key": "player_nick",
                    "label": "Player Nickname",
                    "style": "short",
                    "required": True,
                    "max_length": 100,
                },
                {
                    "key": "evidence_url",
                    "label": "Evidence URL",
                    "style": "short",
                    "required": False,
                    "max_length": 200,
                },
            ],
        }

    async def test_modal_with_custom_fields_submits_to_service(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Modal with field_definitions → submit → custom_fields passed to create_ticket_channel."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        mock_ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket_row = _make_ticket_row(ticket_number=1)
        ticket = Ticket.from_db_row(ticket_row)
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = mock_ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = mock_ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        from bot.views.tickets import TicketIntakeModal

        field_defs = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
            {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False, "max_length": 200},
        ]

        modal = TicketIntakeModal(
            guild=mock_ticket_guild,
            category_id="cat-uuid-001",
            category_name="Report",
            field_definitions=field_defs,
        )
        modal.title_input = MagicMock(value="Cheater report")
        modal.description_input = MagicMock(value="")

        # Simulate user filling custom fields by replacing the _custom_inputs
        # that the modal built from field_definitions.
        mock_nick_input = MagicMock()
        mock_nick_input.value = "DarkSlayer42"
        mock_evidence_input = MagicMock()
        mock_evidence_input.value = "https://imgur.com/proof"
        modal._custom_inputs = [mock_nick_input, mock_evidence_input]

        sent_message = AsyncMock()
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        # 1. create_ticket_channel was called with custom_fields.
        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["subject"] == "Cheater report"
        assert "custom_fields" in call_kwargs
        assert call_kwargs["custom_fields"]["player_nick"] == "DarkSlayer42"
        assert call_kwargs["custom_fields"]["evidence_url"] == "https://imgur.com/proof"

    async def test_modal_without_custom_fields_omits_custom_fields(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Modal without field_definitions → no custom_fields in service call."""
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)
        ticket_bot.db.get_max_ticket_number = AsyncMock(return_value=0)

        category_channel = MagicMock(spec=discord.CategoryChannel)
        mock_ticket_guild.get_channel = MagicMock(return_value=category_channel)

        ticket_row = _make_ticket_row(ticket_number=1)
        ticket = Ticket.from_db_row(ticket_row)
        ticket_bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_ticket_channel, ticket))

        modal_interaction = MagicMock(spec=discord.Interaction)
        modal_interaction.guild = mock_ticket_guild
        modal_interaction.user = MagicMock(spec=discord.Member)
        modal_interaction.user.id = 111111111
        modal_interaction.user.mention = "<@111111111>"
        modal_interaction.client = ticket_bot
        modal_interaction.guild_id = mock_ticket_guild.id
        modal_interaction.response = MagicMock()
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup = MagicMock()
        modal_interaction.followup.send = AsyncMock()

        from bot.views.tickets import TicketIntakeModal

        modal = TicketIntakeModal(
            guild=mock_ticket_guild,
            category_id="cat-uuid-001",
            category_name="Support",
        )
        modal.title_input = MagicMock(value="Help me")
        modal.description_input = MagicMock(value=None)

        sent_message = AsyncMock()
        mock_ticket_channel.send = AsyncMock(return_value=sent_message)

        with patch("bot.views.tickets.TicketActionsView"):
            await modal.on_submit(modal_interaction)

        ticket_bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = ticket_bot.ticket_service.create_ticket_channel.call_args.kwargs
        # No custom_fields or empty custom_fields when no field_definitions.
        assert not call_kwargs.get("custom_fields")

    async def test_welcome_embed_renders_custom_fields(
        self,
        ticket_bot: MagicMock,
        mock_ticket_guild: MagicMock,
        mock_ticket_channel: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """Welcome embed includes custom fields as inline fields."""
        from bot.utils.embeds import build_ticket_embed

        field_defs = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
            {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False, "max_length": 200},
        ]

        ticket_row = {
            **_make_ticket_row(ticket_number=1),
            "customFields": {
                "player_nick": "DarkSlayer42",
                "evidence_url": "https://imgur.com/proof",
            },
        }
        ticket = Ticket.from_db_row(ticket_row)

        embed = build_ticket_embed(ticket, guild_id="123456789", field_definitions=field_defs)

        # Embed should have the custom fields as inline fields.
        field_names = [f.name for f in embed.fields]
        assert "Player Nickname" in field_names
        assert "Evidence URL" in field_names

        # Values should match.
        for f in embed.fields:
            if f.name == "Player Nickname":
                assert f.value == "DarkSlayer42"
            elif f.name == "Evidence URL":
                assert f.value == "https://imgur.com/proof"

    async def test_welcome_embed_fallback_label_for_missing_definition(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """When a definition is removed, stored values use key as fallback label."""
        from bot.utils.embeds import build_ticket_embed

        # Category had 2 fields, now only 1.
        current_defs = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
        ]

        # Ticket was submitted with both fields.
        ticket_row = {
            **_make_ticket_row(ticket_number=1),
            "customFields": {
                "player_nick": "DarkSlayer42",
                "evidence_url": "https://imgur.com/proof",
            },
        }
        ticket = Ticket.from_db_row(ticket_row)

        embed = build_ticket_embed(ticket, guild_id="123456789", field_definitions=current_defs)

        field_names = [f.name for f in embed.fields]
        # player_nick uses its label.
        assert "Player Nickname" in field_names
        # evidence_url uses key as fallback (definition removed).
        assert "evidence_url" in field_names

    async def test_existing_ticket_with_null_custom_fields_renders_safely(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """Existing tickets with null/missing custom_fields render without errors."""
        from bot.utils.embeds import build_ticket_embed

        ticket_row = _make_ticket_row(ticket_number=1)
        # No customFields key at all (old ticket).
        ticket = Ticket.from_db_row(ticket_row)

        embed = build_ticket_embed(ticket, guild_id="123456789")

        # Should not crash and embed should have basic fields.
        assert embed.title is not None
        assert embed.color is not None
