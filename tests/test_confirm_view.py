"""Unit tests for bot.views.confirmation.ConfirmCancelView.

Covers:
    - Confirm executes the on_confirm callback
    - Cancel sends ephemeral cancellation message
    - Timeout disables both buttons and sends ephemeral timeout message
    - Non-owner interaction is rejected with ephemeral message

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.i18n import load_locales, set_guild_language
from bot.views.confirmation import ConfirmCancelView

# Ensure real locales are loaded.
load_locales()
set_guild_language("123456789", "en")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_interaction(user_id: int = 111111111, guild_id: int = 123456789) -> MagicMock:
    """Return a mock discord.Interaction for a specific user and guild."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild_id = guild_id
    interaction.response = MagicMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.send_message = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# Confirm action
# ---------------------------------------------------------------------------


class TestConfirmAction:
    """Tests for the Confirm button callback."""

    @pytest.mark.asyncio
    async def test_confirm_executes_callback(self) -> None:
        """Clicking Confirm should execute the on_confirm callback."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        interaction = _make_interaction(user_id=111111111)

        # Find the confirm button.
        confirm_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:confirm"
        )
        await confirm_button.callback(interaction)

        on_confirm.assert_awaited_once_with(interaction)

    @pytest.mark.asyncio
    async def test_confirm_disables_buttons_after_click(self) -> None:
        """After Confirm, both buttons should be disabled."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        interaction = _make_interaction(user_id=111111111)

        confirm_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:confirm"
        )
        await confirm_button.callback(interaction)

        # Both buttons should be disabled.
        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True


# ---------------------------------------------------------------------------
# Cancel action
# ---------------------------------------------------------------------------


