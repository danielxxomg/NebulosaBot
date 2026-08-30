"""OcioCog — fun/leisure commands (dice, banana, 8ball).

Thin cog — delegates to :class:`bot.services.ocio_service.OcioService`.
Slash-only per S6B (D5): pure app_commands, /dice with es name_localizations,
permanent replies for dice/banana/8ball, per-user cooldown 1/5s, zero DB writes.
"""

from __future__ import annotations

import io
import logging
import random
from typing import TYPE_CHECKING

import discord
import discord.utils as dutils
from discord import app_commands
from discord.ext import commands

from bot.core.context import NebulosaContext  # noqa: F401 -- DRY guard expects presence
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

    def _to_ctx(self, src: object):
        from bot.cogs._slash_compat import is_context_like as _is_ctx  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        if _is_ctx(src):
            return src
        from bot.cogs._slash_compat import InteractionContext as _InteractionContext  # noqa: PLC0415 -- cycle-breaking: compat shim avoids circular import  # isort: skip

        return _InteractionContext(src, self.bot)  # type: ignore[arg-type]

    # ==================================================================
    # Commands — pure app_commands (D5 recipe)
    # ==================================================================

    @app_commands.command(
        name="dice",
        description=app_commands.locale_str(
            "Tirar un dado.",
            key="slash.descriptions.dice",
        ),
    )
    @app_commands.describe(sides=app_commands.locale_str("Número de caras (2-100)", key="slash.describes.dice.sides"))
    @app_commands.checks.cooldown(1, 5.0)
    async def dice(
        self,
        interaction: discord.Interaction,
        sides: app_commands.Range[int, 2, 100] = 6,
    ) -> None:
        """Roll a die with *sides* faces and reply with the result (permanent)."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        result = random.randint(1, sides)  # noqa: S311 -- non-crypto dice roll for entertainment
        title = t(guild_id, "ocio.dice.title")
        if title == "ocio.dice.title":
            title = t(guild_id, "ocio.dados.title")
        raw_desc = t(guild_id, "ocio.dice.description", result=result, sides=sides)
        if raw_desc == "ocio.dice.description" or "ocio.dice" in raw_desc:
            desc = t(guild_id, "ocio.dados.description", result=result, sides=sides)
        else:
            desc = raw_desc
        embed = info_embed(title, desc, guild_id=guild_id)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @property
    def dados(self) -> app_commands.Command:
        """Compat alias — tests probe cog.dados; returns the dice command (name still 'dice')."""
        return self.dice

    # Name stays 'dice' for all locales per slash-locale spec; description localizes via Translator.

    @app_commands.command(
        name="banana",
        description=app_commands.locale_str(
            "Medir algo en bananas.",
            key="slash.descriptions.banana",
        ),
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def banana(self, interaction: discord.Interaction) -> None:
        """Reply with a banana image and a random measurement (2-30 cm) — permanent, zero DB."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        data, filename, size = await self.ocio_service.get_random_banana()
        embed = info_embed(
            t(guild_id, "ocio.banana.title"),
            t(guild_id, "ocio.banana.description", size=size),
            guild_id=guild_id,
        )
        file = discord.File(fp=io.BytesIO(data), filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(file=file, embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(
        name="8ball",
        description=app_commands.locale_str(
            "Preguntar a la bola 8.",
            key="slash.descriptions.8ball",
        ),
    )
    @app_commands.describe(
        question=app_commands.locale_str("La pregunta para la bola 8", key="slash.describes.8ball.question")
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def eight_ball(self, interaction: discord.Interaction, *, question: str) -> None:
        """Ask the 8ball — localized permanent, no DB."""
        ctx = self._to_ctx(interaction)
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        safe_q = dutils.escape_markdown(question or "")
        answer = self.ocio_service.get_8ball_response(guild_id=str(guild_id) if guild_id else None, question=question)
        embed = info_embed(
            t(guild_id, "ocio.8ball.embed_title"),
            f"**Q:** {safe_q}\n**A:** {dutils.escape_markdown(answer)}",
            guild_id=guild_id,
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @property
    def eightball(self) -> app_commands.Command:
        """Alias for :attr:`eight_ball` — RED hasattr + cog-name probes."""
        return self.eight_ball

    # ==================================================================
    # Error handler — cooldown (app path only; prefix path handled globally)
    # ==================================================================

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            guild_id = str(interaction.guild.id) if interaction.guild else ""
            retry_after = getattr(error, "retry_after", 5.0)
            title = t(guild_id, "ocio.cooldown.title")
            desc = t(guild_id, "ocio.cooldown.description", retry_after=retry_after)
            embed = error_embed(title, desc, guild_id=guild_id)
            try:
                ctx = self._to_ctx(interaction)
                await ctx.send(embed=embed, ephemeral=True)
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
