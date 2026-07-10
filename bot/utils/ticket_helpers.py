"""Shared helpers for ticket commands.

Extracted from ``bot/cogs/tickets.py`` to deduplicate the repeated
ticket-by-channel lookup pattern used in 7+ command handlers.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import TYPE_CHECKING, Any

from bot.core.i18n import t
from bot.services.ticket_invariants import parse_ticket_ref
from bot.utils.embeds import error_embed

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

# Discord channel name limit is 100 characters.
_CHANNEL_NAME_MAX = 100
# Suffix format: "-NNNN" (5 chars for typical 4-digit numbers).
_SUFFIX_FMT = "-{number:04d}"


def sanitize_channel_name(
    category: str,
    username: str,
    ticket_number: int,
) -> str:
    """Generate a sanitized Discord channel name from ticket metadata.

    Applies Unicode NFKD ASCII folding, lowercase, whitespace-to-hyphen,
    strips non-``[a-z0-9-]``, collapses/strips hyphens, uses ``ticket``/
    ``user`` fallbacks for empty inputs, and truncates the prefix while
    preserving ``-{number:04d}`` within 100 characters.

    Args:
        category: Ticket category name (e.g. ``"Soporte Técnico"``).
        username: Ticket author's display name.
        ticket_number: Sequential ticket number.

    Returns:
        A lowercase, hyphen-separated channel name safe for Discord.
    """

    def _slugify(text: str, fallback: str) -> str:
        # NFKD ASCII folding — strips accents.
        folded = unicodedata.normalize("NFKD", text)
        ascii_text = folded.encode("ascii", "ignore").decode("ascii")
        # Lowercase.
        slug = ascii_text.lower()
        # Whitespace → hyphen.
        slug = re.sub(r"\s+", "-", slug)
        # Strip non-[a-z0-9-].
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Collapse consecutive hyphens.
        slug = re.sub(r"-{2,}", "-", slug)
        # Strip leading/trailing hyphens.
        slug = slug.strip("-")
        return slug or fallback

    cat_slug = _slugify(category, "ticket")
    user_slug = _slugify(username, "user")
    suffix = _SUFFIX_FMT.format(number=ticket_number)

    prefix = f"{cat_slug}-{user_slug}"

    # Truncate prefix to fit within _CHANNEL_NAME_MAX, preserving suffix.
    max_prefix_len = _CHANNEL_NAME_MAX - len(suffix)
    if len(prefix) > max_prefix_len:
        prefix = prefix[:max_prefix_len].rstrip("-")

    return f"{prefix}{suffix}"


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
