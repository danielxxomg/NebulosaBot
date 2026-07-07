"""UtilityCog — info commands (avatar, serverinfo, userinfo).

Provides hybrid commands for quick member and server information.
No service layer — embed construction only, no DB or cache I/O.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.embeds import COLOR_INFO, error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

# ======================================================================
# UtilityCog
# ======================================================================


class UtilityCog(commands.Cog, name="Utility"):
    """Read-only commands for member and server information."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # ==================================================================
    # Commands
    # ==================================================================

    @commands.hybrid_command(
        name="avatar",
        description="Show a member's avatar.",
    )
    @app_commands.describe(member="Whose avatar to show (default: you)")
    async def avatar(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Reply with an embed showing the targeted member's avatar."""
        target = member or ctx.author

        avatar_url = target.display_avatar.url if target.display_avatar.url else target.default_avatar.url

        embed = discord.Embed(
            title=f"{target.display_name}'s Avatar",
            color=target.color,
        )
        embed.set_thumbnail(url=avatar_url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="serverinfo",
        description="Show server information.",
    )
    async def serverinfo(self, ctx: commands.Context) -> None:
        """Reply with a guild summary embed or error if invoked in DMs."""
        if ctx.guild is None:
            await ctx.send(
                embed=error_embed(
                    "Server Only",
                    "This command only works inside a server.",
                )
            )
            return

        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=COLOR_INFO)

        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown")
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Channels", value=str(len(guild.channels)))
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count))
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(guild.created_at, "R"),
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="userinfo",
        description="Show user information.",
    )
    @app_commands.describe(member="Whose info to show (default: you)")
    async def userinfo(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Reply with a member summary embed."""
        target = member or ctx.author

        embed = discord.Embed(
            title=str(target),
            color=target.color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="ID", value=str(target.id), inline=True)

        # Build roles list — skip @everyone (first role)
        role_mentions = [r.mention for r in target.roles[1:]]
        if len(role_mentions) > 20:
            remaining = len(role_mentions) - 20
            role_mentions = role_mentions[:20]
            roles_text = ", ".join(role_mentions) + f" ... and {remaining} more"
        elif role_mentions:
            roles_text = ", ".join(role_mentions)
        else:
            roles_text = "None"

        embed.add_field(name="Roles", value=roles_text, inline=False)

        embed.add_field(
            name="Joined",
            value=discord.utils.format_dt(target.joined_at, "R"),
            inline=True,
        )
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(target.created_at, "R"),
            inline=True,
        )

        if target.bot:
            embed.add_field(name="Bot", value="Yes", inline=True)

        await ctx.send(embed=embed)


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register UtilityCog with the bot (v2.x pattern)."""
    await bot.add_cog(UtilityCog(bot))
