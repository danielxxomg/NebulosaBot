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
from tests.conftest import make_interaction

# Ensure real locales are loaded.
load_locales()


def _make_pages(n: int = 3) -> list[discord.Embed]:
    """Return *n* distinct embed pages for testing."""
    return [discord.Embed(title=f"Page {i}") for i in range(n)]


def _make_interaction() -> MagicMock:
    """Shared interaction factory plus the async edit_message the buttons use."""
    interaction = make_interaction()
    interaction.response.edit_message = AsyncMock()
    return interaction


class TestEmbedPaginatorInit:
    """Tests for EmbedPaginator default construction."""

    def test_creates_three_buttons(self) -> None:
        """Paginator MUST have prev, next, and stop buttons."""
        view = EmbedPaginator(_make_pages())
        children = list(view.children)
        assert len(children) == 3

    @pytest.mark.parametrize(
        ("timeout", "expect_timeout"),
        [
            pytest.param(None, 120.0, id="default-timeout-is-120"),
            pytest.param(60, 60, id="custom-timeout"),
        ],
    )
    def test_timeout(self, timeout: float | None, expect_timeout: float) -> None:
        """Default timeout MUST be 120s; an explicit timeout is configurable."""
        view = EmbedPaginator(_make_pages()) if timeout is None else EmbedPaginator(_make_pages(), timeout=timeout)
        assert view.timeout == expect_timeout

    def test_starts_on_page_zero(self) -> None:
        """Initial current_page MUST be 0."""
        view = EmbedPaginator(_make_pages())
        assert view.current_page == 0

    def test_prev_disabled_at_start(self) -> None:
        """Previous button MUST be disabled on first page."""
        view = EmbedPaginator(_make_pages())
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[0].disabled is True

    def test_next_enabled_at_start(self) -> None:
        """Next button MUST be enabled when multiple pages exist."""
        view = EmbedPaginator(_make_pages())
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[1].disabled is False


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
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[1].disabled is True

    def test_prev_enabled_after_first_page(self) -> None:
        """Previous button MUST be enabled when not on first page."""
        view = EmbedPaginator(_make_pages(3))
        view.current_page = 1
        view.update_buttons()
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert buttons[0].disabled is False


class TestEmbedPaginatorStop:
    """Tests for the stop button (matrix: disable-all + edit)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("check_edit", [False, True], ids=["disables-all-buttons", "sends-edit"])
    async def test_stop_button(self, check_edit: bool) -> None:
        """Stop button MUST disable prev/next/itself; the edit row also
        asserts edit_message fired once (stop renders the disabled view)."""
        view = EmbedPaginator(_make_pages(3))
        interaction = _make_interaction()

        await view.stop_button.callback(interaction)

        if not check_edit:
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    assert child.disabled is True
        else:
            interaction.response.edit_message.assert_awaited_once()


class TestEmbedPaginatorTimeout:
    """Tests for on_timeout behavior."""

    async def test_timeout_disables_all_buttons(self) -> None:
        """on_timeout MUST disable all buttons."""
        view = EmbedPaginator(_make_pages(3))
        message = AsyncMock()
        view._message = message

        await view.on_timeout()

        for child in view.children:
            if isinstance(child, discord.ui.Button):
                assert child.disabled is True


class TestEmbedPaginatorPersistence:
    """Tests for persistent custom_id support."""

    def test_custom_id_prefix_preserved(self) -> None:
        """Custom custom_id_prefix MUST be reflected in button custom_ids."""
        view = EmbedPaginator(_make_pages(), custom_id_prefix="help:")
        ids = [child.custom_id for child in view.children if isinstance(child, discord.ui.Button)]
        assert "help:prev" in ids
        assert "help:next" in ids
        assert "help:stop" in ids

    def test_default_custom_id_prefix(self) -> None:
        """Default custom_id prefix MUST be 'paginator:'."""
        view = EmbedPaginator(_make_pages())
        ids = [child.custom_id for child in view.children if isinstance(child, discord.ui.Button)]
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

    @pytest.mark.parametrize(
        ("lang", "labels"),
        [
            pytest.param("es", ("◀ Anterior", "Siguiente ▶", "⏹ Detener"), id="spanish-guild-spanish-labels"),
            pytest.param("en", ("◀ Previous", "Next ▶", "⏹ Stop"), id="english-guild-english-labels"),
        ],
    )
    def test_guild_language_shows_localized_labels(self, lang: str, labels: tuple[str, str, str]) -> None:
        """The guild's language MUST drive all three button labels via t()."""
        set_guild_language("300" if lang == "es" else "400", lang)
        view = EmbedPaginator(_make_pages(), guild_id="300" if lang == "es" else "400")
        buttons = self._get_buttons(view)
        assert [b.label for b in buttons] == list(labels)

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
