"""SetupCog — /setup persistent panel (pure app command, zero params).

Opens the non-ephemeral setup panel defined by setup-panel spec. All
configuration flows through guided panel editors; no Discord-object params.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class SetupCog(commands.Cog, name="Setup"):
    """Guild setup panel command."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    @app_commands.command(
        name="setup",
        description=app_commands.locale_str(
            "Configurar ajustes del servidor (panel persistente).",
            key="slash.descriptions.setup",
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction) -> None:
        """Open the persistent setup panel (one non-ephemeral message)."""
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.error_title"),
                    t(None, "setup.error_guild_only"),
                ),
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild.id)
        # Build panel embed (cache-first recompute) and persistent view
        try:
            from bot.views.setup_panel import SetupPanelView, _build_embed  # noqa: PLC0415 -- cycle-break
        except ImportError as exc:
            logger.exception("Setup panel view unavailable")
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.error_title"),
                    t(guild_id, "setup.error_config_load"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            msg = "SetupPanelView unavailable"
            raise RuntimeError(msg) from exc  # noqa: TRY003, EM101 -- msg assigned per rule

        embed = await _build_embed(guild_id, "tickets", bot=self.bot)
        view = SetupPanelView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

        logger.info("Guild %s opened /setup panel", guild_id)


async def setup(bot: NebulosaBot) -> None:
    """Register SetupCog with the bot."""
    await bot.add_cog(SetupCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove SetupCog from the bot."""
    await bot.remove_cog("Setup")
