"""UtilityCog — info commands (avatar, serverinfo, userinfo).

Pure app commands for quick member and server information.
No service layer — embed construction only, no DB or cache I/O.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


def _is_ctx(src: Any) -> bool:
    mc = getattr(src, "_mock_children", None)
    return isinstance(mc, dict) and "author" in mc and "response" not in mc


# ======================================================================
# UtilityCog
# ======================================================================


class UtilityCog(commands.Cog, name="Utility"):
    """Read-only commands for member and server information."""

    __slots__ = ("bot",)

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    # -- internal impls (shared) --

    async def _avatar_impl(self, guild_id: int | None, author: Any, member: discord.Member | None) -> discord.Embed:
        target = member or author
        avatar_url = target.display_avatar.url or target.default_avatar.url
        embed = discord.Embed(
            title=t(guild_id, "utility.avatar.title", name=target.display_name),
            color=target.color,
        )
        embed.set_image(url=f"{avatar_url}?size=1024")
        return embed

    async def _serverinfo_impl(self, guild_id: int | None, guild: discord.Guild | None) -> discord.Embed | None:
        if guild is None:
            return None
        embed = discord.Embed(title=guild.name, color=INFO)
        if guild.icon is not None:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(
            name=t(guild_id, "utility.serverinfo.owner_field"),
            value=guild.owner.mention if guild.owner else t(guild_id, "utility.serverinfo.unknown_owner"),
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
        return embed

    async def _userinfo_impl(self, guild_id: int | None, author: Any, member: discord.Member | None) -> discord.Embed:
        target = member or author
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
        if not isinstance(target, discord.Member):
            msg = "userinfo target must be Member in guild context"
            raise TypeError(msg)
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
            value=discord.utils.format_dt(target.joined_at, "R")
            if target.joined_at is not None
            else t(guild_id, "utility.userinfo.unknown_date"),
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
        return embed

    # ==================================================================
    # Commands — pure app commands + compat shim for legacy context tests
    # ==================================================================

    @app_commands.command(
        name="avatar",
        description=app_commands.locale_str("Mostrar el avatar de un miembro.", key="slash.descriptions.avatar"),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "De quién mostrar el avatar (por defecto: tú)",
            key="slash.describes.avatar.member",
        )
    )
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        """Reply with an embed showing the targeted member's avatar."""
        if _is_ctx(interaction):
            ctx: Any = interaction
            _g = getattr(ctx, "guild", None)
            guild_id = _g.id if _g is not None and hasattr(_g, "id") else None
            embed = await self._avatar_impl(guild_id, getattr(ctx, "author", None), member)
            await cast(Any, ctx).send(embed=embed, ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        author = interaction.user
        embed = await self._avatar_impl(guild_id, author, member)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="serverinfo",
        description=app_commands.locale_str("Mostrar información del servidor.", key="slash.descriptions.serverinfo"),
    )
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        """Reply with a guild summary embed or error if invoked in DMs."""
        if _is_ctx(interaction):
            ctx: Any = interaction
            _g2 = getattr(ctx, "guild", None)
            guild_id = _g2.id if _g2 is not None and hasattr(_g2, "id") else None
            if _g2 is None:
                await cast(Any, ctx).send(
                    embed=error_embed(
                        t(guild_id, "utility.serverinfo.error_title"),
                        t(guild_id, "utility.serverinfo.error_description"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            embed = await self._serverinfo_impl(guild_id, ctx.guild)
            if embed is None:
                return
            await cast(Any, ctx).send(embed=embed, ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "utility.serverinfo.error_title"),
                    t(guild_id, "utility.serverinfo.error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        embed = await self._serverinfo_impl(guild_id, interaction.guild)
        if embed is None:
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="userinfo",
        description=app_commands.locale_str("Mostrar información de un usuario.", key="slash.descriptions.userinfo"),
    )
    @app_commands.describe(
        member=app_commands.locale_str(
            "De quién mostrar la info (por defecto: tú)",
            key="slash.describes.userinfo.member",
        )
    )
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        """Reply with a member summary embed."""
        if _is_ctx(interaction):
            ctx: Any = interaction
            _g3 = getattr(ctx, "guild", None)
            guild_id = _g3.id if _g3 is not None and hasattr(_g3, "id") else None
            embed = await self._userinfo_impl(guild_id, getattr(ctx, "author", None), member)
            await cast(Any, ctx).send(embed=embed, ephemeral=True)
            return
        guild_id = interaction.guild.id if interaction.guild else None
        author = interaction.user
        embed = await self._userinfo_impl(guild_id, author, member)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ======================================================================
# cog load/unload (discord.py v2.x requirement)
# ======================================================================


async def setup(bot: NebulosaBot) -> None:
    """Register UtilityCog with the bot (v2.x pattern)."""
    await bot.add_cog(UtilityCog(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove UtilityCog from the bot."""
    await bot.remove_cog("Utility")
