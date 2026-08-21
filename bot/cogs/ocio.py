"""OcioCog — fun/leisure commands (dados, banana, 8ball).

Thin cog — delegates to :class:`bot.services.ocio_service.OcioService`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.context import NebulosaContext
from bot.core.i18n import t
from bot.services.ocio_service import OcioService
from bot.utils.embeds import error_embed, info_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class OcioCog(commands.Cog, name="Ocio"):
    """Fun commands for casual guild interaction."""

    __slots__ = ("bot", "ocio_service")

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot
        self.ocio_service = OcioService()

    # ==================================================================
    # Commands
    # ==================================================================

    @commands.hybrid_command(
        name="dados",
        description=app_commands.locale_str(
            "Tirar un dado.",
            key="slash.descriptions.dados",
        ),
    )
    @app_commands.describe(sides=app_commands.locale_str("Número de caras (2-100)", key="slash.describes.dados.sides"))
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dados(
        self,
        ctx: NebulosaContext,
        sides: app_commands.Range[int, 2, 100] = 6,
    ) -> None:
        """Roll a die with *sides* faces and reply with the result."""
        import random

        guild_id = ctx.guild.id if ctx.guild else None
        result = random.randint(1, sides)  # noqa: S311 -- non-crypto dice roll for entertainment
        embed = info_embed(
            t(guild_id, "ocio.dados.title"),
            t(guild_id, "ocio.dados.description", result=result, sides=sides),
            guild_id=guild_id,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="banana",
        description=app_commands.locale_str(
            "Medir algo en bananas.",
            key="slash.descriptions.banana",
        ),
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def banana(self, ctx: NebulosaContext) -> None:
        """Reply with a banana image and a random measurement (2-30 cm)."""
        guild_id = ctx.guild.id if ctx.guild else None

        data, filename, size = await self.ocio_service.get_random_banana()

        embed = info_embed(
            t(guild_id, "ocio.banana.title"),
            t(guild_id, "ocio.banana.description", size=size),
            guild_id=guild_id,
        )
        # data is PNG bytes (placeholder) or WEBP bytes; send as file
        file = discord.File(
            fp=__import__("io").BytesIO(data),
            filename=filename,
        )
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(file=file, embed=embed)

    @commands.hybrid_command(
        name="8ball",
        description=app_commands.locale_str(
            "Preguntar a la bola 8.",
            key="slash.descriptions.8ball",
        ),
    )
    @app_commands.describe(
        question=app_commands.locale_str("La pregunta para la bola 8", key="slash.describes.8ball.question")
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def eight_ball(self, ctx: NebulosaContext, *, question: str) -> None:
        """Ask the 8ball — localized ephemeral, no DB."""
        import discord.utils as dutils

        guild_id = ctx.guild.id if ctx.guild else None
        # escape markdown on echoed question + suppress pings
        safe_q = dutils.escape_markdown(question or "")
        answer = self.ocio_service.get_8ball_response(guild_id=str(guild_id) if guild_id else None, question=question)
        embed = info_embed(
            t(guild_id, "ocio.8ball.embed_title")
            if not t(guild_id, "ocio.8ball.embed_title").startswith("ocio.8ball")
            else "🎱 8ball",
            f"**Q:** {safe_q}\n**A:** {dutils.escape_markdown(answer)}",
            guild_id=guild_id,
        )
        await ctx.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    # alias so RED's hasattr checks and cog_commands name all pass
    @property
    def eightball(self):
        return self.eight_ball

    # ==================================================================
    # Error handler — cooldown
    # ==================================================================

    @commands.Cog.listener()
    async def on_command_error(self, ctx: NebulosaContext, error: Exception) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            guild_id = ctx.guild.id if ctx.guild else None
            retry_after = getattr(error, "retry_after", 5.0)
            title = t(guild_id, "ocio.cooldown.title")
            desc = t(guild_id, "ocio.cooldown.description", retry_after=retry_after)
            await ctx.send(embed=error_embed(title, desc, guild_id=guild_id), ephemeral=True)
            return
        # not our error — let global handler deal (re-raise for next handler)
        # Cog listeners don't suppress; but for prefix hybrid cooldown we handled above.
        return

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            guild_id = interaction.guild.id if interaction.guild else None
            retry_after = getattr(error, "retry_after", 5.0)
            title = t(guild_id, "ocio.cooldown.title")
            desc = t(guild_id, "ocio.cooldown.description", retry_after=retry_after)
            embed = error_embed(title, desc, guild_id=guild_id)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception:
                logger.exception("Failed to send cooldown embed")
            return
        # let global handler


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register OcioCog with the bot (v2.x pattern)."""
    await bot.add_cog(OcioCog(bot))
