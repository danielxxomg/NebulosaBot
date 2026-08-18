"""Ticket repair coordinator — single eligibility and fresh-probe helpers.

This module is the single source of truth for the evidence/preflight
decision shared by ``handle_channel_delete``, ``sweep_integrity``,
``repair_ticket_by_ref`` and ``repair_ticket_from_evidence``. ``TicketService``
imports and re-exports these symbols so every repair entry point converges on
one fail-closed path without duplicating gate/evidence logic.
"""

from __future__ import annotations

import asyncio
from typing import Any

import discord

from bot.config import INTEGRITY_BACKOFF_SECONDS, INTEGRITY_BATCH_SIZE, INTEGRITY_MAX_BACKOFF_SECONDS


def backoff_delay(attempt: int) -> float:
    """Return exponential backoff delay for *attempt* (0-indexed)."""
    delay = INTEGRITY_BACKOFF_SECONDS * (2 ** max(attempt, 0))
    return float(min(delay, INTEGRITY_MAX_BACKOFF_SECONDS))


def plan_sweep_batch(
    candidates: list[dict[str, Any]],
    *,
    seen: set[str] | None = None,
    batch_size: int = INTEGRITY_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Return next bounded, deduplicated sweep batch."""
    seen = seen if seen is not None else set()
    batch: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(batch) >= batch_size:
            break
        cid = candidate.get("id")
        if cid is None or cid in seen:
            continue
        batch.append(candidate)
        seen.add(cid)
    return batch


async def probe_channel_absence(bot: Any, guild_id: str, channel_id: str) -> bool | None:
    """Probe whether *channel_id* still exists in *guild_id* via a fresh fetch."""
    if guild_id:
        try:
            guild_id_int = int(guild_id)
        except (ValueError, TypeError):
            return None
        guild = bot.get_guild(guild_id_int)
    else:
        guild = None
    if guild is None:
        return None
    try:
        channel_id_int = int(channel_id)
    except (ValueError, TypeError):
        return None
    try:
        await guild.fetch_channel(channel_id_int)
    except discord.NotFound:
        return False
    except (discord.Forbidden, discord.RateLimited, discord.HTTPException):
        return None
    return True


def evaluate_repair_eligibility(
    *,
    preflight_allows: bool,
    corroborated: bool | None,
) -> tuple[str, str] | None:
    """Return the single fail-closed decision for one repair attempt.

    This is the ONE evidence/preflight evaluation shared by the channel-delete
    listener, integrity sweeps, and manual fallback. Adapters never re-evaluate
    and never keep a parallel truth. Pure — no I/O, no mutation.

    Returns ``None`` when the attempt may proceed to the conditional close
    (preflight resolved AND evidence corroborated), otherwise a
    ``(outcome, reason)`` denial tuple.
    """
    if not preflight_allows:
        return ("skipped", "gate_unresolved")
    if corroborated is None:
        return ("skipped", "evidence_unresolved")
    if corroborated is not True:
        return ("skipped", "not_corroborated")
    return None


# Backoff helper re-exported for sweep retry spacing (used by ticket_service).
async def _backoff_sleep(attempt: int) -> None:
    await asyncio.sleep(backoff_delay(attempt))
