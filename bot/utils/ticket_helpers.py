"""Shared helpers for ticket commands.

Extracted from ``bot/cogs/tickets.py`` to deduplicate the repeated
ticket-by-channel lookup pattern used in 7+ command handlers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bot.core.i18n import t
from bot.services.ticket_invariants import parse_ticket_ref
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


async def resolve_ticket_for_channel(
    bot: NebulosaBot,
    channel_id: int,
    guild_id: str | None,
    *,
    action: str = "lookup",
) -> dict[str, Any] | None:
    """Resolve a ticket row by the current channel ID.

    Returns the raw DB row dict on success, or ``None`` after logging
    the error (the caller MUST check and send its own error embed).
    """
    assert bot.db is not None
    try:
        ticket_row = await bot.db.get_ticket_by_channel(str(channel_id))
    except Exception:
        logger.exception("Failed to look up ticket by channel %s", channel_id)
        return None
    if ticket_row is None:
        return None
    return ticket_row


async def resolve_ticket_for_reopen(
    bot: NebulosaBot,
    ctx: Any,  # commands.Context
    ticket_ref: str | None,
    guild_id: str,
) -> dict[str, Any] | None:
    """Resolve the ticket row for ``/reopen`` by ref or channel (legacy).

    Returns the ticket row dict on success or ``None`` after sending an
    ``error_embed``.
    """
    assert bot.db is not None
    ref = parse_ticket_ref(ticket_ref)

    if ticket_ref is not None and ref is None:
        await ctx.send(
            embed=error_embed(
                t(guild_id, "tickets.reopen.invalid_ref_title"),
                t(guild_id, "tickets.reopen.invalid_ref_description", ref=ticket_ref),
                guild_id=guild_id,
            )
        )
        return None

    if ref is not None and ref.number is not None:
        try:
            row = await bot.db.get_ticket_by_number(guild_id, ref.number)
        except Exception:
            logger.exception("Failed to look up ticket by number %d", ref.number)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "tickets.reopen.lookup_failed_title"),
                    t(guild_id, "tickets.reopen.lookup_failed_description"),
                    guild_id=guild_id,
                )
            )
            return None
        if row is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "tickets.reopen.not_found_title"),
                    t(guild_id, "tickets.reopen.not_found_description", number=ref.number),
                    guild_id=guild_id,
                )
            )
            return None
        return row

    if ref is not None and ref.uuid is not None:
        try:
            row = await bot.db.get_ticket(ref.uuid)
        except Exception:
            logger.exception("Failed to look up ticket by UUID %s", ref.uuid)
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "tickets.reopen.lookup_failed_title"),
                    t(guild_id, "tickets.reopen.lookup_failed_description"),
                    guild_id=guild_id,
                )
            )
            return None
        if row is None:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "tickets.reopen.not_found_uuid_title"),
                    t(guild_id, "tickets.reopen.not_found_uuid_description", id=ref.uuid),
                    guild_id=guild_id,
                )
            )
            return None
        if row.get("guildId") != guild_id:
            await ctx.send(
                embed=error_embed(
                    t(guild_id, "tickets.reopen.wrong_guild_title"),
                    t(guild_id, "tickets.reopen.wrong_guild_description"),
                    guild_id=guild_id,
                )
            )
            return None
        return row

    # Legacy channel-scoped lookup.
    try:
        ticket_row = await bot.db.get_ticket_by_channel(str(ctx.channel.id))
    except Exception:
        logger.exception("Failed to look up ticket by channel %s", ctx.channel.id)
        await ctx.send(
            embed=error_embed(
                t(guild_id, "tickets.reopen.lookup_failed_title"),
                t(guild_id, "tickets.reopen.lookup_failed_description"),
                guild_id=guild_id,
            )
        )
        return None
    if ticket_row is None:
        await ctx.send(
            embed=error_embed(
                t(guild_id, "tickets.reopen.not_ticket_title"),
                t(guild_id, "tickets.reopen.not_ticket_description"),
                guild_id=guild_id,
            )
        )
        return None
    return ticket_row
