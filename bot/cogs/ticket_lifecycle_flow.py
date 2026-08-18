"""Ticket lifecycle flow — subticket/reopen/transfer/unclaim (S3.4A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.services.ticket_service import TicketCategoryNotConfiguredError
from bot.utils.checks import is_mod_check
from bot.utils.embeds import error_embed
from bot.utils.ticket_helpers import (
    resolve_category_name,
    resolve_member_safe,
    resolve_mod_role,
    resolve_ticket_for_reopen,
)

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.context import NebulosaContext

logger = logging.getLogger("bot.cogs.tickets")


def _err(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return error_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _ok(gid: str | None, key: str, **kw: object) -> discord.Embed:
    from bot.utils.embeds import success_embed

    return success_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _info(gid: str | None, key: str, **kw: object) -> discord.Embed:
    from bot.utils.embeds import info_embed

    return info_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


class TicketLifecycleFlow:
    """Lifecycle commands — subticket, reopen, transfer, unclaim."""

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def subticket(self, ctx: NebulosaContext) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.subticket.help"))

    @staticmethod
    async def _resolve_parent_owner(
        guild: discord.Guild, parent_author_id: str, ctx: NebulosaContext
    ) -> discord.Member | None:
        gid = str(guild.id)
        if not parent_author_id:
            await ctx.send(embed=_err(gid, "tickets.subticket.owner_not_found"))
            return None
        try:
            member = resolve_member_safe(guild, parent_author_id)
            if member is not None:
                return member
            return await guild.fetch_member(int(parent_author_id))
        except (discord.NotFound, discord.HTTPException, ValueError, TypeError):
            logger.exception("Failed to resolve parent ticket owner %s", parent_author_id)
            await ctx.send(embed=_err(gid, "tickets.subticket.owner_not_found_resolve"))
            return None

    async def subticket_create(self, ctx: NebulosaContext, parent_id: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.subticket.server_only"))
            return
        guild, author = ctx.guild, ctx.author
        gid = str(guild.id)
        assert (
            isinstance(author, discord.Member)
            and self.bot.db is not None
            and self.bot.guild_service is not None
            and self.bot.ticket_service is not None
        )
        try:
            config = await self.bot.guild_service.get_config(gid)
        except Exception:
            logger.exception("Failed to fetch guild config for sub-ticket (guild=%s)", guild.id)
            await ctx.send(embed=_err(gid, "tickets.open.config_error"))
            return
        if not config.ticket_category_id:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.config_missing.title"), t(gid, "tickets.config_missing.description"), guild_id=gid
                )
            )
            return
        try:
            cat_ch = guild.get_channel(int(config.ticket_category_id))
        except (ValueError, TypeError):
            cat_ch = None
        if not isinstance(cat_ch, discord.CategoryChannel):
            await ctx.send(embed=_err(gid, "tickets.subticket.invalid_category"))
            return
        try:
            parent_row = await (
                self.bot.db.get_ticket_by_channel(str(ctx.channel.id), guild_id=gid)
                if parent_id is None
                else self.bot.db.get_ticket(parent_id, guild_id=gid)
            )
        except Exception:
            logger.exception("Failed to look up parent ticket")
            await ctx.send(embed=_err(gid, "tickets.subticket.lookup_failed"))
            return
        if parent_row is None or parent_row.get("status") == "closed":
            await ctx.send(embed=_err(gid, "tickets.subticket.not_ticket"))
            return
        pid = parent_row["id"]
        parent_author_id = parent_row.get("authorId", str(author.id))
        parent_owner: discord.Member | None = (
            author
            if str(author.id) == parent_author_id
            else await self._resolve_parent_owner(guild, parent_author_id, ctx)
        )
        if parent_owner is None:
            return
        mod_role = resolve_mod_role(guild, config.mod_role_id)
        sub_cat_name = await resolve_category_name(self.bot.db, parent_row.get("categoryId"), guild_id=gid)
        try:
            channel, subticket = await self.bot.ticket_service.create_ticket_channel(
                guild,
                cat_ch,
                parent_owner,
                guild_id=gid,
                category_name=sub_cat_name,
                parent_id=pid,
                mod_role=mod_role,
            )
        except discord.HTTPException:
            logger.exception("Failed to create sub-ticket channel")
            await ctx.send(embed=_err(gid, "tickets.subticket.channel_failed"))
            return
        except Exception:
            logger.exception("Failed to create sub-ticket in DB (parent=%s)", pid)
            await ctx.send(embed=_err(gid, "tickets.subticket.creation_failed"))
            return
        from bot.utils.embeds import build_ticket_embed as _bte

        await channel.send(content=parent_owner.mention, embed=_bte(subticket, guild_id=gid))
        await ctx.send(embed=_ok(gid, "tickets.subticket.success", channel=channel.mention))
        logger.info(
            "Sub-ticket #%d created (parent=%s, guild=%s, author=%s)", subticket.ticket_number, pid, guild.id, author.id
        )

    async def reopen(self, ctx: NebulosaContext, *, ticket_ref: str | None = None) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.reopen.server_only"))
            return
        assert self.bot.ticket_service is not None
        gid = str(ctx.guild.id)
        row = await resolve_ticket_for_reopen(self.bot, ctx, ticket_ref, gid)
        if row is None:
            return
        tid = row["id"]
        try:
            await self.bot.ticket_service.reopen_ticket(tid, guild=ctx.guild)
        except TicketCategoryNotConfiguredError:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.config_missing.title"), t(gid, "tickets.config_missing.description"), guild_id=gid
                )
            )
            return
        except ValueError:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.reopen.failed_title"),
                    t(gid, "tickets.reopen.not_closed_description", status=row.get("status", "unknown")),
                    guild_id=gid,
                )
            )
            return
        except Exception:
            logger.exception("Failed to reopen ticket %s", tid)
            await ctx.send(embed=_err(gid, "tickets.reopen.failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.reopen.success"))

    async def transfer(self, ctx: NebulosaContext, member: discord.Member) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.transfer.server_only"))
            return
        gid = str(ctx.guild.id)
        assert self.bot.ticket_service is not None
        assert self.bot.db is not None
        try:
            row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id), guild_id=gid)
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(embed=_err(gid, "tickets.transfer.lookup_failed"))
            return
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.transfer.not_ticket"))
            return
        try:
            await self.bot.ticket_service.transfer_ticket(
                row["id"],
                new_claimed_by=str(member.id),
                actor_id=str(ctx.author.id),
                guild=ctx.guild,
                logging_service=self.bot.logging_service,
                guild_id=gid,
            )
        except Exception:
            logger.exception("Failed to transfer ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.transfer.failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.transfer.success", member=member.mention))

    async def unclaim(self, ctx: NebulosaContext) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.actions.unclaim_not_ticket_title"))
            return
        gid = str(ctx.guild.id)
        assert self.bot.db is not None and self.bot.ticket_service is not None
        try:
            row = await self.bot.db.get_ticket_by_channel(str(ctx.channel.id), guild_id=gid)
        except Exception:
            logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_failed_title"),
                    t(gid, "tickets.actions.unclaim_failed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return
        if row is None:
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_not_ticket_title"),
                    t(gid, "tickets.actions.unclaim_not_ticket_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return
        actor_id = str(ctx.author.id)
        if not row.get("claimedBy"):
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_not_claimed_title"),
                    t(gid, "tickets.actions.unclaim_not_claimed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return
        actor_is_mod = False
        if isinstance(ctx.author, discord.Member):
            _interaction = type(
                "_Interaction",
                (),
                {
                    "user": ctx.author,
                    "guild": ctx.guild,
                    "guild_id": int(gid),
                    "client": self.bot,
                },
            )()
            actor_is_mod = await is_mod_check(_interaction)
        try:
            ticket = await self.bot.ticket_service.unclaim_ticket(
                row["id"], actor_id, is_mod=actor_is_mod, guild_id=gid
            )
        except ValueError as exc:
            reason = str(exc)
            if "not currently claimed" in reason:
                await ctx.send(
                    embed=error_embed(
                        t(gid, "tickets.actions.unclaim_not_claimed_title"),
                        t(gid, "tickets.actions.unclaim_not_claimed_description"),
                        guild_id=gid,
                    ),
                    ephemeral=True,
                )
            else:
                await ctx.send(
                    embed=error_embed(
                        t(gid, "tickets.actions.unclaim_permission_denied_title"),
                        t(gid, "tickets.actions.unclaim_permission_denied_description"),
                        guild_id=gid,
                    ),
                    ephemeral=True,
                )
            return
        except Exception:
            logger.exception("Failed to unclaim ticket %s", row["id"])
            await ctx.send(
                embed=error_embed(
                    t(gid, "tickets.actions.unclaim_failed_title"),
                    t(gid, "tickets.actions.unclaim_failed_description"),
                    guild_id=gid,
                ),
                ephemeral=True,
            )
            return
        from bot.utils.embeds import build_ticket_embed

        embed = build_ticket_embed(ticket, guild_id=gid, bot=self.bot, guild=ctx.guild)
        try:
            async for message in ctx.channel.history(limit=10):
                if message.pinned and message.author == ctx.guild.me:
                    await message.edit(embed=embed)
                    break
        except (discord.HTTPException, discord.Forbidden):
            logger.warning("Failed to refresh ticket embed after unclaim in channel %s", ctx.channel.id)
        await ctx.send(embed=_ok(gid, "tickets.actions.unclaim_success"))
