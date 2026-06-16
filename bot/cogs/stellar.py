"""StellarCog — economy commands: daily, coins, leaderboard.

Provides hybrid commands for the guild economy system:
  - /daily — claim daily coins with streak tracking
  - /coins [member] — check coin balance (self or target)
  - /leaderboard <xp|coins> — top-10 leaderboard embed
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.embeds import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
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
            success, coins_awarded, streak = (
                await self.bot.economy_service.claim_daily(guild_id, user_id)
            )
        except Exception:
            logger.exception("Daily claim failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    "Daily Claim Failed",
                    "An unexpected error occurred. Please try again later.",
                ),
                ephemeral=True,
            )
            return

        if success:
            embed = success_embed(
                "Daily Reward Claimed! 🎁",
                f"You received **{coins_awarded} coins**!\n"
                f"Streak: **{streak} day{'s' if streak != 1 else ''}** 🔥",
            )
        else:
            embed = warning_embed(
                "Daily Cooldown ⏳",
                f"You already claimed your daily reward.\n"
                f"Current streak: **{streak}** — come back tomorrow!",
            )

        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /coins
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="coins", description="Check your coin balance or someone else's"
    )
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
            balance = await self.bot.economy_service.get_balance(guild_id, user_id)
        except Exception:
            logger.exception("Balance query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    "Balance Check Failed",
                    "Could not retrieve coin balance. Please try again.",
                ),
                ephemeral=True,
            )
            return

        if target == ctx.author:
            description = f"You have **{balance} coins** 💰"
        else:
            description = (
                f"**{target.display_name}** has **{balance} coins** 💰"
            )

        embed = info_embed("Coin Balance", description)
        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="leaderboard",
        description="View the server leaderboard by XP or coins",
    )
    @app_commands.describe(
        type="Leaderboard type: 'xp' or 'coins' (default: xp)"
    )
    async def leaderboard(
        self,
        ctx: commands.Context,
        type: str = "xp",
    ) -> None:
        """Display the top-10 leaderboard for XP or coins."""
        guild_id = str(ctx.guild.id) if ctx.guild else ""

        sort_by = type.lower()
        if sort_by not in ("xp", "coins"):
            sort_by = "xp"

        try:
            rows = await self.bot.economy_service.get_leaderboard(
                guild_id, sort_by=sort_by, limit=10, offset=0
            )
        except Exception:
            logger.exception("Leaderboard query failed for guild %s", guild_id)
            await ctx.send(
                embed=error_embed(
                    "Leaderboard Error",
                    "Could not load the leaderboard. Please try again later.",
                ),
                ephemeral=True,
            )
            return

        if not rows:
            embed = error_embed(
                "Leaderboard Empty",
                f"No members with {'XP' if sort_by == 'xp' else 'coins'} "
                f"in this server yet. Start chatting to earn!",
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

        title = f"{'XP' if sort_by == 'xp' else 'Coin'} Leaderboard"
        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=COLOR_INFO,
        )
        embed.set_footer(text=f"Top {len(rows)} members")

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: NebulosaBot) -> None:
    """Load the StellarCog into the bot."""
    await bot.add_cog(StellarCog(bot))
