"""WatchdogCog — observe+log only.

Detects stalled ``tasks.loop`` instances via ``logging`` at WARNING.
Zero Discord mutations (AGENTS.md listeners rule).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from discord.ext import commands, tasks

if TYPE_CHECKING:
    from bot.bot import NebulosaBot

logger = logging.getLogger(__name__)


class WatchdogCog(commands.Cog, name="Watchdog"):
    """Monotonic heartbeat watchdog for background loops."""

    def __init__(self, bot: NebulosaBot) -> None:
        self.bot = bot
        self._intervals: dict[str, float] = {}
        self._last_heartbeat: dict[str, float] = {}

    def register(self, name: str, interval_s: float) -> None:
        """Register a loop with its expected interval (seconds)."""
        self._intervals[name] = float(interval_s)
        # Initialize heartbeat to now so immediate check is not stale.
        self._last_heartbeat[name] = time.monotonic()

    def heartbeat(self, name: str) -> None:
        """Record a heartbeat for *name* (monotonic)."""
        self._last_heartbeat[name] = time.monotonic()

    async def _check_once(self) -> None:
        """Check all registered loops; WARNING when 2x interval exceeded. Isolated per check."""
        now = time.monotonic()
        for name, interval in list(self._intervals.items()):
            try:
                last = self._last_heartbeat.get(name)
                if last is None:
                    continue
                if now - last > 2 * interval:
                    logger.warning(
                        "Watchdog stall detected: %s interval=%ss last_heartbeat=%.1fs ago",
                        name,
                        interval,
                        now - last,
                    )
            except Exception:  # noqa: BLE001 -- isolated per check
                logger.exception("Watchdog check failed for %s", name)

    @tasks.loop(seconds=30)
    async def _check(self) -> None:
        await self._check_once()

    @_check.before_loop
    async def _before_check(self) -> None:
        await self.bot.wait_until_ready()

    async def cog_unload(self) -> None:
        if self._check.is_running():
            self._check.cancel()


async def setup(bot: NebulosaBot) -> None:
    await bot.add_cog(WatchdogCog(bot))