class TestCancelAction:
    """Tests for the Cancel button callback."""

    @pytest.mark.asyncio
    async def test_cancel_sends_ephemeral_message(self) -> None:
        """Clicking Cancel should send an ephemeral cancellation message."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        interaction = _make_interaction(user_id=111111111)

        cancel_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:cancel"
        )
        await cancel_button.callback(interaction)

        on_confirm.assert_not_awaited()
        interaction.response.edit_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_disables_buttons(self) -> None:
        """After Cancel, both buttons should be disabled."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        interaction = _make_interaction(user_id=111111111)

        cancel_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:cancel"
        )
        await cancel_button.callback(interaction)

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    """Tests for view timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_disables_buttons(self) -> None:
        """On timeout, both buttons should be disabled."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
            timeout=30,
        )
        # Attach a mock message so on_timeout can edit it.
        view._message = AsyncMock()

        # Simulate timeout by calling on_timeout directly.
        await view.on_timeout()

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True

    @pytest.mark.asyncio
    async def test_timeout_sends_timeout_message(self) -> None:
        """On timeout, an ephemeral timeout message should be sent."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
            timeout=30,
        )
        # Attach a mock message so on_timeout can edit it.
        mock_message = AsyncMock()
        view._message = mock_message

        await view.on_timeout()

        mock_message.edit.assert_awaited_once()
        call_kwargs = mock_message.edit.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
        assert embed is not None
        assert embed.title == "Timed Out"
        assert "timed out" in embed.description.lower()

    @pytest.mark.asyncio
    async def test_timeout_with_public_message_attribute(self) -> None:
        """on_timeout edits the message set via public view.message attribute.

        This mirrors the production wiring pattern: ctx.send() returns a
        Message, the command sets view.message = msg, and on_timeout edits it.
        No private attribute injection.
        """
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
            timeout=30,
        )
        # Production pattern: ctx.send() returns a message, assign to view.
        mock_message = AsyncMock()
        view.message = mock_message

        await view.on_timeout()

        mock_message.edit.assert_awaited_once()
        call_kwargs = mock_message.edit.call_args
        embed = call_kwargs.kwargs.get("embed") or call_kwargs[1].get("embed")
        assert embed is not None
        assert embed.title == "Timed Out"

    @pytest.mark.asyncio
    async def test_timeout_no_message_does_not_raise(self) -> None:
        """on_timeout should not raise if no message was set."""
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=AsyncMock(),
            timeout=30,
        )
        # No message set — should not raise.
        await view.on_timeout()

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True


# ---------------------------------------------------------------------------
# Owner-only guard
# ---------------------------------------------------------------------------


class TestOwnerOnlyGuard:
    """Tests that only the invoker can interact with the buttons."""

    @pytest.mark.asyncio
    async def test_non_owner_confirm_rejected(self) -> None:
        """A different user clicking Confirm should be rejected."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        # Different user.
        interaction = _make_interaction(user_id=999999999)

        confirm_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:confirm"
        )
        await confirm_button.callback(interaction)

        on_confirm.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_non_owner_cancel_rejected(self) -> None:
        """A different user clicking Cancel should be rejected."""
        on_confirm = AsyncMock()
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=on_confirm,
        )
        interaction = _make_interaction(user_id=999999999)

        cancel_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "confirm:cancel"
        )
        await cancel_button.callback(interaction)

        on_confirm.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args
        assert call_kwargs.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Tests for ConfirmCancelView constructor."""

    def test_default_timeout_is_30(self) -> None:
        """Default timeout should be 30 seconds."""
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        assert view.timeout == 30

    def test_custom_timeout(self) -> None:
        """Custom timeout should be accepted."""
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=AsyncMock(),
            timeout=60,
        )
        assert view.timeout == 60

    def test_has_two_buttons(self) -> None:
        """View should have exactly two buttons: Confirm and Cancel."""
        view = ConfirmCancelView(
            guild_id="123456789",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 2
        custom_ids = {b.custom_id for b in buttons}
        assert custom_ids == {"confirm:confirm", "confirm:cancel"}


# ---------------------------------------------------------------------------
# Localized button labels
# ---------------------------------------------------------------------------


class TestLocalizedButtonLabels:
    """Tests for localized Confirm/Cancel button labels via t()."""

    def _get_button(self, view: ConfirmCancelView, custom_id: str) -> discord.ui.Button:
        """Find a button by custom_id."""
        return next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == custom_id
        )

    def test_spanish_guild_shows_spanish_confirm_label(self) -> None:
        """Spanish guild MUST show Spanish Confirm button label."""
        set_guild_language("100", "es")
        view = ConfirmCancelView(
            guild_id="100",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        confirm_btn = self._get_button(view, "confirm:confirm")
        assert confirm_btn.label == "Confirmar"

    def test_spanish_guild_shows_spanish_cancel_label(self) -> None:
        """Spanish guild MUST show Spanish Cancel button label."""
        set_guild_language("100", "es")
        view = ConfirmCancelView(
            guild_id="100",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        cancel_btn = self._get_button(view, "confirm:cancel")
        assert cancel_btn.label == "Cancelar"

    def test_english_guild_shows_english_confirm_label(self) -> None:
        """English guild MUST show English Confirm button label."""
        set_guild_language("200", "en")
        view = ConfirmCancelView(
            guild_id="200",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        confirm_btn = self._get_button(view, "confirm:confirm")
        assert confirm_btn.label == "Confirm"

    def test_english_guild_shows_english_cancel_label(self) -> None:
        """English guild MUST show English Cancel button label."""
        set_guild_language("200", "en")
        view = ConfirmCancelView(
            guild_id="200",
            owner_id=111111111,
            on_confirm=AsyncMock(),
        )
        cancel_btn = self._get_button(view, "confirm:cancel")
        assert cancel_btn.label == "Cancel"


# ---------------------------------------------------------------------------
# Decorator defaults (Spanish-first for persistent views)
# ---------------------------------------------------------------------------


class TestDecoratorDefaults:
    """Decorator label defaults MUST be Spanish (matching locale key values).

    Persistent views show decorator defaults before __init__ runs.
    Since the bot defaults to Spanish, decorator labels must be Spanish.
    """

    def _get_button_by_id(self, view: discord.ui.View, custom_id: str) -> discord.ui.Button:
        """Find a button by custom_id."""
        return next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == custom_id
        )

    def test_confirm_decorator_default_is_spanish(self) -> None:
        """The @discord.ui.button default label for Confirm MUST be 'Confirmar'."""
        # Inspect the decorator callback registry on the class itself.
        # The decorator stores the default label on the class attribute.
        from bot.views.confirmation import ConfirmCancelView

        # Build view with empty guild_id to see raw decorator defaults.
        view = ConfirmCancelView(guild_id="", owner_id=1, on_confirm=AsyncMock())
        confirm_btn = self._get_button_by_id(view, "confirm:confirm")
        # After __init__ with guild_id="", t("", ...) falls back to Spanish default.
        assert confirm_btn.label == "Confirmar"

    def test_cancel_decorator_default_is_spanish(self) -> None:
        """The @discord.ui.button default label for Cancel MUST be 'Cancelar'."""
        from bot.views.confirmation import ConfirmCancelView

        view = ConfirmCancelView(guild_id="", owner_id=1, on_confirm=AsyncMock())
        cancel_btn = self._get_button_by_id(view, "confirm:cancel")
        assert cancel_btn.label == "Cancelar"
