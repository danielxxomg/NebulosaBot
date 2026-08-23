"""Regression: service-domain errors must still deliver error_embed (BLE001 narrowing fix).

The BLE001 narrowing diff (366f180) rewrote `except Exception` → `except ImportError`
on service/database call sites. Service methods raise ValueError/RuntimeError/
discord.HTTPException, never ImportError → errors escaped as "interaction failed"
instead of localized error_embed. This file pins the domain-error path.

TDD RED → GREEN:
 - RED on pre-fix code: ValueError/HTTPException escapes (pytest raises), no embed.
 - GREEN after fix: exception caught, logger.exception + error_embed delivered.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim_interaction(
    *,
    guild_id: int = 123456789,
    user_id: int = 222222222,
    channel_id: int = 888888888,
    ticket_row: dict | None = None,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.original_response = AsyncMock()

    guild = MagicMock()
    guild.id = guild_id
    interaction.guild = guild
    # needed by transfer_ticket (guild param)
    interaction.guild_id = guild_id

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.guild_permissions = MagicMock()
    user.guild_permissions.administrator = True
    user.roles = []
    interaction.user = user

    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()

    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)
    bot._guild_mod_role_cache = {}
    bot.ticket_service = MagicMock()
    bot.ticket_service.claim_ticket = AsyncMock()
    bot.ticket_service.transfer_ticket = AsyncMock()
    bot.ticket_service.close_ticket_full = AsyncMock()
    bot.logging_service = MagicMock()
    interaction.client = bot
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.id = channel_id
    # message for embed refresh after transfer
    interaction.message = MagicMock()
    interaction.message.edit = AsyncMock()
    return interaction


def _make_close_interaction(
    *,
    guild_id: int = 123456789,
    user_id: int = 111111111,
    channel_id: int = 888888888,
    ticket_row: dict | None = None,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.original_response = AsyncMock()
    interaction.response.is_done.return_value = False

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    interaction.guild = guild

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.guild_permissions = MagicMock()
    user.guild_permissions.administrator = True
    user.roles = []
    interaction.user = user

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.guild = guild
    interaction.channel = channel

    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.get_ticket_by_channel = AsyncMock(return_value=ticket_row)
    bot.ticket_service = MagicMock()
    bot.ticket_service.close_ticket_full = AsyncMock(return_value=None)
    interaction.client = bot
    return interaction


def _open_ticket_row() -> dict:
    return {
        "id": "ticket-uuid-open",
        "ticketNumber": 1,
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


def _claimed_ticket_row() -> dict:
    return {
        "id": "ticket-uuid-claimed",
        "ticketNumber": 5,
        "guildId": "123456789",
        "authorId": "111111111",
        "channelId": "888888888",
        "categoryId": None,
        "status": "claimed",
        "claimedBy": "111111111",
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# RED regression tests
# ---------------------------------------------------------------------------


class TestClaimTicketDomainErrorStillShowsEmbed:
    @pytest.mark.asyncio
    async def test_claim_valueerror_delivers_error_embed_not_propagate(self) -> None:
        """claim_ticket ValueError (already claimed race) MUST deliver error_embed, not propagate."""
        from bot.views.ticket_actions import TicketActionsView

        ticket_row = _open_ticket_row()
        interaction = _make_claim_interaction(ticket_row=ticket_row)
        # Simulate race: service raises ValueError (already claimed)
        interaction.client.ticket_service.claim_ticket = AsyncMock(side_effect=ValueError("already claimed"))

        view = TicketActionsView(guild_id="123456789")
        # Should NOT raise; must send ephemeral error_embed
        await view.claim_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
        # localized keys: claim_failed + generic_error or already_claimed
        # We assert an embed was sent (error path), not success
        assert embed.title is not None or embed.description is not None
        # Ensure service was called
        interaction.client.ticket_service.claim_ticket.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_runtimeerror_delivers_error_embed(self) -> None:
        """claim_ticket RuntimeError MUST also be caught and show error_embed."""
        from bot.views.ticket_actions import TicketActionsView

        ticket_row = _open_ticket_row()
        interaction = _make_claim_interaction(ticket_row=ticket_row)
        interaction.client.ticket_service.claim_ticket = AsyncMock(side_effect=RuntimeError("DB write failed"))

        view = TicketActionsView(guild_id="123456789")
        await view.claim_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


class TestTransferTicketDomainErrorStillShowsEmbed:
    @pytest.mark.asyncio
    async def test_transfer_valueerror_delivers_error_embed(self) -> None:
        """transfer_ticket ValueError (same claimant, TI-010) MUST edit message with error_embed."""
        from bot.views.ticket_actions import TicketActionsView

        claimed_row = _claimed_ticket_row()
        interaction = _make_claim_interaction(ticket_row=claimed_row, user_id=222222222)
        # Need guild for transfer_ticket kwargs
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        interaction.guild = guild

        view = TicketActionsView(guild_id="123456789")
        await view.claim_button.callback(interaction)

        # Should have sent ConfirmCancelView
        interaction.response.send_message.assert_awaited_once()
        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        # Mock transfer to raise ValueError (same claimant)
        interaction.client.ticket_service.transfer_ticket = AsyncMock(
            side_effect=ValueError("Cannot transfer a ticket to the same staff member who already claimed it")
        )

        confirm_interaction = MagicMock(spec=discord.Interaction)
        confirm_interaction.user = interaction.user
        confirm_interaction.response = MagicMock()
        confirm_interaction.response.edit_message = AsyncMock()
        confirm_interaction.followup = MagicMock()
        confirm_interaction.followup.send = AsyncMock()
        confirm_interaction.client = interaction.client
        confirm_interaction.guild = guild

        await sent_view._on_confirm(confirm_interaction)

        confirm_interaction.response.edit_message.assert_awaited_once()
        kwargs = confirm_interaction.response.edit_message.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        # Must be transfer failed embed, not success
        # We assert edit was called with an embed (error path)
        assert kwargs.get("view") is None


class TestCloseTicketDomainErrorStillShowsEmbed:
    @pytest.mark.asyncio
    async def test_close_httpexception_delivers_error_embed(self) -> None:
        """close_ticket_full HTTPException (transcript) MUST followup with error_embed."""
        from bot.views.ticket_actions import TicketActionsView

        ticket_row = _open_ticket_row()
        interaction = _make_close_interaction(ticket_row=ticket_row)
        view = TicketActionsView(guild_id="123456789")
        await view.close_button.callback(interaction)

        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        # Mock close to raise HTTPException
        interaction.client.ticket_service.close_ticket_full = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "transcript upload failed")
        )

        confirm_interaction = MagicMock(spec=discord.Interaction)
        confirm_interaction.user = interaction.user
        confirm_interaction.response = MagicMock()
        confirm_interaction.response.edit_message = AsyncMock()
        confirm_interaction.followup = MagicMock()
        confirm_interaction.followup.send = AsyncMock()
        confirm_interaction.channel = interaction.channel
        confirm_interaction.guild = interaction.guild
        confirm_interaction.guild_id = interaction.guild_id
        confirm_interaction.client = interaction.client

        await sent_view._on_confirm(confirm_interaction)

        confirm_interaction.followup.send.assert_awaited_once()
        kwargs = confirm_interaction.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert kwargs.get("embed") is not None

    @pytest.mark.asyncio
    async def test_close_valueerror_delivers_error_embed(self) -> None:
        """close_ticket_full ValueError (already closed) MUST followup with error_embed."""
        from bot.views.ticket_actions import TicketActionsView

        ticket_row = _open_ticket_row()
        interaction = _make_close_interaction(ticket_row=ticket_row)
        view = TicketActionsView(guild_id="123456789")
        await view.close_button.callback(interaction)

        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        interaction.client.ticket_service.close_ticket_full = AsyncMock(
            side_effect=ValueError("Ticket already closed or not found")
        )

        confirm_interaction = MagicMock(spec=discord.Interaction)
        confirm_interaction.user = interaction.user
        confirm_interaction.response = MagicMock()
        confirm_interaction.response.edit_message = AsyncMock()
        confirm_interaction.followup = MagicMock()
        confirm_interaction.followup.send = AsyncMock()
        confirm_interaction.channel = interaction.channel
        confirm_interaction.guild = interaction.guild
        confirm_interaction.guild_id = interaction.guild_id
        confirm_interaction.client = interaction.client

        await sent_view._on_confirm(confirm_interaction)

        confirm_interaction.followup.send.assert_awaited_once()
        assert confirm_interaction.followup.send.call_args.kwargs.get("embed") is not None


class TestCreateTicketChannelFallbackStillShowsEmbed:
    @pytest.mark.asyncio
    async def test_create_ticket_runtimeerror_delivers_creation_failed(self) -> None:
        """create_ticket_channel RuntimeError MUST deliver creation_failed embed, not propagate."""
        from bot.views.ticket_panel import _create_ticket_after_modal

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.get_role = MagicMock(return_value=None)
        guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.CategoryChannel))

        bot = MagicMock()
        bot.db = MagicMock()
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=config)
        bot.ticket_service = MagicMock()
        bot.ticket_service.create_ticket_channel = AsyncMock(
            side_effect=RuntimeError("Failed to create ticket after 3 attempts")
        )

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild.get_channel = MagicMock(return_value=category_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.client = bot
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await _create_ticket_after_modal(interaction, guild, "cat-uuid", "Support", "Help", "desc")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        embed = kwargs.get("embed")
        assert embed is not None
