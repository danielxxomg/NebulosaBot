"""Unit tests for bot.utils.paginator — EmbedPaginator.

Covers:
    - Default init (buttons created, timeout=120)
    - Pagination prev/next navigation
    - Stop button disables all buttons
    - Timeout disables all buttons
    - Persistent custom_id preserved
    - Localized button labels via guild_id + t()
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.i18n import load_locales, set_guild_language
from bot.utils.paginator import EmbedPaginator

# Ensure real locales are loaded.
load_locales()


def _make_pages(n: int = 3) -> list[discord.Embed]:
    """Return *n* distinct embed pages for testing."""
    return [discord.Embed(title=f"Page {i}") for i in range(n)]


def _make_interaction() -> MagicMock:
    """Return a mock interaction with an async edit_message."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.edit_message = AsyncMock()
    return interaction


class TestEmbedPaginatorInit:
    """Tests for EmbedPaginator default construction."""

    def test_creates_three_buttons(self) -> None:
        """Paginator MUST have prev, next, and stop buttons."""
        view = EmbedPaginator(_make_pages())
        children = list(view.children)
        assert len(children) == 3

    def test_default_timeout_is_120(self) -> None:
        """Default timeout MUST be 120 seconds."""
        view = EmbedPaginator(_make_pages())
        assert view.timeout == 120.0

    def test_custom_timeout(self) -> None:
        """Timeout MUST be configurable."""
        view = EmbedPaginator(_make_pages(), timeout=60)
        assert view.timeout == 60

    def test_starts_on_page_zero(self) -> None:
        """Initial current_page MUST be 0."""
        view = EmbedPaginator(_make_pages())
        assert view.current_page == 0

    def test_prev_disabled_at_start(self) -> None:
        """Previous button MUST be disabled on first page."""
        view = EmbedPaginator(_make_pages())
        children = list(view.children)
        assert children[0].disabled is True

    def test_next_enabled_at_start(self) -> None:
        """Next button MUST be enabled when multiple pages exist."""
        view = EmbedPaginator(_make_pages())
        children = list(view.children)
        assert children[1].disabled is False


class TestEmbedPaginatorNavigation:
    """Tests for prev/next page navigation."""

    async def test_next_advances_page(self) -> None:
        """Next button MUST advance current_page by 1."""
        view = EmbedPaginator(_make_pages(3))
        interaction = _make_interaction()

        await view.next_button.callback(interaction)

        assert view.current_page == 1
        interaction.response.edit_message.assert_awaited_once()

    async def test_prev_returns_to_previous(self) -> None:
        """Previous button MUST decrement current_page."""
        view = EmbedPaginator(_make_pages(3))
        interaction = _make_interaction()

        view.current_page = 2
        view.update_buttons()
        await view.prev_button.callback(interaction)

        assert view.current_page == 1

    async def test_next_clamps_at_last_page(self) -> None:
        """Next button MUST NOT advance past the last page."""
        view = EmbedPaginator(_make_pages(2))

        view.current_page = 1
        view.update_buttons()
        interaction = _make_interaction()
        await view.next_button.callback(interaction)

        assert view.current_page == 1

    async def test_prev_clamps_at_zero(self) -> None:
        """Previous button MUST NOT go below page 0."""
        view = EmbedPaginator(_make_pages(2))
        interaction = _make_interaction()

        await view.prev_button.callback(interaction)

        assert view.current_page == 0

    def test_next_disabled_on_last_page(self) -> None:
        """Next button MUST be disabled when on the last page."""
        view = EmbedPaginator(_make_pages(2))
        view.current_page = 1
        view.update_buttons()
        children = list(view.children)
        assert children[1].disabled is True

    def test_prev_enabled_after_first_page(self) -> None:
        """Previous button MUST be enabled when not on first page."""
        view = EmbedPaginator(_make_pages(3))
        view.current_page = 1
        view.update_buttons()
        children = list(view.children)
        assert children[0].disabled is False


class TestEmbedPaginatorStop:
    """Tests for the stop button."""

    async def test_stop_disables_all_buttons(self) -> None:
        """Stop button MUST disable prev, next, and itself."""
        view = EmbedPaginator(_make_pages(3))
        interaction = _make_interaction()

        await view.stop_button.callback(interaction)

        children = list(view.children)
        for child in children:
            assert child.disabled is True

    async def test_stop_sends_edit(self) -> None:
        """Stop button MUST call edit_message to update the view."""
        view = EmbedPaginator(_make_pages(3))
        interaction = _make_interaction()

        await view.stop_button.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()


