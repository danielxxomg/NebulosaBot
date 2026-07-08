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
            success, coins_awarded, streak = await self.bot.economy_service.claim_daily(guild_id, user_id)
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
                f"You received **{coins_awarded} coins**!\nStreak: **{streak} day{'s' if streak != 1 else ''}** 🔥",
            )
        else:
            embed = warning_embed(
                "Daily Cooldown ⏳",
                f"You already claimed your daily reward.\nCurrent streak: **{streak}** — come back tomorrow!",
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
            description = f"**{target.display_name}** has **{balance} coins** 💰"

        embed = info_embed("Coin Balance", description)
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
            rows = await self.bot.economy_service.get_leaderboard(guild_id, sort_by=sort_by, limit=10, offset=0)
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
                f"No members with {'XP' if sort_by == 'xp' else 'coins'} in this server yet. Start chatting to earn!",
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
            rank_info = await self.bot.economy_service.get_rank_info(guild_id, user_id)
        except Exception:
            logger.exception("Rank info query failed for user %s", user_id)
            await ctx.send(
                embed=error_embed(
                    "Rank Card Error",
                    "Could not retrieve rank data. Please try again later.",
                ),
                ephemeral=True,
            )
            return

        if rank_info is None:
            await ctx.send(
                embed=error_embed(
                    "No Rank Data",
                    f"**{target.display_name}** has no stats yet.\nStart chatting to earn XP and level up!",
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
