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

from bot.core.i18n import t
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
        guild_id = ctx.guild.id if ctx.guild else None
        target = member or ctx.author

        avatar_url = target.display_avatar.url if target.display_avatar.url else target.default_avatar.url

        embed = discord.Embed(
            title=t(guild_id, "utility.avatar.title", name=target.display_name),
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
        guild_id = ctx.guild.id if ctx.guild else None

        if ctx.guild is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "utility.serverinfo.error_title"),
                    t(guild_id, "utility.serverinfo.error_description"),
                    guild_id=guild_id,
                )
            )
            return

        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=COLOR_INFO)

        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name=t(guild_id, "utility.serverinfo.owner_field"),
            value=guild.owner.mention if guild.owner else "Unknown",
        )
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.members_field"),
            value=str(guild.member_count),
        )
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.channels_field"),
            value=str(len(guild.channels)),
        )
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.roles_field"),
            value=str(len(guild.roles)),
        )
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.boosts_field"),
            value=str(guild.premium_subscription_count),
        )
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.created_field"),
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
        guild_id = ctx.guild.id if ctx.guild else None
        target = member or ctx.author

        embed = discord.Embed(
            title=str(target),
            color=target.color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name=t(guild_id, "utility.userinfo.id_field"),
            value=str(target.id),
            inline=True,
        )

        # Build roles list — skip @everyone (first role)
        if not isinstance(target, discord.Member):
            return  # User objects don't have roles/joined_at.
        role_mentions = [r.mention for r in target.roles[1:]]
        if len(role_mentions) > 20:
            remaining = len(role_mentions) - 20
            role_mentions = role_mentions[:20]
            roles_text = (
                ", ".join(role_mentions) + " " + t(guild_id, "utility.userinfo.roles_overflow", count=remaining)
            )
        elif role_mentions:
            roles_text = ", ".join(role_mentions)
        else:
            roles_text = t(guild_id, "utility.userinfo.roles_none")

        embed.add_field(
            name=t(guild_id, "utility.userinfo.roles_field"),
            value=roles_text,
            inline=False,
        )

        embed.add_field(
            name=t(guild_id, "utility.userinfo.joined_field"),
            value=discord.utils.format_dt(target.joined_at, "R"),
            inline=True,
        )
        embed.add_field(
            name=t(guild_id, "utility.userinfo.created_field"),
            value=discord.utils.format_dt(target.created_at, "R"),
            inline=True,
        )

        if target.bot:
            embed.add_field(
                name=t(guild_id, "utility.userinfo.bot_field"),
                value=t(guild_id, "utility.userinfo.bot_yes"),
                inline=True,
            )

        await ctx.send(embed=embed)


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register UtilityCog with the bot (v2.x pattern)."""
    await bot.add_cog(UtilityCog(bot))
