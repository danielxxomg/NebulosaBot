"""OcioCog — fun/leisure commands (dados, banana).

Provides hybrid commands for casual entertainment. No service layer —
pure random generation and static asset delivery.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.embeds import error_embed, info_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

_BANANA_IMAGE_PATH = Path("assets/images/banana.webp")

# ======================================================================
# OcioCog
# ======================================================================


class OcioCog(commands.Cog, name="Ocio"):
    """Fun commands for casual guild interaction."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # ==================================================================
    # Commands
    # ==================================================================

    @commands.hybrid_command(name="dados", description="Roll a dice.")  # type: ignore[arg-type]  # discord.py hybrid_command stub limitation
    @app_commands.describe(sides="Number of sides (2-100)")
    async def dados(
        self,
        ctx: commands.Context[Any],
        sides: app_commands.Range[int, 2, 100] = 6,
    ) -> None:
        """Roll a die with *sides* faces and reply with the result."""
        guild_id = ctx.guild.id if ctx.guild else None
        result = random.randint(1, sides)
        embed = info_embed(
            t(guild_id, "ocio.dados.title"),
            t(guild_id, "ocio.dados.description", result=result, sides=sides),
            guild_id=guild_id,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banana", description="Measure something in bananas.")  # type: ignore[arg-type]  # discord.py hybrid_command stub limitation
    async def banana(self, ctx: commands.Context[Any]) -> None:
        """Reply with a banana image and a random measurement (2-30 cm)."""
        guild_id = ctx.guild.id if ctx.guild else None

        if not _BANANA_IMAGE_PATH.exists():
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "ocio.banana.error_title"),
                    t(guild_id, "ocio.banana.error_description"),
                    guild_id=guild_id,
                )
            )
            return

        size = random.randint(2, 30)
        embed = info_embed(
            t(guild_id, "ocio.banana.title"),
            t(guild_id, "ocio.banana.description", size=size),
            guild_id=guild_id,
        )
        file = discord.File(str(_BANANA_IMAGE_PATH), filename="banana.webp")
        try:
            embed.set_image(url="attachment://banana.webp")
            await ctx.send(file=file, embed=embed)
        finally:
            file.close()


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register OcioCog with the bot (v2.x pattern)."""
    await bot.add_cog(OcioCog(bot))
