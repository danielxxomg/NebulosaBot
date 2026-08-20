"""Ticket integrity flow — manual sweep/repair (S3.4A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.core.i18n import t
from bot.services.ticket_invariants import RepairAuthority
from bot.utils.checks import is_mod_check
from bot.utils.embeds import cog_err as _err
from bot.utils.embeds import cog_info as _info

if TYPE_CHECKING:
    from bot.bot import NebulosaBot
    from bot.core.context import NebulosaContext

logger = logging.getLogger("bot.cogs.tickets")


class TicketIntegrityFlow:
    """Integrity — manual sweep and per-ticket repair."""

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot: NebulosaBot = bot

    async def sweep_integrity(self, ctx: NebulosaContext) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.integrity.server_only"), ephemeral=True)
            return
        gid = str(ctx.guild.id)
        if self.bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        try:
            results = await self.bot.ticket_service.sweep_integrity(gid, self.bot)
        except Exception:
            logger.exception("Failed to run integrity sweep for guild %s", ctx.guild.id)
            await ctx.send(embed=_err(gid, "tickets.integrity.sweep_failed"), ephemeral=True)
            return
        repaired = sum(1 for r in results if r.outcome == "repaired")
        reviewable = len(results) - repaired
        await ctx.send(
            embed=_info(gid, "tickets.integrity.sweep_summary", repaired=repaired, reviewable=reviewable),
            ephemeral=True,
        )

    async def repair_ticket(self, ctx: NebulosaContext, *, ticket_ref: str) -> None:
        if ctx.guild is None:
            await ctx.send(embed=_err(None, "tickets.integrity.server_only"), ephemeral=True)
            return
        gid = str(ctx.guild.id)
        if self.bot.ticket_service is None:
            msg = "ticket_service not initialised"
            raise RuntimeError(msg)
        actor = ctx.author
        is_owner = isinstance(actor, discord.Member) and actor == ctx.guild.owner
        is_admin = isinstance(actor, discord.Member) and actor.guild_permissions.administrator
        has_mod_role = False
        if isinstance(actor, discord.Member):
            _interaction = type(
                "_Interaction",
                (),
                {
                    "user": actor,
                    "guild": ctx.guild,
                    "guild_id": int(gid),
                    "client": self.bot,
                },
            )()
            has_mod_role = await is_mod_check(_interaction) and not is_admin
        authority = RepairAuthority(
            actor_id=str(actor.id),
            guild_id=gid,
            target_guild_id=gid,
            is_guild_owner=is_owner,
            is_administrator=is_admin,
            has_mod_role=has_mod_role,
        )
        try:
            result = await self.bot.ticket_service.repair_ticket_by_ref(
                ticket_ref,
                guild_id=gid,
                actor_id=str(actor.id),
                authority=authority,
                bot=self.bot,
            )
        except Exception:
            logger.exception("Failed to repair ticket (guild=%s, ref=%s)", gid, ticket_ref)
            await ctx.send(embed=_err(gid, "tickets.integrity.repair_failed"), ephemeral=True)
            return
        if result is None:
            await ctx.send(embed=_err(gid, "tickets.reopen.invalid_ref"), ephemeral=True)
            return
        outcome = result.outcome
        reason_suffix = t(gid, "tickets.integrity.repair_result_reason", reason=result.reason) if result.reason else ""
        await ctx.send(
            embed=_info(gid, "tickets.integrity.repair_result", outcome=outcome, reason=reason_suffix),
            ephemeral=True,
        )
