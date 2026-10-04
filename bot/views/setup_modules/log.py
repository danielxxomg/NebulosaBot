"""Log setup module."""

from __future__ import annotations

import contextlib
import inspect
import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, success_embed

logger = logging.getLogger(__name__)


class LogSetupModule:
    """Setup module for log channel — gated by ticket/operational perms.

    Uses existing guild config log_channel_id (no new permission key).
    For simplicity, reuse tickets.manage or allow greeting.manage fallback;
    permission_key kept as tickets.manage per spec contract (no new key).
    """

    key = "log"
    permission_key = "tickets.manage"

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

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:  # noqa: ARG002
        title = t(guild_id, "setup.module.log.title")
        desc = t(guild_id, "setup.module.log.description")
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = t(guild_id, "setup.module.log.title")
        desc = t(guild_id, "setup.module.log.description")
        if b is not None and getattr(b, "guild_service", None) is not None:
            try:
                cfg = await b.guild_service.get_config(guild_id)
                not_cfg = t(guild_id, "setup.module.log.not_configured")
                log_display = f"<#{cfg.log_channel_id}>" if cfg.log_channel_id else not_cfg
                desc = f"{desc}\n\n**{t(guild_id, 'setup.module.log.channel_label')}:** {log_display}"
            except Exception:  # noqa: BLE001
                logger.debug("Log render_async failed", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        return [
            discord.ui.ChannelSelect(
                custom_id="setup:log:select_channel",
                channel_types=[discord.ChannelType.text],
                placeholder=t(guild_id, "setup.module.log.channel_select_placeholder"),
                min_values=1,
                max_values=1,
                row=2,
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.log.clear_button"),
                style=discord.ButtonStyle.danger,
                custom_id="setup:log:clear",
                emoji="🗑️",
                row=3,
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.log.test_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:log:test",
                emoji="🔔",
                row=3,
            ),
        ]

    async def _handle_test(self, interaction: discord.Interaction, guild_id: str, bot: typing.Any) -> None:
        guild = interaction.guild
        with contextlib.suppress(Exception):  # noqa: BLE001
            await interaction.response.defer(ephemeral=True)
        try:
            cfg = await bot.guild_service.get_config(guild_id)
        except Exception:  # noqa: BLE001
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.log.preview_error_title"),
                    t(guild_id, "setup.module.log.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        if not cfg.log_channel_id:
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.log.preview_no_channel_title"),
                    t(guild_id, "setup.module.log.preview_no_channel_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        try:
            channel = guild.get_channel(int(cfg.log_channel_id)) if guild else None
        except Exception:  # noqa: BLE001
            channel = None
        if channel is None:
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.log.preview_no_channel_title"),
                    t(guild_id, "setup.module.log.preview_no_channel_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        try:
            embed = discord.Embed(
                title=t(guild_id, "setup.module.log.preview_embed_title"),
                description=t(guild_id, "setup.module.log.preview_embed_description"),
                color=INFO,
            )
            await channel.send(embed=embed)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            logger.exception("Log preview send failed")
            await interaction.followup.send(
                embed=error_embed(
                    t(guild_id, "setup.module.log.preview_error_title"),
                    t(guild_id, "setup.module.log.preview_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=discord.Embed(
                title=t(guild_id, "setup.module.log.preview_success_title"),
                description=t(
                    guild_id,
                    "setup.module.log.preview_success_description",
                    channel=f"<#{cfg.log_channel_id}>",
                ),
                color=INFO,
            ),
            ephemeral=True,
        )

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
                    t(guild_id, "setup.module.log.error_title"),
                    t(guild_id, "setup.module.log.unknown_action", action=action),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        is_done_fn = getattr(getattr(interaction, "response", None), "is_done", None)
        is_already_done = bool(is_done_fn() if callable(is_done_fn) else False)
        if not is_already_done:
            try:
                await interaction.response.defer()
            except Exception:
                logger.exception("Failed to acknowledge interaction in log select_channel (guild=%s)", guild_id)
                return

        try:
            cfg = await bot.guild_service.get_config(guild_id)
            cfg.log_channel_id = channel_id
            await bot.guild_service.save_config(cfg)
        except Exception:
            logger.exception("Failed to save log channel for guild %s", guild_id)
            err_embed = error_embed(
                t(guild_id, "setup.module.log.error_title"),
                t(guild_id, "setup.module.log.preview_error_description"),
                guild_id=guild_id,
            )
            followup = getattr(interaction, "followup", None)
            followup_send = getattr(followup, "send", None) if followup is not None else None
            if callable(followup_send) and (
                inspect.iscoroutinefunction(followup_send) or hasattr(followup_send, "assert_awaited")
            ):
                await interaction.followup.send(embed=err_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=err_embed, ephemeral=True)
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, "log", bot=bot, mod=self)
        view = SetupPanelView(current_module="log", guild_id=guild_id)
        edit_orig = getattr(interaction, "edit_original_response", None)
        if callable(edit_orig) and (inspect.iscoroutinefunction(edit_orig) or hasattr(edit_orig, "assert_awaited")):
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.log.channel_set_title"),
                t(guild_id, "setup.module.log.channel_set_description", channel=f"<#{channel_id}>"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def _handle_clear(self, interaction: discord.Interaction, guild_id: str, bot: typing.Any) -> None:
        is_done_fn = getattr(getattr(interaction, "response", None), "is_done", None)
        is_already_done = bool(is_done_fn() if callable(is_done_fn) else False)
        if not is_already_done:
            try:
                await interaction.response.defer()
            except Exception:
                logger.exception("Failed to acknowledge interaction in log clear (guild=%s)", guild_id)
                return

        try:
            cfg = await bot.guild_service.get_config(guild_id)
            cfg.log_channel_id = None
            await bot.guild_service.save_config(cfg)
        except Exception:
            logger.exception("Failed to clear log channel for guild %s", guild_id)
            err_embed = error_embed(
                t(guild_id, "setup.module.log.error_title"),
                t(guild_id, "setup.module.log.preview_error_description"),
                guild_id=guild_id,
            )
            followup = getattr(interaction, "followup", None)
            followup_send = getattr(followup, "send", None) if followup is not None else None
            if callable(followup_send) and (
                inspect.iscoroutinefunction(followup_send) or hasattr(followup_send, "assert_awaited")
            ):
                await interaction.followup.send(embed=err_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=err_embed, ephemeral=True)
            return

        from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break

        embed = await _build_embed(guild_id, "log", bot=bot, mod=self)
        view = SetupPanelView(current_module="log", guild_id=guild_id)
        edit_orig = getattr(interaction, "edit_original_response", None)
        if callable(edit_orig) and (inspect.iscoroutinefunction(edit_orig) or hasattr(edit_orig, "assert_awaited")):
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            embed=success_embed(
                t(guild_id, "setup.module.log.channel_cleared_title"),
                t(guild_id, "setup.module.log.channel_cleared_description"),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.module.log.error_guild_only_title"),
                    t(None, "setup.module.log.error_guild_only_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "guild_service", None) is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.log.error_title"),
                    t(guild_id, "setup.module.log.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        if action == "test":
            await self._handle_test(interaction, guild_id, bot)
            return
        if action == "select_channel":
            await self._handle_select_channel(interaction, guild_id, bot, action)
            return
        if action == "clear":
            await self._handle_clear(interaction, guild_id, bot)
            return

        if action == "set_channel":
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.log.editor_title"),
                    description=t(guild_id, "setup.module.log.editor_description"),
                    color=INFO,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=error_embed(
                t(guild_id, "setup.module.log.error_title"),
                t(guild_id, "setup.module.log.unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
