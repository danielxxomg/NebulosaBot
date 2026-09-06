"""Goodbye setup module — parity with legacy /goodbye group + preview.

Kind-specific glue over the shared factory in
``bot.views.setup_modules._template_picker`` (jscpd budget extraction).
"""

from __future__ import annotations

import inspect
import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.checks import can_member  # noqa: F401  # re-export: test patch target
from bot.utils.embeds import error_embed, success_embed
from bot.views.setup_modules._template_picker import (  # noqa: PLC0415  # facade indirection
    build_template_select,
    handle_preview_flow,
    handle_template_select_flow,
)

_GOODBYE_SELECT_CUSTOM_ID = "setup:goodbye:select_template"

# Preview forwards the resolved per-kind template via the shared factory:
# greetings.card greeting_title/member_count_text are t()-sourced there.
_PREVIEW_CARD_KEYS = ("greetings.card.goodbye_title", "greetings.card.member_count")

logger = logging.getLogger(__name__)


class GoodbyeSetupModule:
    """Setup module for goodbye — gated by greeting.manage."""

    key = "goodbye"
    permission_key = "greeting.manage"

    def __init__(self, bot: typing.Any | None = None) -> None:
        self._bot = bot

    def _resolve_bot(self, interaction: discord.Interaction | None = None) -> typing.Any | None:
        if self._bot is not None:
            return self._bot
        if interaction is not None:
            return getattr(interaction, "client", None)
        try:
            from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

            return _get_setup_bot()
        except Exception:  # noqa: BLE001
            return None

    async def set_goodbye_channel(self, guild_id: str, channel_id: str) -> None:
        bot = self._resolve_bot()
        if bot is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

                bot = _get_setup_bot()
            except Exception:  # noqa: BLE001
                bot = None
        if bot is None or getattr(bot, "greeting_service", None) is None:
            msg = "GreetingService unavailable"
            raise RuntimeError(msg)
        cfg = await bot.greeting_service.get_config(guild_id)
        cfg.goodbye_channel_id = channel_id
        await bot.greeting_service.save_config(cfg)

    async def set_goodbye_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        """Persist the per-kind goodbye template id (migration 030 column).

        ``bot`` may be passed by callers that already resolved it from the
        interaction (panel-routed selects run on the MODULES singleton,
        which holds no bot reference).
        """
        bot = bot or self._resolve_bot()
        if bot is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

                bot = _get_setup_bot()
            except Exception:  # noqa: BLE001
                bot = None
        if bot is None or getattr(bot, "greeting_service", None) is None:
            msg = "GreetingService unavailable"
            raise RuntimeError(msg)
        cfg = await bot.greeting_service.get_config(guild_id)
        cfg.goodbye_template_id = template_id  # orphan: goodbyeTemplateId
        await bot.greeting_service.save_config(cfg)

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:  # noqa: ARG002
        title = t(guild_id, "setup.module.goodbye.title")
        desc = t(guild_id, "setup.module.goodbye.description")
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = t(guild_id, "setup.module.goodbye.title")
        desc = t(guild_id, "setup.module.goodbye.description")
        if b is not None and getattr(b, "greeting_service", None) is not None:
            try:
                cfg = await b.greeting_service.get_config(guild_id)
                not_cfg = t(guild_id, "setup.module.goodbye.not_configured")
                channel_display = f"<#{cfg.goodbye_channel_id}>" if cfg.goodbye_channel_id else not_cfg
                enabled_display = "✅" if cfg.goodbye_enabled else "❌"
                card_display = "✅" if getattr(cfg, "goodbye_card_enabled", False) else "❌"
                resolved = cfg.goodbye_template_id or cfg.theme_id or "default"
                template_display = t(guild_id, f"templates.greeting.{resolved}.label")
                if template_display == f"templates.greeting.{resolved}.label":
                    template_display = resolved
                desc = (
                    f"{desc}\n\n"
                    f"**{t(guild_id, 'setup.module.goodbye.channel_label')}:** {channel_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.enabled_label')}:** {enabled_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.card_enabled_label')}:** {card_display}\n"
                    f"**{t(guild_id, 'setup.module.goodbye.template_label')}:** {template_display}"
                )
            except Exception:  # noqa: BLE001
                logger.debug("Goodbye render_async failed", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        select = build_template_select(guild_id, "goodbye")
        select.row = 2
        select.callback = self._on_template_select  # type: ignore[method-assign]
        return [
            select,
            discord.ui.ChannelSelect(
                custom_id="setup:goodbye:select_channel",
                channel_types=[discord.ChannelType.text],
                placeholder=t(guild_id, "setup.module.goodbye.channel_select_placeholder"),
                min_values=1,
                max_values=1,
                row=3,
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.clear_button"),
                style=discord.ButtonStyle.danger,
                custom_id="setup:goodbye:clear",
                emoji="🗑️",
                row=4,
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.goodbye.test_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:goodbye:test",
                emoji="🔔",
                row=4,
            ),
        ]

    async def _handle_select_channel(
        self, interaction: discord.Interaction, guild_id: str, bot: typing.Any, action: str
    ) -> None:
        channel_id: str | None = None
        data = getattr(interaction, "data", None)
        if isinstance(data, dict):
            vals = data.get("values") or []
            if vals:
                v = vals[0]
                channel_id = str(getattr(v, "id", v))
        vals_attr = getattr(interaction, "values", None)
        if channel_id is None and vals_attr:
            v = vals_attr[0]
            channel_id = str(getattr(v, "id", v))

        if not channel_id:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.unknown_action", action=action),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        try:
            cfg = await bot.greeting_service.get_config(guild_id)
            cfg.goodbye_channel_id = channel_id
            await bot.greeting_service.save_config(cfg)
        except Exception:
            logger.exception("Failed to save goodbye channel for guild %s", guild_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, "goodbye", bot=bot, mod=self)
        view = SetupPanelView(current_module="goodbye", guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.goodbye.channel_set_title"),
                t(guild_id, "setup.module.goodbye.channel_set_description", channel=f"<#{channel_id}>"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _handle_clear(self, interaction: discord.Interaction, guild_id: str, bot: typing.Any) -> None:
        try:
            cfg = await bot.greeting_service.get_config(guild_id)
            cfg.goodbye_channel_id = None
            await bot.greeting_service.save_config(cfg)
        except Exception:
            logger.exception("Failed to clear goodbye channel for guild %s", guild_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.goodbye.error_title"),
                    t(guild_id, "setup.module.goodbye.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, "goodbye", bot=bot, mod=self)
        view = SetupPanelView(current_module="goodbye", guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.goodbye.channel_cleared_title"),
                t(guild_id, "setup.module.goodbye.channel_cleared_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            embed = error_embed(
                t(None, "setup.module.goodbye.error_guild_only_title"),
                t(None, "setup.module.goodbye.error_guild_only_description"),
            )
            send_fn = getattr(interaction.response, "send_message", None)
            if inspect.iscoroutinefunction(send_fn) or hasattr(send_fn, "assert_awaited"):
                await interaction.response.send_message(embed=embed, ephemeral=True)
            elif callable(send_fn):
                send_fn(embed=embed, ephemeral=True)
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "greeting_service", None) is None:
            embed = error_embed(
                t(guild_id, "setup.module.goodbye.error_title"),
                t(guild_id, "setup.module.goodbye.error_bot_unavailable"),
                guild_id=guild_id,
            )
            send_fn = getattr(interaction.response, "send_message", None)
            if inspect.iscoroutinefunction(send_fn) or hasattr(send_fn, "assert_awaited"):
                await interaction.response.send_message(embed=embed, ephemeral=True)
            elif callable(send_fn):
                send_fn(embed=embed, ephemeral=True)
            return

        if action == "test":
            await self._handle_test(interaction)
            return
        if action == "select_template":
            await self._handle_template_select(interaction)
            return
        if action == "select_channel":
            await self._handle_select_channel(interaction, guild_id, bot, action)
            return
        if action == "clear":
            await self._handle_clear(interaction, guild_id, bot)
            return

        if action in ("set_channel", "toggle", "set_message", "card_toggle"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.goodbye.editor_title"),
                    description=t(guild_id, "setup.module.goodbye.editor_description"),
                    color=INFO,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=error_embed(
                t(guild_id, "setup.module.goodbye.error_title"),
                t(guild_id, "setup.module.goodbye.unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _on_template_select(self, interaction: discord.Interaction) -> None:
        """Select callback — dispatches to the module handler (persistent reroute path)."""
        await self.handle(interaction, "select_template")

    async def _handle_template_select(self, interaction: discord.Interaction) -> None:
        """Persist the picked template (greeting.manage gated) and refresh the panel."""
        await handle_template_select_flow(
            self,
            interaction,
            "goodbye",
            persist=self.set_goodbye_template_id,
        )

    async def _handle_test(self, interaction: discord.Interaction) -> None:
        await handle_preview_flow(self, interaction, "goodbye")
