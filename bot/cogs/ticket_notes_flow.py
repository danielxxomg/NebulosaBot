"""Ticket notes flow — add/list/delete (S3.4A)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.utils.embeds import error_embed, info_embed, success_embed
from bot.utils.ticket_helpers import resolve_ticket_for_channel

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.context import NebulosaContext

logger = logging.getLogger("bot.cogs.tickets")

INFO = discord.Color.from_str("#5865F2") if hasattr(discord.Color, "from_str") else discord.Color.blurple()


def _err(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return error_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _ok(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return success_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


def _info(gid: str | None, key: str, **kw: object) -> discord.Embed:
    return info_embed(t(gid, f"{key}_title"), t(gid, f"{key}_description", **kw), guild_id=gid)


class TicketNotesFlow:
    """Staff notes — add, list, delete."""

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def note(self, ctx: NebulosaContext) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        await ctx.send(embed=_info(gid, "tickets.note.help"))

    async def note_add(self, ctx: NebulosaContext, content: str) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_add")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.add_not_ticket"))
            return
        if gid is None:
            await ctx.send(embed=_err(gid, "tickets.note.add_failed"))
            return
        try:
            note = await self.bot.ticket_service.create_note(row["id"], str(ctx.author.id), content, guild_id=gid)
        except Exception:
            logger.exception("Failed to add note to ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.note.add_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.add_success", id=note.id))

    async def _send_notes_private(self, ctx: NebulosaContext, embed: discord.Embed) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        if ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
            return
        try:
            await ctx.author.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Failed to DM staff notes to %s", ctx.author.id)
            await ctx.send(embed=_err(gid, "tickets.note.list_dm_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.list_sent"))

    async def note_list(self, ctx: NebulosaContext) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_list")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.add_not_ticket"))
            return
        try:
            if gid is None:
                raise ValueError("guild_id required")
            notes = await self.bot.ticket_service.get_notes(row["id"], guild_id=gid)
        except Exception:
            logger.exception("Failed to fetch notes for ticket %s", row["id"])
            await ctx.send(embed=_err(gid, "tickets.note.add_failed"))
            return
        if not notes:
            await self._send_notes_private(ctx, _info(gid, "tickets.note.list_no_notes"))
            return
        lines = [f"`{n.id}` <@{n.author_id}> \u2014 {n.content}" for n in notes]
        embed = discord.Embed(
            title=t(gid, "tickets.note.list_title"),
            description="\n".join(lines),
            color=INFO,
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=t(gid, "tickets.open.footer"))
        await self._send_notes_private(ctx, embed)

    async def note_delete(self, ctx: NebulosaContext, note_id: str) -> None:
        gid = str(ctx.guild.id) if ctx.guild else None
        assert self.bot.ticket_service is not None
        row = await resolve_ticket_for_channel(self.bot, ctx.channel.id, gid, action="note_delete")
        if row is None:
            await ctx.send(embed=_err(gid, "tickets.note.delete_not_ticket"))
            return
        try:
            if gid is None:
                raise ValueError("guild_id required")
            await self.bot.ticket_service.delete_note(
                note_id=note_id, author_id=str(ctx.author.id), ticket_id=row["id"], guild_id=gid
            )
        except Exception:
            logger.exception("Failed to delete note %s", note_id)
            await ctx.send(embed=_err(gid, "tickets.note.delete_failed"))
            return
        await ctx.send(embed=_ok(gid, "tickets.note.delete_success", id=note_id))
