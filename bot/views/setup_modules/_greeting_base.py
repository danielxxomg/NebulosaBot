"""Base class for greeting setup modules (welcome and goodbye).

Provides shared state management, channel selection, clearance, rendering,
and action routing for greeting-related setup panels.
"""

from __future__ import annotations

import inspect
import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, success_embed
from bot.views.setup_modules._template_picker import (
    build_template_select,
    handle_preview_flow,
    handle_template_select_flow,
)

logger = logging.getLogger(__name__)


class GreetingSetupModuleBase:
    """Base setup module for greeting features — gated by greeting.manage."""

    key: str
    permission_key: str = "greeting.manage"
    channel_field: str
    template_field: str
    enabled_field: str
    card_enabled_field: str
    editor_actions: tuple[str, ...]

    def __init__(self, bot: typing.Any | None = None) -> None:
        self._bot = bot

    def _resolve_bot(self, interaction: discord.Interaction | None = None) -> typing.Any | None:
        if self._bot is not None:
            return self._bot
        if interaction is not None:
            return getattr(interaction, "client", None)
        try:
            from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-break

            return _get_setup_bot()
        except Exception:  # noqa: BLE001
            return None

    def _require_greeting_service(self, bot: typing.Any | None = None) -> tuple[typing.Any, typing.Any]:
        b = bot or self._resolve_bot()
        if b is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-break

                b = _get_setup_bot()
            except Exception:  # noqa: BLE001
                b = None
        if b is None or getattr(b, "greeting_service", None) is None:
            msg = "GreetingService unavailable"
            raise RuntimeError(msg)
        return b, b.greeting_service

    def _t(self, guild_id: str | None, suffix: str, **kwargs: typing.Any) -> str:
        return t(guild_id, f"setup.module.{self.key}.{suffix}", **kwargs)

    async def _save_channel(self, guild_id: str, channel_id: str | None, bot: typing.Any) -> None:
        cfg = await bot.greeting_service.get_config(guild_id)
        setattr(cfg, self.channel_field, channel_id)
        await bot.greeting_service.save_config(cfg)

    async def _save_template_id(
        self,
        guild_id: str,
        template_id: str | None,
        bot: typing.Any | None = None,
    ) -> None:
        b, _ = self._require_greeting_service(bot)
        cfg = await b.greeting_service.get_config(guild_id)
        setattr(cfg, self.template_field, template_id)
        await b.greeting_service.save_config(cfg)

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:  # noqa: ARG002
        title = self._t(guild_id, "title")
        desc = self._t(guild_id, "description")
        return discord.Embed(title=title, description=desc, color=INFO)

    def _render_extra_status_lines(self, guild_id: str, cfg: typing.Any, not_cfg: str) -> list[str]:  # noqa: ARG002
        return []

    def _render_post_template_status_lines(self, guild_id: str, cfg: typing.Any, not_cfg: str) -> list[str]:  # noqa: ARG002
        return []

    def _render_status_lines(self, guild_id: str, cfg: typing.Any) -> list[str]:
        not_cfg = self._t(guild_id, "not_configured")
        channel_id = getattr(cfg, self.channel_field, None)
        channel_display = f"<#{channel_id}>" if channel_id else not_cfg
        enabled_display = "✅" if getattr(cfg, self.enabled_field, False) else "❌"
        card_display = "✅" if getattr(cfg, self.card_enabled_field, False) else "❌"
        resolved = getattr(cfg, self.template_field, None) or getattr(cfg, "theme_id", None) or "default"
        template_display = t(guild_id, f"templates.greeting.{resolved}.label")
        if template_display == f"templates.greeting.{resolved}.label":
            template_display = resolved

        lines = [
            f"**{self._t(guild_id, 'channel_label')}:** {channel_display}",
            f"**{self._t(guild_id, 'enabled_label')}:** {enabled_display}",
            f"**{self._t(guild_id, 'card_enabled_label')}:** {card_display}",
        ]
        lines.extend(self._render_extra_status_lines(guild_id, cfg, not_cfg))
        lines.append(f"**{self._t(guild_id, 'template_label')}:** {template_display}")
        lines.extend(self._render_post_template_status_lines(guild_id, cfg, not_cfg))
        return lines

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = self._t(guild_id, "title")
        desc = self._t(guild_id, "description")
        if b is not None and getattr(b, "greeting_service", None) is not None:
            try:
                cfg = await b.greeting_service.get_config(guild_id)
                lines = self._render_status_lines(guild_id, cfg)
                status_block = "\n".join(lines)
                desc = f"{desc}\n\n{status_block}"
            except Exception:  # noqa: BLE001
                logger.debug("%s render_async failed", self.key.capitalize(), exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        select = build_template_select(guild_id, self.key)  # type: ignore[arg-type]
        select.row = 2
        select.callback = self._on_template_select  # type: ignore[method-assign]
        return [
            select,
            discord.ui.ChannelSelect(
                custom_id=f"setup:{self.key}:select_channel",
                channel_types=[discord.ChannelType.text],
                placeholder=self._t(guild_id, "channel_select_placeholder"),
                min_values=1,
                max_values=1,
                row=3,
            ),
            discord.ui.Button(
                label=self._t(guild_id, "clear_button"),
                style=discord.ButtonStyle.danger,
                custom_id=f"setup:{self.key}:clear",
                emoji="🗑️",
                row=4,
            ),
            discord.ui.Button(
                label=self._t(guild_id, "test_button"),
                style=discord.ButtonStyle.secondary,
                custom_id=f"setup:{self.key}:test",
                emoji="🔔",
                row=4,
            ),
        ]

    async def _on_template_select(self, interaction: discord.Interaction) -> None:
        """Select callback — dispatches to the module handler (persistent reroute path)."""
        await self.handle(interaction, "select_template")

    async def _handle_template_select(self, interaction: discord.Interaction) -> None:
        """Persist the picked template (greeting.manage gated) and refresh the panel."""
        await handle_template_select_flow(
            self,
            interaction,
            self.key,  # type: ignore[arg-type]
            persist=self._save_template_id,
        )

    async def _handle_test(self, interaction: discord.Interaction) -> None:
        await handle_preview_flow(self, interaction, self.key)  # type: ignore[arg-type]

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
                    self._t(guild_id, "error_title"),
                    self._t(guild_id, "unknown_action", action=action),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        try:
            await self._save_channel(guild_id, channel_id, bot)
        except Exception:
            logger.exception("Failed to save %s channel for guild %s", self.key, guild_id)
            await interaction.response.send_message(
                embed=error_embed(
                    self._t(guild_id, "error_title"),
                    self._t(guild_id, "error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, self.key, bot=bot, mod=self)
        view = SetupPanelView(current_module=self.key, guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                self._t(guild_id, "channel_set_title"),
                self._t(guild_id, "channel_set_description", channel=f"<#{channel_id}>"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _handle_clear(self, interaction: discord.Interaction, guild_id: str, bot: typing.Any) -> None:
        try:
            await self._save_channel(guild_id, None, bot)
        except Exception:
            logger.exception("Failed to clear %s channel for guild %s", self.key, guild_id)
            await interaction.response.send_message(
                embed=error_embed(
                    self._t(guild_id, "error_title"),
                    self._t(guild_id, "error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, self.key, bot=bot, mod=self)
        view = SetupPanelView(current_module=self.key, guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                self._t(guild_id, "channel_cleared_title"),
                self._t(guild_id, "channel_cleared_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            embed = error_embed(
                self._t(None, "error_guild_only_title"),
                self._t(None, "error_guild_only_description"),
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
                self._t(guild_id, "error_title"),
                self._t(guild_id, "error_bot_unavailable"),
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

        if action in self.editor_actions:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=self._t(guild_id, "editor_title"),
                    description=self._t(guild_id, "editor_description"),
                    color=INFO,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=error_embed(
                self._t(guild_id, "error_title"),
                self._t(guild_id, "unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
