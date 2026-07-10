"""Unit tests for ticket views — dynamic modal, embed rendering, i18n.

Covers Phase 2 of the ticket-category-fields change:
    - TicketIntakeModal with dynamic TextInputs from field_definitions
    - build_ticket_embed with custom_fields rendering
    - Validation of required custom fields on submit
    - i18n keys for field validation errors
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.models.ticket import Ticket
from bot.utils.embeds import build_ticket_embed

# ===========================================================================
# deploy_ticket_panel — shared helper (ticket-panel-persistence, Phase 2)
# ===========================================================================


class TestDeployTicketPanel:
    """Verify deploy_ticket_panel() sends embed+view, returns message, calls update_guild_panel."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_panel_view_and_returns_message(self) -> None:
        """deploy_ticket_panel() MUST send an embed with TicketPanelView and return the message."""
        from bot.views.tickets import TicketPanelView, deploy_ticket_panel

        channel = MagicMock()
        channel.id = 999
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()

        msg = await deploy_ticket_panel(channel, "123456789", bot=mock_bot)

        channel.send.assert_awaited_once()
        call_kwargs = channel.send.call_args.kwargs
        assert "embed" in call_kwargs
        assert "view" in call_kwargs
        assert isinstance(call_kwargs["view"], TicketPanelView)
        assert msg is mock_message

    @pytest.mark.asyncio
    async def test_calls_update_guild_panel_with_message_ids(self) -> None:
        """deploy_ticket_panel() MUST call guild_service.update_guild_panel() with the message/channel IDs."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.id = 999
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()

        await deploy_ticket_panel(channel, "123456789", bot=mock_bot)

        mock_bot.guild_service.update_guild_panel.assert_awaited_once_with(
            "123456789", str(42), str(999)
        )

    @pytest.mark.asyncio
    async def test_raises_on_forbidden(self) -> None:
        """deploy_ticket_panel() MUST propagate discord.Forbidden when channel.send() fails."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "missing perms"))

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()

        with pytest.raises(discord.Forbidden):
            await deploy_ticket_panel(channel, "123456789", bot=mock_bot)

    @pytest.mark.asyncio
    async def test_uses_custom_title_and_description(self) -> None:
        """deploy_ticket_panel(title=..., description_text=...) MUST pass them to the embed."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()

        await deploy_ticket_panel(
            channel, "123456789", bot=mock_bot,
            title="Soporte", description_text="Abre un ticket",
        )

        embed = channel.send.call_args.kwargs["embed"]
        assert embed.title == "Soporte"
        assert embed.description == "Abre un ticket"

    @pytest.mark.asyncio
    async def test_embed_footer_uses_bot_avatar_icon(self) -> None:
        """deploy_ticket_panel MUST set footer icon_url from bot.user.display_avatar."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()
        mock_bot.user = MagicMock()
        mock_bot.user.display_avatar = MagicMock()
        mock_bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot123/avatar.png"

        await deploy_ticket_panel(channel, "123456789", bot=mock_bot)

        embed = channel.send.call_args.kwargs["embed"]
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/bot123/avatar.png"

    @pytest.mark.asyncio
    async def test_embed_footer_uses_guild_icon_when_available(self) -> None:
        """deploy_ticket_panel MUST use guild.icon.url as footer icon when guild has an icon."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()
        mock_bot.user = MagicMock()
        mock_bot.user.display_avatar = MagicMock()
        mock_bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot123/avatar.png"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123456789
        mock_guild.icon = MagicMock()
        mock_guild.icon.url = "https://cdn.discordapp.com/icons/123456789/server.png"

        await deploy_ticket_panel(channel, "123456789", bot=mock_bot, guild=mock_guild)

        embed = channel.send.call_args.kwargs["embed"]
        assert embed.footer.icon_url == "https://cdn.discordapp.com/icons/123456789/server.png"

    @pytest.mark.asyncio
    async def test_embed_footer_falls_back_to_bot_avatar_when_guild_no_icon(self) -> None:
        """deploy_ticket_panel MUST fall back to bot avatar when guild has no custom icon."""
        from bot.views.tickets import deploy_ticket_panel

        channel = MagicMock()
        channel.send = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 42
        mock_message.channel = channel
        channel.send.return_value = mock_message

        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_bot.guild_service.update_guild_panel = AsyncMock()
        mock_bot.user = MagicMock()
        mock_bot.user.display_avatar = MagicMock()
        mock_bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot123/avatar.png"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123456789
        mock_guild.icon = None

        await deploy_ticket_panel(channel, "123456789", bot=mock_bot, guild=mock_guild)

        embed = channel.send.call_args.kwargs["embed"]
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/bot123/avatar.png"


# ===========================================================================
# build_ticket_embed — custom_fields rendering (task 2.5 RED)
# ===========================================================================


class TestBuildTicketEmbedCustomFields:
    """Verify build_ticket_embed renders custom fields as inline fields."""

    def test_no_custom_fields(self) -> None:
        """A ticket without custom_fields MUST render normally without extra fields."""
        ticket = Ticket(
            id="t1",
            ticket_number=1,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="open",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields=None,
        )
        embed = build_ticket_embed(ticket, guild_id="123")
        # Only author field and footer — no custom field entries.
        field_names = [f.name for f in embed.fields]
        assert "Player Nickname" not in field_names
        assert "Evidence URL" not in field_names

    def test_empty_custom_fields(self) -> None:
        """A ticket with custom_fields={} MUST render normally without extra fields."""
        ticket = Ticket(
            id="t2",
            ticket_number=2,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="open",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields={},
        )
        embed = build_ticket_embed(ticket, guild_id="123")
        # Only author/details fields — no custom field entries.
        # The author/details field names are localized, so count baseline fields.
        assert len(embed.fields) <= 2  # at most author + details

    def test_custom_fields_rendered_as_inline_fields(self) -> None:
        """Custom fields MUST appear as inline embed fields with their labels."""
        ticket = Ticket(
            id="t3",
            ticket_number=3,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="open",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields={"player_nick": "DarkSlayer42", "evidence_url": "https://imgur.com/abc"},
        )
        definitions = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
            {"key": "evidence_url", "label": "Evidence URL", "style": "short", "required": False, "max_length": 100},
        ]
        embed = build_ticket_embed(ticket, guild_id="123", field_definitions=definitions)
        field_names = [f.name for f in embed.fields]
        assert "Player Nickname" in field_names
        assert "Evidence URL" in field_names
        # Values match.
        for f in embed.fields:
            if f.name == "Player Nickname":
                assert f.value == "DarkSlayer42"
                assert f.inline is True
            elif f.name == "Evidence URL":
                assert f.value == "https://imgur.com/abc"
                assert f.inline is True

    def test_custom_field_value_truncated_for_display(self) -> None:
        """Custom field values exceeding Discord's 1024-char field limit MUST be truncated."""
        long_value = "x" * 1100
        ticket = Ticket(
            id="t4",
            ticket_number=4,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="open",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields={"evidence": long_value},
        )
        definitions = [
            {"key": "evidence", "label": "Evidence", "style": "short", "required": False, "max_length": 1000},
        ]
        embed = build_ticket_embed(ticket, guild_id="123", field_definitions=definitions)
        evidence_field = next(f for f in embed.fields if f.name == "Evidence")
        assert len(evidence_field.value) <= 1024
        assert evidence_field.value.endswith("...")

    def test_missing_definition_uses_key_as_fallback_label(self) -> None:
        """When a stored key has no matching definition, the key itself is used as label."""
        ticket = Ticket(
            id="t5",
            ticket_number=5,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="open",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields={"removed_field": "some value"},
        )
        embed = build_ticket_embed(ticket, guild_id="123", field_definitions=[])
        field_names = [f.name for f in embed.fields]
        assert "removed_field" in field_names

    def test_claimed_ticket_with_custom_fields(self) -> None:
        """A claimed ticket MUST also render custom fields."""
        ticket = Ticket(
            id="t6",
            ticket_number=6,
            guild_id="123",
            author_id="456",
            channel_id="789",
            status="claimed",
            claimed_by="999",
            created_at="2026-01-01T00:00:00",
            last_activity="2026-01-01T00:00:00",
            custom_fields={"player_nick": "DarkSlayer42"},
        )
        definitions = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
        ]
        embed = build_ticket_embed(ticket, guild_id="123", field_definitions=definitions)
        field_names = [f.name for f in embed.fields]
        assert "Player Nickname" in field_names


