"""Log setup module."""

from __future__ import annotations

import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed

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
            from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-breaking circular import

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
            discord.ui.Button(
                label=t(guild_id, "setup.module.log.set_channel_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:log:set_channel",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.log.clear_button"),
                style=discord.ButtonStyle.danger,
                custom_id="setup:log:clear",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.log.test_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:log:test",
            ),
        ]

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
            import contextlib

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
                channel = guild.get_channel(int(cfg.log_channel_id))
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
            return

        if action in ("set_channel", "clear"):
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
