"""VoiceListener — read-only voice observatory with per-member debounce.

Listens to :meth:`on_voice_state_update` (requires ``intents.voice_states = True``
and the Discord Developer Portal Voice States toggle) and routes meaningful
transitions (join, leave, move, mute, deafen) to
:meth:`~bot.services.logging_service.LoggingService.log_voice_event`.

The listener is strictly read-only (never kick, mute, move, or DM), guild-scoped,
config-gated (``log_enabled`` + ``log_channel_id``), async-only, and debounced
per-member (guild-scoped key ``{guild_id}:{member_id}`` with TTL eviction) to
avoid flooding the log.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)

# Per-member debounce window — rapid toggles within this window coalesce.
_DEBOUNCE_TTL: float = 2.0


class VoiceListener(commands.Cog):
    """Read-only voice observatory — logs voice transitions, no moderation.

    Debounce is guild-scoped via ``{guild_id}:{member_id}`` and evicts stale
    entries on every event so the store never grows unbounded.
    """

    __slots__ = ("_debounce", "_logging", "bot")

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot
        if bot.logging_service is None:
            msg = "LoggingService initialised in setup_hook"
            raise RuntimeError(msg)
        self._logging = bot.logging_service
        self._debounce: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _evict_stale(self, now: float) -> None:
        """Evict debounce entries older than the TTL."""
        stale = [k for k, ts in self._debounce.items() if now - ts > _DEBOUNCE_TTL]
        for k in stale:
            del self._debounce[k]

    @staticmethod
    def _classify_transition(
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> str | None:
        """Return a meaningful transition name or ``None`` if not loggable."""
        b_ch = getattr(before, "channel", None)
        a_ch = getattr(after, "channel", None)

        if b_ch is None and a_ch is not None:
            return "join"
        if b_ch is not None and a_ch is None:
            return "leave"
        if b_ch is not None and a_ch is not None:
            b_id = getattr(b_ch, "id", None)
            a_id = getattr(a_ch, "id", None)
            if b_id is not None and a_id is not None and b_id != a_id:
                return "move"
            # Same channel — mute/deafen toggles.
            if getattr(before, "self_mute", None) != getattr(after, "self_mute", None):
                return "mute"
            if getattr(before, "self_deaf", None) != getattr(after, "self_deaf", None):
                return "deafen"
            # Server mute/deafen aliases (discord.py maps both).
            if getattr(before, "mute", None) != getattr(after, "mute", None):
                return "mute"
            if getattr(before, "deaf", None) != getattr(after, "deaf", None):
                return "deafen"
            return None
        return None

    # ------------------------------------------------------------------
    # Listener
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Log meaningful voice-state transitions with debounce and config gate."""
        # Early exits — keep the listener cheap.
        if getattr(member, "bot", False):
            return
        if getattr(before, "channel", None) is None and getattr(after, "channel", None) is None:
            return

        guild = getattr(member, "guild", None)
        if guild is None:
            return
        guild_id = str(guild.id)
        member_id = str(getattr(member, "id", ""))
        key = f"{guild_id}:{member_id}"

        now = time.monotonic()
        self._evict_stale(now)
        last = self._debounce.get(key)
        if last is not None and now - last < _DEBOUNCE_TTL:
            return

        # Config gate — delegates to GuildService cache (guild-scoped).
        if self.bot.guild_service is None:
            return
        try:
            config = await self.bot.guild_service.get_config(guild_id)
        except Exception:
            logger.exception("Failed to resolve guild config for voice event (guild=%s)", guild_id)
            return
        if not getattr(config, "log_enabled", False):
            return
        if not getattr(config, "log_channel_id", None):
            return

        transition = self._classify_transition(before, after)
        if transition is None:
            return

        # Record debounce before logging so rapid bursts coalesce.
        self._debounce[key] = now
        # Opportunistic second eviction after insert keeps the store bounded.
        # (Stale entries already evicted at the top; this is a no-op in the
        # common case.)
        try:
            await self._logging.log_voice_event(guild_id, member, transition, before, after)
        except Exception:
            logger.exception("Failed to log voice event (guild=%s, member=%s)", guild_id, member_id)


async def setup(bot: NebulosaBot) -> None:
    """Register VoiceListener with the bot."""
    await bot.add_cog(VoiceListener(bot))


async def teardown(bot: NebulosaBot) -> None:
    """Remove VoiceListener from the bot."""
    await bot.remove_cog("VoiceListener")