# ===========================================================================
# TicketIntakeModal — dynamic fields (task 2.3 RED)
# ===========================================================================


class TestTicketIntakeModalDynamicFields:
    """Verify TicketIntakeModal builds TextInputs from field_definitions."""

    def _make_modal(
        self,
        field_definitions: list[dict] | None = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Build a TicketIntakeModal with mocked dependencies.

        Returns (modal, guild) where guild.id = 123456789.
        """
        from bot.views.tickets import TicketIntakeModal

        guild = MagicMock()
        guild.id = 123456789

        modal = TicketIntakeModal(
            guild=guild,
            category_id="cat-uuid-001",
            category_name="Reportes",
            field_definitions=field_definitions or [],
        )
        return modal, guild

    def test_no_field_definitions_has_two_inputs(self) -> None:
        """With no field_definitions, modal MUST have exactly 2 TextInputs (title + desc)."""
        modal, _ = self._make_modal(field_definitions=[])
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) == 2

    def test_single_field_definition_adds_third_input(self) -> None:
        """With 1 field_definition, modal MUST have 3 TextInputs."""
        defs = [
            {"key": "player_nick", "label": "Player Nickname", "style": "short", "required": True, "max_length": 100},
        ]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) == 3
        # Third input label is the field label (use serialized payload to avoid
        # deprecated TextInput.label property).
        assert text_inputs[2].to_component_dict()["label"] == "Player Nickname"

    def test_three_field_definitions_adds_five_inputs(self) -> None:
        """With 3 field_definitions, modal MUST have 5 TextInputs (Discord max)."""
        defs = [
            {"key": "a", "label": "Field A", "style": "short", "required": True, "max_length": 100},
            {"key": "b", "label": "Field B", "style": "short", "required": False, "max_length": 100},
            {"key": "c", "label": "Field C", "style": "paragraph", "required": False, "max_length": 500},
        ]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) == 5

    def test_paragraph_field_uses_paragraph_style(self) -> None:
        """A field with style='paragraph' MUST use TextStyle.paragraph."""
        defs = [{"key": "details", "label": "Details", "style": "paragraph", "required": False, "max_length": 500}]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert text_inputs[2].style == discord.TextStyle.paragraph

    def test_required_field_marks_input_required(self) -> None:
        """A field with required=True MUST set the TextInput's required attribute."""
        defs = [{"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert text_inputs[2].required is True

    def test_optional_field_marks_input_not_required(self) -> None:
        """A field with required=False MUST set the TextInput's required attribute to False."""
        defs = [{"key": "evidence_url", "label": "Evidence", "style": "short", "required": False, "max_length": 100}]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert text_inputs[2].required is False

    def test_placeholder_set_on_input(self) -> None:
        """A field with placeholder MUST set it on the TextInput."""
        defs = [
            {
                "key": "player_nick",
                "label": "Nick",
                "style": "short",
                "required": True,
                "max_length": 100,
                "placeholder": "In-game name",
            },
        ]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert text_inputs[2].placeholder == "In-game name"

    def test_max_length_set_on_input(self) -> None:
        """A field with max_length MUST set it on the TextInput."""
        defs = [{"key": "code", "label": "Code", "style": "short", "required": False, "max_length": 50}]
        modal, _ = self._make_modal(field_definitions=defs)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert text_inputs[2].max_length == 50


class TestTicketIntakeModalSubmit:
    """Verify TicketIntakeModal.on_submit validates and passes custom_fields."""

    @staticmethod
    def _make_mock_input(value: str = "", label: str = "Test") -> MagicMock:
        """Return a mock TextInput with settable value."""
        inp = MagicMock(spec=discord.ui.TextInput)
        inp.value = value
        inp.label = label
        return inp

    def _build_modal_with_mocked_inputs(
        self,
        field_definitions: list[dict],
        title_value: str = "Help me",
        desc_value: str = "",
        custom_values: list[str] | None = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Build a TicketIntakeModal and replace its inputs with settable mocks."""
        from bot.views.tickets import TicketIntakeModal

        guild = MagicMock()
        guild.id = 123456789
        modal = TicketIntakeModal(guild, "cat-uuid", "Reportes", field_definitions=field_definitions)

        # Replace the real TextInput objects with mocks that allow value setting.
        mock_title = self._make_mock_input(title_value, "Title")
        mock_desc = self._make_mock_input(desc_value, "Description")
        modal.title_input = mock_title  # type: ignore[assignment]
        modal.description_input = mock_desc  # type: ignore[assignment]

        # Replace dynamic custom inputs.
        if custom_values is None:
            custom_values = []
        mock_custom = []
        for i, defn in enumerate(field_definitions):
            val = custom_values[i] if i < len(custom_values) else ""
            mock_custom.append(self._make_mock_input(val, defn["label"]))
        modal._custom_inputs = mock_custom  # type: ignore[assignment]

        return modal, guild

    @pytest.mark.asyncio
    async def test_submit_with_custom_fields_passes_to_create(self) -> None:
        """on_submit MUST collect dynamic field values into custom_fields and pass to _create_ticket_after_modal."""

        defs = [{"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}]
        modal, _ = self._build_modal_with_mocked_inputs(defs, custom_values=["DarkSlayer42"])

        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.mention = "<@456>"

        with patch("bot.views.tickets._create_ticket_after_modal", new_callable=AsyncMock) as mock_create:
            await modal.on_submit(interaction)

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["custom_fields"] == {"player_nick": "DarkSlayer42"}

    @pytest.mark.asyncio
    async def test_submit_required_field_empty_shows_error(self) -> None:
        """on_submit with a blank required field MUST send an ephemeral error and NOT create a ticket."""

        defs = [{"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}]
        modal, _ = self._build_modal_with_mocked_inputs(defs, custom_values=[""])

        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        with patch("bot.views.tickets._create_ticket_after_modal", new_callable=AsyncMock) as mock_create:
            await modal.on_submit(interaction)

        # Error sent, no ticket creation.
        interaction.response.send_message.assert_awaited_once()
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_submit_optional_field_empty_excluded(self) -> None:
        """on_submit with a blank optional field MUST exclude it from custom_fields."""

        defs = [
            {"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100},
            {"key": "evidence_url", "label": "Evidence", "style": "short", "required": False, "max_length": 100},
        ]
        modal, _ = self._build_modal_with_mocked_inputs(
            defs, custom_values=["DarkSlayer42", ""]
        )

        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.mention = "<@456>"

        with patch("bot.views.tickets._create_ticket_after_modal", new_callable=AsyncMock) as mock_create:
            await modal.on_submit(interaction)

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["custom_fields"] == {"player_nick": "DarkSlayer42"}
        assert "evidence_url" not in call_kwargs["custom_fields"]

    @pytest.mark.asyncio
    async def test_submit_no_definitions_passes_empty_custom_fields(self) -> None:
        """on_submit with no field_definitions MUST pass custom_fields={} to create."""

        modal, _ = self._build_modal_with_mocked_inputs([], custom_values=[])

        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.mention = "<@456>"

        with patch("bot.views.tickets._create_ticket_after_modal", new_callable=AsyncMock) as mock_create:
            await modal.on_submit(interaction)

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["custom_fields"] == {}


# ===========================================================================
# PR2 — Close Confirmation (task 2.2.1 RED)
# ===========================================================================


class TestCloseButtonConfirmation:
    """Verify close button sends ephemeral ConfirmCancelView before closing."""

    @staticmethod
    def _make_close_interaction(
        *,
        guild_id: int = 123456789,
        user_id: int = 111111111,
        channel_id: int = 888888888,
        is_author: bool = True,
    ) -> MagicMock:
        """Return a mock Interaction wired for the close button callback."""

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild_id = guild_id
        interaction.channel_id = channel_id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.response.is_done.return_value = False
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.original_response = AsyncMock()

        guild = MagicMock()
        guild.id = guild_id
        interaction.guild = guild

        user = MagicMock(spec=discord.Member)
        user.id = user_id
        interaction.user = user

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.send = AsyncMock()
        interaction.channel = channel

        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_by_channel = AsyncMock()
        bot.guild_service = MagicMock()
        bot.ticket_service = MagicMock()
        interaction.client = bot

        return interaction

    @staticmethod
    def _ticket_row_for_close(*, author_id: str = "111111111", status: str = "open") -> dict:
        return {
            "id": "ticket-uuid-close",
            "ticketNumber": 7,
            "guildId": "123456789",
            "authorId": author_id,
            "channelId": "888888888",
            "categoryId": None,
            "status": status,
            "claimedBy": None,
            "transcriptUrl": None,
            "createdAt": "2026-01-15T10:00:00+00:00",
            "closedAt": None,
            "lastActivity": "2026-01-15T10:00:00+00:00",
        }

    @pytest.mark.asyncio
    async def test_close_button_sends_ephemeral_confirm_view(self) -> None:
        """Close button MUST send an ephemeral ConfirmCancelView (not close immediately)."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close()

        await view.close_button.callback(interaction)

        # MUST send an ephemeral message with a ConfirmCancelView.
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), ConfirmCancelView)

    @pytest.mark.asyncio
    async def test_close_button_does_not_close_immediately(self) -> None:
        """Close button MUST NOT call close_ticket_full — confirm callback does that."""
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close()
        interaction.client.ticket_service.close_ticket_full = AsyncMock()

        await view.close_button.callback(interaction)

        # close_ticket_full MUST NOT be called yet.
        interaction.client.ticket_service.close_ticket_full.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_confirm_calls_close_ticket_full(self) -> None:
        """Confirm callback MUST call close_ticket_full(manual=True)."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close()
        interaction.client.ticket_service.close_ticket_full = AsyncMock(return_value=None)

        await view.close_button.callback(interaction)

        # Extract the ConfirmCancelView that was sent.
        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        assert isinstance(sent_view, ConfirmCancelView)

        # Build a confirm interaction.
        confirm_interaction = MagicMock(spec=discord.Interaction)
        confirm_interaction.user = interaction.user
        confirm_interaction.response = MagicMock()
        confirm_interaction.response.edit_message = AsyncMock()
        confirm_interaction.response.send_message = AsyncMock()
        confirm_interaction.followup = MagicMock()
        confirm_interaction.followup.send = AsyncMock()
        confirm_interaction.channel = interaction.channel
        confirm_interaction.guild = interaction.guild
        confirm_interaction.guild_id = interaction.guild_id
        confirm_interaction.client = interaction.client

        await sent_view._on_confirm(confirm_interaction)

        interaction.client.ticket_service.close_ticket_full.assert_awaited_once()
        call_args = interaction.client.ticket_service.close_ticket_full.call_args
        assert call_args.kwargs.get("manual") is True

    @pytest.mark.asyncio
    async def test_close_cancel_shows_ephemeral_cancelled(self) -> None:
        """Cancel callback MUST edit the ephemeral message with a cancelled embed."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close()

        await view.close_button.callback(interaction)

        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        assert isinstance(sent_view, ConfirmCancelView)

        # Simulate cancel.
        cancel_interaction = MagicMock(spec=discord.Interaction)
        cancel_interaction.user = interaction.user
        cancel_interaction.response = MagicMock()
        cancel_interaction.response.edit_message = AsyncMock()
        cancel_interaction.response.send_message = AsyncMock()

        await sent_view.cancel_button.callback(cancel_interaction)

        # MUST edit the ephemeral message.
        cancel_interaction.response.edit_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_other_user_confirm_rejected(self) -> None:
        """Confirm from a different user MUST be rejected (not close the ticket)."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction(user_id=111111111)
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close()
        interaction.client.ticket_service.close_ticket_full = AsyncMock()

        await view.close_button.callback(interaction)

        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        assert isinstance(sent_view, ConfirmCancelView)

        # A different user tries to confirm.
        other_interaction = MagicMock(spec=discord.Interaction)
        other_user = MagicMock(spec=discord.Member)
        other_user.id = 999999999  # different from closer
        other_interaction.user = other_user
        other_interaction.response = MagicMock()
        other_interaction.response.send_message = AsyncMock()
        other_interaction.response.edit_message = AsyncMock()

        await sent_view.confirm_button.callback(other_interaction)

        # MUST send rejection, NOT close the ticket.
        other_interaction.response.send_message.assert_awaited_once()
        interaction.client.ticket_service.close_ticket_full.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_non_author_non_mod_rejected(self) -> None:
        """Non-author non-mod clicking close MUST be rejected (existing guard preserved)."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_close_interaction(user_id=999999999)
        # Ticket authored by someone else.
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close(author_id="111111111")

        # Patch is_mod_check to return False.
        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=False):
            await view.close_button.callback(interaction)

        # MUST send rejection embed (ephemeral), not a confirm view.
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        # The embed should be an error (not a ConfirmCancelView).
        assert "view" not in call_kwargs or not isinstance(call_kwargs.get("view"), ConfirmCancelView)

    @pytest.mark.asyncio
    async def test_close_non_author_mod_gets_confirm_view(self) -> None:
        """A non-author moderator clicking close MUST see the confirmation dialog, not rejection."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        # User is NOT the author (author is 111111111, closer is 999999999).
        interaction = self._make_close_interaction(user_id=999999999)
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row_for_close(author_id="111111111")

        # Patch is_mod_check to return True — this user IS a moderator.
        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await view.close_button.callback(interaction)

        # MUST send ephemeral ConfirmCancelView (not a rejection).
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), ConfirmCancelView)


# ===========================================================================
# PR3 — Claim-on-Claimed Transfer Confirm (task 3.5.1 RED)
# ===========================================================================


class TestClaimOnClaimedTransferConfirm:
    """Verify claim on already-claimed ticket shows transfer confirmation dialog."""

    @staticmethod
    def _make_claim_interaction(
        *,
        guild_id: int = 123456789,
        user_id: int = 222222222,
        channel_id: int = 888888888,
    ) -> MagicMock:
        """Return a mock Interaction wired for the claim button callback."""
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

        user = MagicMock(spec=discord.Member)
        user.id = user_id
        user.guild_permissions = MagicMock()
        user.guild_permissions.administrator = True
        user.roles = []
        interaction.user = user

        # message.edit must be an AsyncMock for the embed refresh after transfer.
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()

        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_by_channel = AsyncMock()
        bot._guild_mod_role_cache = {}
        bot.ticket_service = MagicMock()
        bot.ticket_service.claim_ticket = AsyncMock()
        bot.ticket_service.transfer_ticket = AsyncMock()
        bot.logging_service = MagicMock()
        interaction.client = bot

        return interaction

    @pytest.mark.asyncio
    async def test_claim_on_claimed_shows_transfer_confirm(self) -> None:
        """Claim on already-claimed ticket MUST send ephemeral ConfirmCancelView (not error embed)."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_claim_interaction()

        claimed_row = {
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
        interaction.client.db.get_ticket_by_channel.return_value = claimed_row

        await view.claim_button.callback(interaction)

        # MUST send ephemeral ConfirmCancelView (not a direct error embed).
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), ConfirmCancelView)

    @pytest.mark.asyncio
    async def test_transfer_confirm_calls_transfer_ticket(self) -> None:
        """Transfer confirm MUST call transfer_ticket with the new claimer."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_claim_interaction(user_id=222222222)

        claimed_row = {
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
        interaction.client.db.get_ticket_by_channel.return_value = claimed_row

        from bot.models.ticket import Ticket

        transferred = Ticket.from_db_row({**claimed_row, "claimedBy": "222222222"})
        interaction.client.ticket_service.transfer_ticket = AsyncMock(return_value=transferred)

        await view.claim_button.callback(interaction)

        # Extract the ConfirmCancelView.
        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        assert isinstance(sent_view, ConfirmCancelView)

        # Build a confirm interaction.
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

        # transfer_ticket MUST be called with the new claimer.
        interaction.client.ticket_service.transfer_ticket.assert_called_once()
        call_kwargs = interaction.client.ticket_service.transfer_ticket.call_args.kwargs
        assert call_kwargs["new_claimed_by"] == "222222222"

    @pytest.mark.asyncio
    async def test_transfer_cancel_dismisses(self) -> None:
        """Cancel on transfer confirm MUST edit the ephemeral message."""
        from bot.views.confirmation import ConfirmCancelView
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_claim_interaction()

        claimed_row = {
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
        interaction.client.db.get_ticket_by_channel.return_value = claimed_row

        await view.claim_button.callback(interaction)

        sent_view = interaction.response.send_message.call_args.kwargs["view"]
        assert isinstance(sent_view, ConfirmCancelView)

        # Simulate cancel.
        cancel_interaction = MagicMock(spec=discord.Interaction)
        cancel_interaction.user = interaction.user
        cancel_interaction.response = MagicMock()
        cancel_interaction.response.edit_message = AsyncMock()

        await sent_view.cancel_button.callback(cancel_interaction)

        cancel_interaction.response.edit_message.assert_awaited_once()


# ===========================================================================
# PR3 — Modal mod-role resolution characterization (task 3.2)
# ===========================================================================


class TestModalModRoleResolution:
    """Characterize _create_ticket_after_modal mod_role resolution paths.

    Currently: ``if config.mod_role_id: guild.get_role(int(config.mod_role_id))``
    wrapped in ``contextlib.suppress(ValueError, TypeError)``.

    After PR3 wiring: replaced by ``resolve_mod_role()`` helper.
    Behavior MUST remain identical.
    """

    @staticmethod
    def _make_modal_interaction(
        guild: MagicMock,
        bot: MagicMock,
    ) -> MagicMock:
        """Build a mock interaction wired for _create_ticket_after_modal."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.user.mention = "<@111111111>"
        interaction.client = bot
        interaction.guild_id = guild.id
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        return interaction

    @pytest.mark.asyncio
    async def test_valid_mod_role_passed_to_service(self) -> None:
        """config.mod_role_id set + guild.get_role returns Role → mod_role kwarg is the Role."""
        from bot.views.tickets import _create_ticket_after_modal

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        mod_role = MagicMock(spec=discord.Role)
        guild.get_role = MagicMock(return_value=mod_role)

        bot = MagicMock()
        bot.db = MagicMock()
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = "987654321"
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=config)
        bot.ticket_service = MagicMock()

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild.get_channel = MagicMock(return_value=category_channel)

        from bot.models.ticket import Ticket

        ticket = Ticket(
            id="t1", ticket_number=1, guild_id="123", author_id="456",
            channel_id="789", status="open", created_at="2026-01-01",
            last_activity="2026-01-01",
        )
        mock_channel = MagicMock()
        sent_message = AsyncMock()
        mock_channel.send = AsyncMock(return_value=sent_message)
        bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_channel, ticket))

        interaction = self._make_modal_interaction(guild, bot)

        with patch("bot.views.tickets.TicketActionsView"):
            await _create_ticket_after_modal(interaction, guild, "cat-uuid", "Support", "Help", "desc")

        bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["mod_role"] is mod_role

    @pytest.mark.asyncio
    async def test_none_mod_role_id_passes_none(self) -> None:
        """config.mod_role_id=None → mod_role=None passed to service."""
        from bot.views.tickets import _create_ticket_after_modal

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.get_role = MagicMock(return_value=None)

        bot = MagicMock()
        bot.db = MagicMock()
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = None
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=config)
        bot.ticket_service = MagicMock()

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild.get_channel = MagicMock(return_value=category_channel)

        from bot.models.ticket import Ticket

        ticket = Ticket(
            id="t1", ticket_number=1, guild_id="123", author_id="456",
            channel_id="789", status="open", created_at="2026-01-01",
            last_activity="2026-01-01",
        )
        mock_channel = MagicMock()
        sent_message = AsyncMock()
        mock_channel.send = AsyncMock(return_value=sent_message)
        bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_channel, ticket))

        interaction = self._make_modal_interaction(guild, bot)

        with patch("bot.views.tickets.TicketActionsView"):
            await _create_ticket_after_modal(interaction, guild, "cat-uuid", "Support", "Help", "desc")

        bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["mod_role"] is None

    @pytest.mark.asyncio
    async def test_invalid_mod_role_id_passes_none(self) -> None:
        """config.mod_role_id='not-a-number' → ValueError suppressed, mod_role=None."""
        from bot.views.tickets import _create_ticket_after_modal

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        guild.get_role = MagicMock(return_value=None)

        bot = MagicMock()
        bot.db = MagicMock()
        config = MagicMock()
        config.ticket_category_id = "100000000"
        config.mod_role_id = "not-a-number"
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=config)
        bot.ticket_service = MagicMock()

        category_channel = MagicMock(spec=discord.CategoryChannel)
        guild.get_channel = MagicMock(return_value=category_channel)

        from bot.models.ticket import Ticket

        ticket = Ticket(
            id="t1", ticket_number=1, guild_id="123", author_id="456",
            channel_id="789", status="open", created_at="2026-01-01",
            last_activity="2026-01-01",
        )
        mock_channel = MagicMock()
        sent_message = AsyncMock()
        mock_channel.send = AsyncMock(return_value=sent_message)
        bot.ticket_service.create_ticket_channel = AsyncMock(return_value=(mock_channel, ticket))

        interaction = self._make_modal_interaction(guild, bot)

        with patch("bot.views.tickets.TicketActionsView"):
            await _create_ticket_after_modal(interaction, guild, "cat-uuid", "Support", "Help", "desc")

        bot.ticket_service.create_ticket_channel.assert_awaited_once()
        call_kwargs = bot.ticket_service.create_ticket_channel.call_args.kwargs
        assert call_kwargs["mod_role"] is None