class TestEmbedPaginatorTimeout:
    """Tests for on_timeout behavior."""

    async def test_timeout_disables_all_buttons(self) -> None:
        """on_timeout MUST disable all buttons."""
        view = EmbedPaginator(_make_pages(3))
        message = AsyncMock()
        view._message = message

        await view.on_timeout()

        children = list(view.children)
        for child in children:
            assert child.disabled is True


class TestEmbedPaginatorPersistence:
    """Tests for persistent custom_id support."""

    def test_custom_id_prefix_preserved(self) -> None:
        """Custom custom_id_prefix MUST be reflected in button custom_ids."""
        view = EmbedPaginator(_make_pages(), custom_id_prefix="help:")
        children = list(view.children)
        ids = [child.custom_id for child in children]
        assert "help:prev" in ids
        assert "help:next" in ids
        assert "help:stop" in ids

    def test_default_custom_id_prefix(self) -> None:
        """Default custom_id prefix MUST be 'paginator:'."""
        view = EmbedPaginator(_make_pages())
        children = list(view.children)
        ids = [child.custom_id for child in children]
        assert "paginator:prev" in ids
        assert "paginator:next" in ids
        assert "paginator:stop" in ids


# ===========================================================================
# Localized button labels (task 2.3 RED)
# ===========================================================================


class TestEmbedPaginatorLocalizedLabels:
    """Tests for localized Previous/Next/Stop labels via guild_id + t()."""

    def _get_buttons(self, view: EmbedPaginator) -> list[discord.ui.Button]:
        """Return all button children in order."""
        return [c for c in view.children if isinstance(c, discord.ui.Button)]

    def test_spanish_guild_shows_spanish_previous(self) -> None:
        """Spanish guild MUST show Spanish Previous button label."""
        set_guild_language("300", "es")
        view = EmbedPaginator(_make_pages(), guild_id="300")
        buttons = self._get_buttons(view)
        assert buttons[0].label == "◀ Anterior"

    def test_spanish_guild_shows_spanish_next(self) -> None:
        """Spanish guild MUST show Spanish Next button label."""
        set_guild_language("300", "es")
        view = EmbedPaginator(_make_pages(), guild_id="300")
        buttons = self._get_buttons(view)
        assert buttons[1].label == "Siguiente ▶"

    def test_spanish_guild_shows_spanish_stop(self) -> None:
        """Spanish guild MUST show Spanish Stop button label."""
        set_guild_language("300", "es")
        view = EmbedPaginator(_make_pages(), guild_id="300")
        buttons = self._get_buttons(view)
        assert buttons[2].label == "⏹ Detener"

    def test_english_guild_shows_english_previous(self) -> None:
        """English guild MUST show English Previous button label."""
        set_guild_language("400", "en")
        view = EmbedPaginator(_make_pages(), guild_id="400")
        buttons = self._get_buttons(view)
        assert buttons[0].label == "◀ Previous"

    def test_english_guild_shows_english_next(self) -> None:
        """English guild MUST show English Next button label."""
        set_guild_language("400", "en")
        view = EmbedPaginator(_make_pages(), guild_id="400")
        buttons = self._get_buttons(view)
        assert buttons[1].label == "Next ▶"

    def test_english_guild_shows_english_stop(self) -> None:
        """English guild MUST show English Stop button label."""
        set_guild_language("400", "en")
        view = EmbedPaginator(_make_pages(), guild_id="400")
        buttons = self._get_buttons(view)
        assert buttons[2].label == "⏹ Stop"

    def test_no_guild_id_shows_default_labels(self) -> None:
        """Without guild_id, buttons MUST use default Spanish (es) labels."""
        view = EmbedPaginator(_make_pages())
        buttons = self._get_buttons(view)
        assert buttons[0].label == "◀ Anterior"
        assert buttons[1].label == "Siguiente ▶"
        assert buttons[2].label == "⏹ Detener"

    def test_guild_id_preserves_timeout(self) -> None:
        """Passing guild_id MUST preserve timeout behavior."""
        set_guild_language("300", "es")
        view = EmbedPaginator(_make_pages(), guild_id="300", timeout=60)
        assert view.timeout == 60
