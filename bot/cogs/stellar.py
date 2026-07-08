"""StellarCog — economy commands: daily, coins, leaderboard, rank.

Provides hybrid commands for the guild economy system:
  - /daily — claim daily coins with streak tracking
  - /coins [member] — check coin balance (self or target)
  - /leaderboard <xp|coins> — top-10 leaderboard embed
  - /rank [member] — generate and send a rank card image
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.embeds import (
    COLOR_INFO,
    error_embed,
    info_embed,
    success_embed,
    warning_embed,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class StellarCog(commands.Cog, name="Stellar"):
    """Economy and level system commands.

    All commands are hybrid (prefix + slash).  Business logic is delegated
    to :class:`~bot.services.economy_service.EconomyService`.
    """

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /daily
    # ------------------------------------------------------------------

    @commands.hybrid_command(name="daily", description="Claim your daily coin reward")
    async def daily(self, ctx: commands.Context) -> None:  # type: ignore[override]
        """Claim the daily coin reward with streak tracking."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        user_id = str(ctx.author.id)

        try:
            assert self.bot.economy_service is not None, "EconomyService initialised in setup_hook"
            success, coins_awarded, streak = await self.bot.economy_service.claim_daily(guild_id, user_id)
        except Exception:
            logger.exception("Daily claim failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.daily.failed_title"),
                    t(guild_id, "stellar.daily.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if success:
            plural = "s" if streak != 1 else ""
            embed = success_embed(
                t(guild_id, "stellar.daily.success_title"),
                t(guild_id, "stellar.daily.success_description", coins=coins_awarded, streak=streak, plural=plural),
            )
        else:
            embed = warning_embed(
                t(guild_id, "stellar.daily.cooldown_title"),
                t(guild_id, "stellar.daily.cooldown_description", streak=streak),
            )

        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /coins
    # ------------------------------------------------------------------

    @commands.hybrid_command(name="coins", description="Check your coin balance or someone else's")
    @app_commands.describe(member="The member to check (defaults to yourself)")
    async def coins(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Show the coin balance for yourself or a target member."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        target = member or ctx.author
        user_id = str(target.id)

        try:
            assert self.bot.economy_service is not None, "EconomyService initialised in setup_hook"
            balance = await self.bot.economy_service.get_balance(guild_id, user_id)
        except Exception:
            logger.exception("Balance query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.coins.failed_title"),
                    t(guild_id, "stellar.coins.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if target == ctx.author:
            description = t(guild_id, "stellar.coins.self_description", balance=balance)
        else:
            description = t(guild_id, "stellar.coins.target_description", name=target.display_name, balance=balance)

        embed = info_embed(t(guild_id, "stellar.coins.balance_title"), description)
        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="leaderboard",
        description="View the server leaderboard by XP or coins",
    )
    @app_commands.describe(lb_type="Leaderboard type: 'xp' or 'coins' (default: xp)")
    async def leaderboard(
        self,
        ctx: commands.Context,
        lb_type: str = "xp",
    ) -> None:
        """Display the top-10 leaderboard for XP or coins."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""

        sort_by = lb_type.lower()
        if sort_by not in ("xp", "coins"):
            sort_by = "xp"

        try:
            assert self.bot.economy_service is not None, "EconomyService initialised in setup_hook"
            rows = await self.bot.economy_service.get_leaderboard(guild_id, sort_by=sort_by, limit=10, offset=0)
        except Exception:
            logger.exception("Leaderboard query failed for guild %s", guild_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.leaderboard.error_title"),
                    t(guild_id, "stellar.leaderboard.error_description"),
                ),
                ephemeral=True,
            )
            return

        if not rows:
            type_label = "XP" if sort_by == "xp" else "coins"
            embed = error_embed(
                t(guild_id, "stellar.leaderboard.empty_title"),
                t(guild_id, "stellar.leaderboard.empty_description", type=type_label),
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Build description lines: "#1 <@id> — {value} XP/coins"
        lines: list[str] = []
        emoji_type = "✨" if sort_by == "xp" else "💰"
        for idx, row in enumerate(rows, start=1):
            user_id = row.get("userId", "unknown")
            value = row.get(sort_by, 0)
            trophy = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"
            lines.append(f"{trophy} <@{user_id}> — **{value:,}** {emoji_type}")

        title_key = "stellar.leaderboard.xp_title" if sort_by == "xp" else "stellar.leaderboard.coins_title"
        embed = discord.Embed(
            title=t(guild_id, title_key),
            description="\n".join(lines),
            color=COLOR_INFO,
        )
        embed.set_footer(text=t(guild_id, "stellar.leaderboard.footer", count=len(rows)))

        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /rank
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="rank",
        description="View your rank card or someone else's",
    )
    @app_commands.describe(member="The member to check (defaults to yourself)")
    async def rank(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Generate and send a rank card for yourself or a target member."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""
        target: discord.Member = member or ctx.author  # type: ignore[assignment]
        user_id = str(target.id)

        # Defer — image generation and avatar fetch are I/O-bound.
        await ctx.defer(ephemeral=True)

        try:
            assert self.bot.economy_service is not None, "EconomyService initialised in setup_hook"
            rank_info = await self.bot.economy_service.get_rank_info(guild_id, user_id)
        except Exception:
            logger.exception("Rank info query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.rank.failed_title"),
                    t(guild_id, "stellar.rank.failed_description"),
                ),
                ephemeral=True,
            )
            return

        if rank_info is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "stellar.rank.no_data_title"),
                    t(guild_id, "stellar.rank.no_data_description", name=target.display_name),
                ),
                ephemeral=True,
            )
            return

        # Fetch avatar URL for the rank card.
        # ImageService downloads the avatar itself in-thread, so we only
        # pass the URL — no need to read() bytes here.
        try:
            avatar_url: str | None = str(target.display_avatar.url)
        except Exception:
            avatar_url = None
            logger.debug(
                "Could not resolve avatar URL for user %s — using placeholder",
                user_id,
                exc_info=True,
            )

        # Generate the rank card in a thread to avoid blocking.
        assert self.bot.image_service is not None, "ImageService initialised in setup_hook"
        buffer = await asyncio.to_thread(
            self.bot.image_service.generate_rank_card,
            username=target.display_name,
            avatar_url=avatar_url,
            xp=rank_info["xp"],
            level=rank_info["level"],
            rank=rank_info["rank"],
            xp_for_current=rank_info["xp_current"],
            xp_for_next=rank_info["xp_needed"],
        )

        file = discord.File(buffer, filename="rank.png")
        await ctx.send(file=file, ephemeral=True)


async def setup(bot: NebulosaBot) -> None:
    """Load the StellarCog into the bot."""
    await bot.add_cog(StellarCog(bot))
