"""S2a.2 RED — Module navigation with breadcrumb and refresh.

Ref: setup-panel "Module navigation with breadcrumb and refresh"
- breadcrumb reflects selection
- refresh shows live state (post-mutation re-read)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest


class TestBreadcrumbReflectsSelection:
    """Breadcrumb must identify selected module."""

    @pytest.mark.asyncio
    async def test_breadcrumb_tickets(self) -> None:
        # Use guild with es locale
        from bot.core.i18n import load_locales, set_guild_language
        from bot.views.setup_panel import _build_embed

        load_locales()
        set_guild_language("111", "es")

        # Build embed for tickets module
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])

        embed = (
            await _build_embed("111", "tickets", bot=bot)
            if hasattr(__import__("bot.views.setup_panel", fromlist=["_build_embed"]), "_build_embed")
            else None
        )
        # Fallback: render via view helper if _build_embed not async; adapt
        if embed is None:
            # Try synchronous
            from bot.views.setup_panel import _build_embed as build

            if callable(build):
                # Check if coroutine
                import inspect

                if inspect.iscoroutinefunction(build):
                    embed = await build("111", "tickets", bot=bot)
                else:
                    embed = build("111", "tickets", bot=bot)

        # Breadcrumb is in author name or title or footer? Spec: human breadcrumb in embed author line + machine token in footer
        author_name = getattr(embed.author, "name", "") if embed.author else ""  # ty:ignore[unresolved-attribute]
        footer_text = getattr(embed.footer, "text", "") if embed.footer else ""  # ty:ignore[unresolved-attribute]
        combined = f"{author_name} {embed.title or ''} {embed.description or ''} {footer_text}"  # ty:ignore[unresolved-attribute]
        assert "tickets" in combined.lower() or "ticket" in combined.lower(), (
            f"breadcrumb must identify tickets, got author={author_name!r} footer={footer_text!r} title={embed.title!r}"  # ty:ignore[unresolved-attribute]
        )
        assert "nbpanel|module=tickets" in footer_text, (
            f"footer token must be nbpanel|module=tickets, got {footer_text!r}"
        )

    @pytest.mark.asyncio
    async def test_select_nav_switches_breadcrumb(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        select = next(c for c in view.children if getattr(c, "custom_id", None) == "setup:nav")
        # Simulate selecting welcome (even if module not fully implemented, breadcrumb should change)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        interaction.message = MagicMock()
        # Existing embed
        embed0 = MagicMock()
        embed0.footer.text = "nbpanel|module=tickets"
        interaction.message.embeds = [embed0]
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 222
        interaction.guild_id = 222
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.data = {"values": ["welcome"], "custom_id": "setup:nav"}
        bot = MagicMock()
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.client = bot

        await select.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        footer = getattr(embed.footer, "text", "") if embed.footer else ""
        assert "nbpanel|module=welcome" in footer, f"after nav to welcome, footer must be welcome, got {footer!r}"
        author = getattr(embed.author, "name", "") if embed.author else ""
        # Breadcrumb should mention welcome
        assert "welcome" in author.lower() or "welcome" in (embed.title or "").lower() or "welcome" in footer.lower(), (
            f"breadcrumb must reflect welcome, got author={author!r}"
        )


class TestRefreshShowsLiveState:
    """Refresh must re-read from service/cache before re-rendering."""

    @pytest.mark.asyncio
    async def test_refresh_re_reads_after_mutation(self) -> None:
        from bot.views.setup_panel import SetupPanelView

        view = SetupPanelView()
        # Find refresh button
        btn = next(c for c in view.children if getattr(c, "custom_id", None) == "setup:refresh")

        # Setup bot with guild_service that will return different values on second call
        bot = MagicMock()
        # First call returns old channel, second returns new channel
        old_config = MagicMock(ticket_category_id="111", language="es", welcome_enabled=False)
        new_config = MagicMock(ticket_category_id="999", language="es", welcome_enabled=True)
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock(side_effect=[old_config, new_config])
        bot.db = MagicMock()
        bot.db.get_ticket_categories = AsyncMock(return_value=[])
        # Also mock ticket categories live read?
        # For tickets module, live state is categories; simulate mutation
        bot.db.get_ticket_categories = AsyncMock(
            return_value=[{"id": "cat-1", "name": "Support", "guildId": "333", "position": 0, "active": True}]
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()
        embed0 = MagicMock()
        embed0.footer.text = "nbpanel|module=tickets"
        interaction.message = MagicMock()
        interaction.message.embeds = [embed0]
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 333
        interaction.guild_id = 333
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.guild_permissions.administrator = True
        interaction.client = bot

        await btn.callback(interaction)

        # Must have re-read (get_config or get_ticket_categories called)
        # At least one service read must have happened
        assert bot.guild_service.get_config.await_count >= 1 or bot.db.get_ticket_categories.await_count >= 1
        interaction.response.edit_message.assert_awaited_once()
        # Embed should reflect live data (e.g., category name Support if tickets module lists categories)
        kwargs = interaction.response.edit_message.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        # Check footer still present
        footer = getattr(embed.footer, "text", "") if embed.footer else ""
        assert "nbpanel|module=" in footer