# ===========================================================================
# Phase 3 — Edit Category Button + Ephemeral Select (task 3.3 RED)
# ===========================================================================


class TestEditCategoryButton:
    """Verify Edit Category button on TicketActionsView: i18n, mod gate, select."""

    @staticmethod
    def _make_edit_interaction(
        *,
        guild_id: int = 123456789,
        user_id: int = 111111111,
        channel_id: int = 888888888,
    ) -> MagicMock:
        """Return a mock Interaction wired for the edit category button."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild_id = guild_id
        interaction.channel_id = channel_id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.response.is_done.return_value = False
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.original_response = AsyncMock()

        guild = MagicMock()
        guild.id = guild_id
        interaction.guild = guild

        user = MagicMock(spec=discord.Member)
        user.id = user_id
        interaction.user = user

        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_by_channel = AsyncMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        bot._guild_mod_role_cache = {}
        bot.ticket_service = MagicMock()
        interaction.client = bot

        return interaction

    @staticmethod
    def _ticket_row(*, status: str = "open", category_id: str | None = "cat-uuid") -> dict:
        return {
            "id": "ticket-uuid-edit",
            "ticketNumber": 5,
            "guildId": "123456789",
            "authorId": "111111111",
            "channelId": "888888888",
            "categoryId": category_id,
            "status": status,
            "claimedBy": None,
            "transcriptUrl": None,
            "createdAt": "2026-01-15T10:00:00+00:00",
            "closedAt": None,
            "lastActivity": "2026-01-15T10:00:00+00:00",
        }

    @staticmethod
    def _category_rows() -> list[dict]:
        return [
            {
                "id": "cat-uuid-1",
                "guildId": "123456789",
                "name": "Support",
                "emoji": None,
                "description": "General support",
                "position": 0,
                "active": True,
                "createdAt": "2026-01-01T00:00:00",
                "fieldDefinitions": [],
            },
            {
                "id": "cat-uuid-2",
                "guildId": "123456789",
                "name": "Billing",
                "emoji": None,
                "description": "Billing issues",
                "position": 1,
                "active": True,
                "createdAt": "2026-01-01T00:00:00",
                "fieldDefinitions": [],
            },
        ]

    def test_edit_category_button_exists_on_view(self) -> None:
        """TicketActionsView MUST have a button with custom_id='ticket:edit-category'."""
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        buttons = [
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:edit-category"
        ]
        assert len(buttons) == 1
        assert buttons[0].style == discord.ButtonStyle.secondary

    def test_edit_button_label_resolved_via_i18n(self) -> None:
        """Edit category button label MUST be resolved via t() at init time."""
        from bot.views.tickets import TicketActionsView

        with patch("bot.views.tickets.t", return_value="Editar Categoría") as mock_t:
            view = TicketActionsView(guild_id="123456789")

        mock_t.assert_any_call("123456789", "tickets.actions.edit_category_button")
        button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:edit-category"
        )
        assert button.label == "Editar Categoría"

    @pytest.mark.asyncio
    async def test_edit_button_non_mod_rejected(self) -> None:
        """Non-mod clicking Edit Category MUST receive ephemeral rejection."""
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_edit_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=False):
            await view.edit_category_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_edit_button_mod_shows_ephemeral_select(self) -> None:
        """Mod clicking Edit Category MUST see ephemeral _EditCategoryView with select."""
        from bot.views.tickets import TicketActionsView, _EditCategoryView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_edit_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        interaction.client.db.get_ticket_categories.return_value = self._category_rows()

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await view.edit_category_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert isinstance(call_kwargs.get("view"), _EditCategoryView)

    @pytest.mark.asyncio
    async def test_edit_button_no_categories_shows_message(self) -> None:
        """When no active categories exist, MUST show ephemeral no-categories message."""
        from bot.views.tickets import TicketActionsView

        view = TicketActionsView(guild_id="123456789")
        interaction = self._make_edit_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        interaction.client.db.get_ticket_categories.return_value = []

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await view.edit_category_button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        # Should NOT have a view (just a message embed).
        assert call_kwargs.get("view") is None


class TestEditCategorySelect:
    """Verify _EditCategorySelect callback: mod re-check, closed, limit, rename."""

    @staticmethod
    def _make_select_interaction(
        *,
        guild_id: int = 123456789,
        user_id: int = 111111111,
        channel_id: int = 888888888,
    ) -> MagicMock:
        """Return a mock Interaction wired for the edit category select callback."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild_id = guild_id
        interaction.channel_id = channel_id
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()
        interaction.response.is_done.return_value = False
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        guild = MagicMock()
        guild.id = guild_id
        interaction.guild = guild

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.guild = guild
        interaction.channel = channel

        user = MagicMock(spec=discord.Member)
        user.id = user_id
        interaction.user = user

        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.get_ticket_by_channel = AsyncMock()
        bot._guild_mod_role_cache = {}
        bot.ticket_service = MagicMock()
        interaction.client = bot

        return interaction

    @staticmethod
    def _ticket_row(*, status: str = "open") -> dict:
        return {
            "id": "ticket-uuid-select",
            "ticketNumber": 5,
            "guildId": "123456789",
            "authorId": "111111111",
            "channelId": "888888888",
            "categoryId": "cat-uuid-1",
            "status": status,
            "claimedBy": None,
            "transcriptUrl": None,
            "createdAt": "2026-01-15T10:00:00+00:00",
            "closedAt": None,
            "lastActivity": "2026-01-15T10:00:00+00:00",
        }

    @staticmethod
    def _make_select(
        guild: MagicMock,
        categories: list | None = None,
        ticket_row: dict | None = None,
    ) -> object:
        """Build an _EditCategorySelect with real category options."""
        from bot.models.ticket_category import TicketCategory
        from bot.views.tickets import _EditCategorySelect

        if categories is None:
            categories = [
                TicketCategory(
                    id="cat-uuid-2", guild_id="123456789", name="Billing",
                    description="Billing issues", position=1,
                ),
            ]
        if ticket_row is None:
            ticket_row = {
                "id": "ticket-uuid-select",
                "ticketNumber": 5,
                "guildId": "123456789",
                "authorId": "111111111",
                "channelId": "888888888",
                "categoryId": "cat-uuid-1",
                "status": "open",
                "claimedBy": None,
                "transcriptUrl": None,
                "createdAt": "2026-01-15T10:00:00+00:00",
                "closedAt": None,
                "lastActivity": "2026-01-15T10:00:00+00:00",
            }
        options = [
            discord.SelectOption(label=cat.name, value=cat.id, description=cat.description)
            for cat in categories
        ]
        return _EditCategorySelect(options, guild, categories, ticket_row)

    @pytest.mark.asyncio
    async def test_select_non_mod_rejected_on_submit(self) -> None:
        """Select callback MUST re-check is_mod_check and reject non-mods."""

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        # Simulate selecting "Billing".
        select._values = ["cat-uuid-2"]

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=False):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        interaction.client.ticket_service.edit_ticket_category.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_closed_ticket_rejected(self) -> None:
        """Select callback MUST reject closed tickets with ephemeral message."""

        guild = MagicMock()
        guild.id = 123456789
        closed_row = self._ticket_row(status="closed")
        select = self._make_select(guild, ticket_row=closed_row)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = closed_row
        select._values = ["cat-uuid-2"]

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        interaction.client.ticket_service.edit_ticket_category.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_calls_edit_ticket_category(self) -> None:
        """Valid selection MUST call edit_ticket_category on the service."""
        from bot.models.ticket import Ticket

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        updated_ticket = Ticket(
            id="ticket-uuid-select", ticket_number=5, guild_id="123456789",
            author_id="111111111", channel_id="888888888", status="open",
            created_at="2026-01-15T10:00:00+00:00",
            last_activity="2026-01-15T10:00:00+00:00", category_id="cat-uuid-2",
        )
        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            return_value=(updated_ticket, True),
        )

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await select.callback(interaction)

        interaction.client.ticket_service.edit_ticket_category.assert_awaited_once()
        call_kwargs = interaction.client.ticket_service.edit_ticket_category.call_args.kwargs
        assert call_kwargs["is_mod"] is True

    @pytest.mark.asyncio
    async def test_select_limit_violation_shows_specific_ux(self) -> None:
        """Limit ValueError from edit_ticket_category MUST show edit_category_limit_* UX."""

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        # Mirror the real invariant message from check_one_ticket_per_user_per_category.
        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            side_effect=ValueError(
                "User 111111111 already has an open ticket in category 'cat-uuid-2'"
            ),
        )

        # Patch t() to return the raw key so we can verify the right key is used.
        with (
            patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True),
            patch("bot.views.tickets.t", side_effect=lambda gid, key, **kw: key),
        ):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        # Verify the embed uses edit_category_limit_* keys, NOT the generic/unexpected key.
        embed = call_kwargs["embed"]
        assert embed.title == "tickets.actions.edit_category_limit_title"
        assert "tickets.actions.edit_category_limit_description" in embed.description

    @pytest.mark.asyncio
    async def test_select_closed_during_dropdown_window_is_rejected(self) -> None:
        """Stale ``self._ticket_row`` MUST NOT bypass the closed check.

        The select is built with an OPEN row (captured when the button was
        clicked) but the DB now reports the ticket as closed — the callback
        MUST re-fetch and reject with the closed UX.
        """

        guild = MagicMock()
        guild.id = 123456789
        # Select carries a stale OPEN row from button-open time.
        select = self._make_select(guild, ticket_row=self._ticket_row(status="open"))
        interaction = self._make_select_interaction()
        # DB now reports it CLOSED.
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row(
            status="closed",
        )
        select._values = ["cat-uuid-2"]

        with (
            patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True),
            patch("bot.views.tickets.t", side_effect=lambda gid, key, **kw: key),
        ):
            await select.callback(interaction)

        # Service MUST NOT run on a ticket the DB reports closed.
        interaction.client.ticket_service.edit_ticket_category.assert_not_called()
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs["embed"]
        assert embed.title == "tickets.actions.edit_category_closed_title"
        assert "tickets.actions.edit_category_closed_description" in embed.description

    @pytest.mark.asyncio
    async def test_select_service_closed_valueerror_shows_closed_ux(self) -> None:
        """Service closing the ticket under us MUST show closed keys, not limit.

        The DB row is still open (race) but the service re-fetches internally
        and raises a closed ValueError — the callback MUST map it to the
        closed UX, NOT the limit UX.
        """

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            side_effect=ValueError(
                "Cannot edit category of a closed ticket (status='closed')"
            ),
        )

        with (
            patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True),
            patch("bot.views.tickets.t", side_effect=lambda gid, key, **kw: key),
        ):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs["embed"]
        # MUST use the closed keys, NOT the limit keys.
        assert embed.title == "tickets.actions.edit_category_closed_title"
        assert "tickets.actions.edit_category_closed_description" in embed.description
        assert "edit_category_limit" not in embed.title
        assert "edit_category_limit" not in (embed.description or "")

    @pytest.mark.asyncio
    async def test_select_other_valueerror_does_not_show_limit_ux(self) -> None:
        """A non-closed, non-limit ValueError MUST NOT show limit keys.

        The generic fallback uses common.error.unexpected_title with str(exc)
        as the description — never the misleading edit_category_limit_* keys.
        """

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        bogus_message = "Ticket some-uuid not found"
        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            side_effect=ValueError(bogus_message),
        )

        with (
            patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True),
            patch("bot.views.tickets.t", side_effect=lambda gid, key, **kw: key),
        ):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        embed = call_kwargs["embed"]
        # MUST NOT map to the limit keys.
        assert "edit_category_limit" not in embed.title
        assert "edit_category_limit" not in (embed.description or "")
        # Generic fallback title is the unexpected error key, with str(exc) as body.
        assert embed.title == "common.error.unexpected_title"
        assert embed.description == bogus_message

    @pytest.mark.asyncio
    async def test_select_rename_failure_shows_warning(self) -> None:
        """When rename_succeeded=False, MUST show success with rename warning."""
        from bot.models.ticket import Ticket

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        updated_ticket = Ticket(
            id="ticket-uuid-select", ticket_number=5, guild_id="123456789",
            author_id="111111111", channel_id="888888888", status="open",
            created_at="2026-01-15T10:00:00+00:00",
            last_activity="2026-01-15T10:00:00+00:00", category_id="cat-uuid-2",
        )
        # rename_succeeded=False — the channel rename failed.
        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            return_value=(updated_ticket, False),
        )

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        # Embed description MUST contain the rename warning.
        embed = call_kwargs["embed"]
        assert embed.description is not None and len(embed.description) > 0

    @pytest.mark.asyncio
    async def test_select_success_shows_confirmation(self) -> None:
        """Successful edit MUST show ephemeral success embed."""
        from bot.models.ticket import Ticket

        guild = MagicMock()
        guild.id = 123456789
        select = self._make_select(guild)
        interaction = self._make_select_interaction()
        interaction.client.db.get_ticket_by_channel.return_value = self._ticket_row()
        select._values = ["cat-uuid-2"]

        updated_ticket = Ticket(
            id="ticket-uuid-select", ticket_number=5, guild_id="123456789",
            author_id="111111111", channel_id="888888888", status="open",
            created_at="2026-01-15T10:00:00+00:00",
            last_activity="2026-01-15T10:00:00+00:00", category_id="cat-uuid-2",
        )
        interaction.client.ticket_service.edit_ticket_category = AsyncMock(
            return_value=(updated_ticket, True),
        )

        with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
            await select.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True

    def test_select_view_timeout_300(self) -> None:
        """_EditCategoryView MUST have timeout=300."""
        from bot.models.ticket_category import TicketCategory
        from bot.views.tickets import _EditCategoryView

        guild = MagicMock()
        guild.id = 123456789
        categories = [
            TicketCategory(
                id="cat-uuid-2", guild_id="123456789", name="Billing",
                description="Billing", position=1,
            ),
        ]
        options = [discord.SelectOption(label="Billing", value="cat-uuid-2")]
        ticket_row = {
            "id": "ticket-uuid-select", "ticketNumber": 5, "guildId": "123456789",
            "authorId": "111111111", "channelId": "888888888", "categoryId": "cat-uuid-1",
            "status": "open", "claimedBy": None, "transcriptUrl": None,
            "createdAt": "2026-01-15T10:00:00+00:00", "closedAt": None,
            "lastActivity": "2026-01-15T10:00:00+00:00",
        }
        view = _EditCategoryView(options, guild, categories, ticket_row)
        assert view.timeout == 300
