"""Language setup module — gated by admin default (tickets.manage fallback, no new key)."""

from __future__ import annotations

import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, success_embed

logger = logging.getLogger(__name__)


class LanguageSetupModule:
    """Setup module for guild language."""

    key = "language"
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
        title = t(guild_id, "setup.module.language.title")
        desc = t(guild_id, "setup.module.language.description")
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        b = bot or self._resolve_bot()
        title = t(guild_id, "setup.module.language.title")
        desc = t(guild_id, "setup.module.language.description")
        if b is not None and getattr(b, "guild_service", None) is not None:
            try:
                cfg = await b.guild_service.get_config(guild_id)
                lang_display = cfg.language or "es"
                desc = f"{desc}\n\n**{t(guild_id, 'setup.module.language.current_label')}:** `{lang_display}`"
            except Exception:  # noqa: BLE001
                logger.debug("Language render_async failed", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        return [
            discord.ui.Button(
                label=t(guild_id, "setup.module.language.set_es_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:language:set_es",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.language.set_en_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:language:set_en",
            ),
        ]

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.module.language.error_guild_only_title"),
                    t(None, "setup.module.language.error_guild_only_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction)
        if bot is None or getattr(bot, "guild_service", None) is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.language.error_title"),
                    t(guild_id, "setup.module.language.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        if action in ("set_es", "set_en"):
            lang = "es" if action == "set_es" else "en"
            try:
                cfg = await bot.guild_service.get_config(guild_id)
                cfg.language = lang
                await bot.guild_service.save_config(cfg)
            except Exception:  # noqa: BLE001
                logger.exception("Language set failed")
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.module.language.error_title"),
                        t(guild_id, "setup.module.language.error_save"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                embed=success_embed(
                    t(guild_id, "setup.module.language.success_title"),
                    t(guild_id, "setup.module.language.success_description", language=lang),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=error_embed(
                t(guild_id, "setup.module.language.error_title"),
                t(guild_id, "setup.module.language.unknown_action", action=action),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )
