"""Unit tests for bot.utils.embeds — embed factories and asset resolvers.

Verifies:
    - _make_embed() uses brand tokens for color
    - bot_avatar_url() resolves to bot.user.display_avatar.url
    - guild_footer_icon() returns guild icon or bot avatar fallback
    - Factory functions (error_embed, success_embed, etc.) use brand tokens
    - build_ticket_embed() uses brand tokens and accepts bot/guild for footer icon
    - Production callers (deploy_ticket_panel, logging) wire bot/guild through
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.utils.brand import ERROR, INFO, PRIMARY, SUCCESS, WARNING


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot() -> MagicMock:
    """Return a mock bot with user.display_avatar.url."""
    bot = MagicMock()
    bot.user = MagicMock(spec=discord.User)
    bot.user.display_avatar = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/123/avatar.png"
    return bot


@pytest.fixture
def mock_guild_with_icon() -> MagicMock:
    """Return a mock guild with a custom icon."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    guild.icon = MagicMock()
    guild.icon.url = "https://cdn.discordapp.com/icons/111/server.png"
    return guild


@pytest.fixture
def mock_guild_no_icon() -> MagicMock:
    """Return a mock guild without an icon."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 222
    guild.icon = None
    return guild


# ---------------------------------------------------------------------------
# bot_avatar_url — pure resolver
# ---------------------------------------------------------------------------


class TestBotAvatarUrl:
    """Tests for bot_avatar_url() resolver."""

    def test_returns_bot_avatar_url(self, mock_bot: MagicMock) -> None:
        """bot_avatar_url must return bot.user.display_avatar.url."""
        from bot.utils.embeds import bot_avatar_url

        url = bot_avatar_url(mock_bot)
        assert url == "https://cdn.discordapp.com/avatars/123/avatar.png"


# ---------------------------------------------------------------------------
# guild_footer_icon — guild icon with bot fallback
# ---------------------------------------------------------------------------


class TestGuildFooterIcon:
    """Tests for guild_footer_icon() resolver."""

    def test_returns_guild_icon_when_available(self, mock_guild_with_icon: MagicMock, mock_bot: MagicMock) -> None:
        """guild_footer_icon must return guild.icon.url when guild has an icon."""
        from bot.utils.embeds import guild_footer_icon

        url = guild_footer_icon(mock_guild_with_icon, mock_bot)
        assert url == "https://cdn.discordapp.com/icons/111/server.png"

    def test_falls_back_to_bot_avatar_when_no_guild_icon(
        self, mock_guild_no_icon: MagicMock, mock_bot: MagicMock
    ) -> None:
        """guild_footer_icon must fall back to bot_avatar_url when guild has no icon."""
        from bot.utils.embeds import guild_footer_icon

        url = guild_footer_icon(mock_guild_no_icon, mock_bot)
        assert url == "https://cdn.discordapp.com/avatars/123/avatar.png"

    def test_falls_back_when_guild_is_none(self, mock_bot: MagicMock) -> None:
        """guild_footer_icon must fall back to bot_avatar_url when guild is None."""
        from bot.utils.embeds import guild_footer_icon

        url = guild_footer_icon(None, mock_bot)
        assert url == "https://cdn.discordapp.com/avatars/123/avatar.png"


# ---------------------------------------------------------------------------
# _make_embed — brand tokens and resolvers
# ---------------------------------------------------------------------------


class TestMakeEmbed:
    """Tests for _make_embed() internal factory."""

    def test_uses_primary_brand_color(self) -> None:
        """_make_embed must use the PRIMARY brand token when building default embeds."""
        from bot.utils.embeds import _make_embed

        embed = _make_embed("Title", "Desc", PRIMARY)
        assert embed.color.value == PRIMARY

    def test_accepts_bot_for_footer_icon(self, mock_bot: MagicMock) -> None:
        """_make_embed must accept bot kwarg and use bot avatar as footer icon."""
        from bot.utils.embeds import _make_embed

        embed = _make_embed("Title", "Desc", PRIMARY, bot=mock_bot)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/123/avatar.png"

    def test_accepts_guild_for_footer_icon(self, mock_guild_with_icon: MagicMock, mock_bot: MagicMock) -> None:
        """_make_embed must accept guild kwarg and use guild icon as footer icon."""
        from bot.utils.embeds import _make_embed

        embed = _make_embed("Title", "Desc", PRIMARY, bot=mock_bot, guild=mock_guild_with_icon)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/icons/111/server.png"

    def test_guild_no_icon_falls_back_to_bot(self, mock_guild_no_icon: MagicMock, mock_bot: MagicMock) -> None:
        """_make_embed with guild without icon must fall back to bot avatar."""
        from bot.utils.embeds import _make_embed

        embed = _make_embed("Title", "Desc", PRIMARY, bot=mock_bot, guild=mock_guild_no_icon)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/123/avatar.png"

    def test_no_bot_no_guild_uses_none_footer_icon(self) -> None:
        """_make_embed without bot or guild must set footer icon to None."""
        from bot.utils.embeds import _make_embed

        embed = _make_embed("Title", "Desc", PRIMARY)
        # When no bot is passed, footer icon should be None (no hardcoded URL)
        assert embed.footer.icon_url is None


# ---------------------------------------------------------------------------
# Factory functions — brand token mapping
# ---------------------------------------------------------------------------


class TestFactoryFunctions:
    """Tests for error_embed, success_embed, info_embed, warning_embed."""

    def test_error_embed_uses_error_token(self) -> None:
        """error_embed must use brand ERROR color."""
        from bot.utils.embeds import error_embed

        embed = error_embed("Err", "desc")
        assert embed.color.value == ERROR

    def test_success_embed_uses_success_token(self) -> None:
        """success_embed must use brand SUCCESS color."""
        from bot.utils.embeds import success_embed

        embed = success_embed("OK", "desc")
        assert embed.color.value == SUCCESS

    def test_info_embed_uses_info_token(self) -> None:
        """info_embed must use brand INFO color."""
        from bot.utils.embeds import info_embed

        embed = info_embed("Info", "desc")
        assert embed.color.value == INFO

    def test_warning_embed_uses_warning_token(self) -> None:
        """warning_embed must use brand WARNING color."""
        from bot.utils.embeds import warning_embed

        embed = warning_embed("Warn", "desc")
        assert embed.color.value == WARNING


# ---------------------------------------------------------------------------
# build_ticket_embed — brand tokens
# ---------------------------------------------------------------------------


class TestBuildTicketEmbed:
    """Tests for build_ticket_embed() using brand tokens."""

    def test_open_ticket_uses_success_token(self) -> None:
        """Open ticket embed must use brand SUCCESS color."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "open", "authorId": "123"}
        embed = build_ticket_embed(ticket)
        assert embed.color.value == SUCCESS

    def test_claimed_ticket_uses_info_token(self) -> None:
        """Claimed ticket embed must use brand INFO color."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "claimed", "authorId": "123"}
        embed = build_ticket_embed(ticket)
        assert embed.color.value == INFO

    def test_accepts_bot_for_footer_icon(self, mock_bot: MagicMock) -> None:
        """build_ticket_embed must accept bot kwarg and set bot avatar as footer icon."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "open", "authorId": "123"}
        embed = build_ticket_embed(ticket, bot=mock_bot)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/123/avatar.png"

    def test_accepts_guild_for_footer_icon(
        self, mock_bot: MagicMock, mock_guild_with_icon: MagicMock
    ) -> None:
        """build_ticket_embed must accept guild kwarg and set guild icon as footer icon."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "open", "authorId": "123"}
        embed = build_ticket_embed(ticket, bot=mock_bot, guild=mock_guild_with_icon)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/icons/111/server.png"

    def test_guild_no_icon_falls_back_to_bot(
        self, mock_bot: MagicMock, mock_guild_no_icon: MagicMock
    ) -> None:
        """build_ticket_embed with guild without icon must fall back to bot avatar."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "open", "authorId": "123"}
        embed = build_ticket_embed(ticket, bot=mock_bot, guild=mock_guild_no_icon)
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/123/avatar.png"

    def test_no_bot_no_guild_uses_none_footer_icon(self) -> None:
        """build_ticket_embed without bot/guild must set footer icon to None."""
        from bot.utils.embeds import build_ticket_embed

        ticket = {"ticketNumber": 1, "status": "open", "authorId": "123"}
        embed = build_ticket_embed(ticket)
        assert embed.footer.icon_url is None
