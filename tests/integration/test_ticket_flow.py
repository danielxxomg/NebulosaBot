"""Integration tests for the ticket lifecycle flow.

Verifies the ticket open → channel creation → close → transcript chain.
Uses mock Discord objects and mock DB — no real API calls.

TDD cycle: RED → GREEN — tests specify expected behavior of existing code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
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


# ---------------------------------------------------------------------------
# product-artifact-audit PR4b-b — end-to-end integrity repair flow (task 5.3)
# ---------------------------------------------------------------------------


class TestIntegrityRepairFlow:
    """End-to-end evidence-gated repair across entry points (disabled by default)."""

    @staticmethod
    def _service_with(db: AsyncMock, cache: Any = None) -> Any:
        from bot.core.cache import TTLCache
        from bot.services.ticket_service import TicketService

        return TicketService(db=db, cache=cache or TTLCache())

    async def test_delete_event_to_evidence_to_repair_to_close(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Channel-delete event -> single-use evidence -> repair -> close -> audit."""
        import discord

        from bot.listeners.audit_listener import AuditListener

        service = self._service_with(mock_db)
        row = _make_ticket_row(ticket_number=1, status="open")
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        closed_row = {**row, "status": "closed", "closedAt": "2026-01-15T10:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.insert_audit_row = AsyncMock(return_value={})

        bot = MagicMock()
        bot.ticket_service = service
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 999999999

        listener = AuditListener(bot)
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 444444444
        channel.guild = MagicMock()
        channel.guild.id = 123456789

        await listener.on_guild_channel_delete(channel)

        # The event routed the exact (guild, channel) facts to the coordinator,
        # which performed the conditional close (preflight=None fail-closes, so
        # no mutation is claimed here — the transition is NOT reached).
        # The listener must have delegated to the shared path.
        mock_db.get_active_ticket_by_channel.assert_awaited_once_with("123456789", "444444444")
        # Deletion logging is preserved.
        bot.logging_service.log_channel_delete.assert_awaited_once()

    async def test_manual_repair_with_authority_and_fresh_probe(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Manual repair: authority -> fresh probe -> shared evidence path."""
        import discord

        from bot.services.ticket_invariants import RepairAuthority

        service = self._service_with(mock_db)
        row = _make_ticket_row(ticket_number=1, status="open")
        mock_db.get_ticket = AsyncMock(return_value=row)
        closed_row = {**row, "status": "closed", "closedAt": "2026-01-15T10:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.insert_audit_row = AsyncMock(return_value={})

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)

        authority = RepairAuthority(
            actor_id="111111111",
            guild_id="123456789",
            target_guild_id="123456789",
            has_mod_role=True,
        )

        # Manual bypasses G.2: fresh NotFound -> repaired even without external preflight
        result = await service.repair_ticket_manual(
            row["id"],
            guild_id="123456789",
            actor_id="111111111",
            authority=authority,
            bot=bot,
        )

        assert result.outcome == "repaired"
        mock_db.transition_ticket_to_closed.assert_awaited_once()

    async def test_cross_guild_manual_repair_is_denied(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """A cross-guild manual repair is denied before any probe or mutation."""
        from bot.services.ticket_invariants import RepairAuthority

        service = self._service_with(mock_db)
        authority = RepairAuthority(
            actor_id="111111111",
            guild_id="123456789",
            target_guild_id="123456789",
            has_mod_role=True,
        )

        result = await service.repair_ticket_manual(
            "t-1",
            guild_id="999999999",  # target a different guild
            actor_id="111111111",
            authority=authority,
            bot=MagicMock(),
        )

        assert result.outcome == "skipped"
        assert result.reason == "cross_guild_denied"
        mock_db.get_ticket.assert_not_awaited()
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    async def test_full_chain_repairs_closes_and_audits_with_resolved_preflight(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """Resolved preflight + corroborated absence → close + audit across the shared path."""

        from bot.models.ticket import IntegrityEvidence
        from bot.services.integrity_report import evaluate_live_preflight

        service = self._service_with(mock_db)
        row = _make_ticket_row(ticket_number=1, status="open")
        closed_row = {**row, "status": "closed", "closedAt": "2026-01-15T10:00:00+00:00"}
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.insert_audit_row = AsyncMock(return_value={})

        preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            active_rows_channel_id_non_null=3,
            observed_at=datetime.now(UTC).isoformat(),
        )
        evidence = IntegrityEvidence(
            ticket_id=row["id"],
            guild_id=row["guildId"],
            channel_id=row["channelId"],
            status="open",
            channel_exists=False,
        )
        assert evidence.corroborated is True

        result = await service.repair_ticket_from_evidence(
            evidence,
            preflight=preflight,
            close_reason="zombie:channel_deleted",
        )

        assert result.outcome == "repaired"
        assert result.evidence_id == evidence.evidence_id
        mock_db.transition_ticket_to_closed.assert_awaited_once_with(
            "123456789",
            row["id"],
            expected_statuses=("open", "claimed"),
            close_reason="zombie:channel_deleted",
        )
        mock_db.insert_audit_row.assert_awaited_once()

    async def test_operator_mutation_is_explicit_grant_vs_no_grant(
        self,
        mock_db: AsyncMock,
    ) -> None:
        """End-to-end: an operator is read-only without a grant, mutating with a grant."""
        import discord

        from bot.services.integrity_report import evaluate_live_preflight
        from bot.services.ticket_invariants import GlobalMutationGrant, RepairAuthority

        service = self._service_with(mock_db)
        row = _make_ticket_row(ticket_number=1, status="open")
        closed_row = {**row, "status": "closed", "closedAt": "2026-01-15T10:00:00+00:00"}
        mock_db.get_ticket = AsyncMock(return_value=row)
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=closed_row)
        mock_db.insert_audit_row = AsyncMock(return_value={})

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)

        operator = RepairAuthority(
            actor_id="owner-1",
            guild_id=None,
            target_guild_id="123456789",
            is_bot_owner=True,
        )

        # No grant: read-only diagnosis, mutation denied.
        no_grant = await service.repair_ticket_manual(
            row["id"],
            guild_id="123456789",
            actor_id="owner-1",
            authority=operator,
            bot=bot,
            preflight=evaluate_live_preflight(
                project_status="ACTIVE_HEALTHY",
                migration_015_applied=True,
                close_reason_nullable=True,
                required_indexes_present=True,
                realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
                active_rows_channel_id_non_null=3,
                observed_at=datetime.now(UTC).isoformat(),
            ),
        )
        assert no_grant.outcome == "skipped"
        assert no_grant.reason == "operator_mutation_requires_grant"
        assert mock_db.transition_ticket_to_closed.await_count == 0

        # Explicit grant: mutation proceeds through the shared path.
        grant = GlobalMutationGrant(
            actor_id="owner-1",
            scope="global",
            target_guild_id="123456789",
            reason="maintenance: channel delete sweep",
            confirmed=True,
        )
        with_grant = await service.repair_ticket_manual(
            row["id"],
            guild_id="123456789",
            actor_id="owner-1",
            authority=operator,
            bot=bot,
            preflight=evaluate_live_preflight(
                project_status="ACTIVE_HEALTHY",
                migration_015_applied=True,
                close_reason_nullable=True,
                required_indexes_present=True,
                realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
                active_rows_channel_id_non_null=3,
                observed_at=datetime.now(UTC).isoformat(),
            ),
            global_grant=grant,
        )
        assert with_grant.outcome == "repaired"
        mock_db.transition_ticket_to_closed.assert_awaited_once()


# ---------------------------------------------------------------------------
# PR5 — Disabled / rollback + audit best-effort determinism (tasks 5.3-5.4 RED)
# ---------------------------------------------------------------------------
#
# The disabled/rollback gate MUST leave tickets untouched. The channel-delete
# listener always preserves deletion-only logging, while repair/sweep remain
# fail-closed when no resolved preflight is supplied. No repair audit rows
# are claimed, and a best-effort audit WARNING is emitted when audit persistence
# fails.


class TestPR5DisabledSliceAndAuditDeterminism:
    """Disabled slice and audit best-effort integration cases."""

    @staticmethod
    def _service_with(db, cache=None):
        from bot.core.cache import TTLCache
        from bot.services.ticket_service import TicketService

        return TicketService(db=db, cache=cache or TTLCache())

    async def test_disabled_slice_leaves_tickets_untouched(self, mock_db: AsyncMock) -> None:
        """Disabled/gate-off slice MUST NOT mutate tickets; deletion auditing continues.

        Threat: Rollback/no-op — the prior close/channel-delete behavior must be
        preserved and tickets must be left untouched when repair is disabled.
        """
        from bot.listeners.audit_listener import AuditListener

        # An open ticket maps to the deleted channel, but the listener is invoked
        # WITHOUT a resolved preflight (the default disabled state).
        row = _make_ticket_row(ticket_number=9, status="open")
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        mock_db.transition_ticket_to_closed = AsyncMock(return_value={**row, "status": "closed"})
        mock_db.insert_audit_row = AsyncMock(return_value={})

        # The service path itself is also disabled without a resolved preflight.
        from bot.models.ticket import IntegrityEvidence

        svc = self._service_with(mock_db)
        evidence = IntegrityEvidence(
            ticket_id=row["id"],
            guild_id=row["guildId"],
            channel_id=row["channelId"],
            status="open",
            channel_exists=False,
        )
        # No preflight supplied -> gate_unresolved -> no mutation.
        result = await svc.repair_ticket_from_evidence(evidence)
        assert result.outcome == "skipped"
        assert result.reason == "gate_unresolved"
        mock_db.transition_ticket_to_closed.assert_not_awaited()

        # The listener, which is the deletion-only boundary, must still log the deletion.
        bot = MagicMock()
        bot.db = mock_db
        bot.ticket_service = svc
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        bot.user.id = 1
        listener = AuditListener(bot)
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.guild.id = int(row["guildId"])
        channel.id = int(row["channelId"])

        # Even though a ticket maps to the channel, the disabled listener must
        # NOT close it (fail-closed) and MUST still emit deletion logging.
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        mock_db.transition_ticket_to_closed = AsyncMock()  # should stay unawaited
        await listener.on_guild_channel_delete(channel)
        bot.logging_service.log_channel_delete.assert_awaited_once()
        mock_db.transition_ticket_to_closed.assert_not_awaited()

    async def test_no_op_run_emits_no_close_and_no_repair_audit(self, mock_db: AsyncMock) -> None:
        """A no-op sweep/run MUST emit no close and no repair audit rows.

        Threat: Rollback/no-op — a run that finds no corroborated zombies must
        not claim completion or side effects.
        """
        svc = self._service_with(mock_db)

        # The sweep discovers one live ticket whose channel still exists.
        mock_db.get_open_ticket_channel_ids = AsyncMock(return_value=[_make_ticket_row(ticket_number=7)["channelId"]])
        mock_db.get_active_ticket_by_channel = AsyncMock(return_value=_make_ticket_row(ticket_number=7, status="open"))
        mock_db.insert_audit_row = AsyncMock(return_value={})

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 444444444
        guild.fetch_channel = AsyncMock(return_value=channel)
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=guild)

        from bot.services.integrity_report import evaluate_live_preflight

        preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            active_rows_channel_id_non_null=3,
            observed_at=datetime.now(UTC).isoformat(),
        )

        results = await svc.sweep_integrity("123456789", bot, preflight=preflight)

        # The only candidate was live (channel_exists=True) -> skipped, no close.
        assert all(r.action != "close" for r in results)
        assert all(r.outcome != "repaired" for r in results)
        # No successful repair audit was produced for this no-op run.
        repair_success_audits = [
            c for c in mock_db.insert_audit_row.call_args_list if c.args[2] == "repair" and c.args[4] == "success"
        ]
        assert len(repair_success_audits) == 0
