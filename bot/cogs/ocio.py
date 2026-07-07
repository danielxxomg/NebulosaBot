"""OcioCog — fun/leisure commands (dados, banana).

Provides hybrid commands for casual entertainment. No service layer —
pure random generation and static asset delivery.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

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

    @commands.hybrid_command(name="dados", description="Roll a dice.")
    @app_commands.describe(sides="Number of sides (2-100)")
    async def dados(
        self,
        ctx: commands.Context,
        sides: app_commands.Range[int, 2, 100] = 6,
    ) -> None:
        """Roll a die with *sides* faces and reply with the result."""
        result = random.randint(1, sides)
        embed = info_embed(
            "🎲 Dice Roll",
            f"You rolled a **{result}** (d{sides})",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banana", description="Measure something in bananas.")
    async def banana(self, ctx: commands.Context) -> None:
        """Reply with a banana image and a random measurement (2-30 cm)."""
        if not _BANANA_IMAGE_PATH.exists():
            await ctx.send(
                embed=error_embed(
                    "Image Missing",
                    "The banana image asset is not available. Please contact the bot owner.",
                )
            )
            return

        size = random.randint(2, 30)
        embed = info_embed(
            "🍌 Banana",
            f"This banana is **{size} cm**",
        )
        file = discord.File(str(_BANANA_IMAGE_PATH), filename="banana.webp")
        embed.set_image(url="attachment://banana.webp")
        await ctx.send(file=file, embed=embed)


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register OcioCog with the bot (v2.x pattern)."""
    await bot.add_cog(OcioCog(bot))
