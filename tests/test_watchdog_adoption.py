"""Watchdog adoption guard + wiring — S1 RED suite (strict TDD).

Covers ops-observability delta (spec.md 5 ADDED req, 11 scenarios):
- AST guard per @tasks.loop requires register("name") + heartbeat("name") pair
  (excl. bot/cogs/watchdog.py + bot/core/realtime.py); self-test proves
  detector is non-tautological.
- Heartbeat per tick via get_watchdog(bot.get_cog) — present path.
- Watchdog-absent safe no-op (get_cog None → no exception, logic completes).
- Gated scheduled_close_loop register respects TICKET_TIMER_ENABLED (off→no register).
- resource_log_loop running after CoreCog.cog_load (dead-loop activation).
- Intervals: 300 / 3600 / 60 / 3600 / 3600.
- WARNING exercisable at 2x via _check_once (caplog, stale monotonic).

RED expectation: suite FAILS before wiring (loops unwired), GREEN after S1.
"""

from __future__ import annotations

import ast
import logging
import pathlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.cogs.watchdog import WatchdogCog

# ---------------------------------------------------------------------------
# AST helpers (mirror test_zero_hybrid_guard style — AST + literal scan)
# ---------------------------------------------------------------------------

_EXCLUDE = {"bot/cogs/watchdog.py", "bot/core/realtime.py"}
_LOOP_DECOR = "tasks.loop"


def _loop_names_in_source(src: str, filename: str = "<unknown>") -> list[str]:
    """Return @tasks.loop function names parsed from *src*."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # Match @tasks.loop, @tasks.loop(...), or @loop etc. — check attr chain text
            dec_src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
            attr_name = ""
            if isinstance(dec, ast.Attribute):
                attr_name = dec.attr
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                attr_name = dec.func.attr
            # Fallback via unparse text
            if (attr_name == "loop" or _LOOP_DECOR in dec_src or "loop(" in dec_src) and (
                "loop" in dec_src or attr_name == "loop"
            ):
                names.append(node.name)
                break
            # Also catch simple @tasks.loop without args where unparse may be empty on older py
            if attr_name == "loop" and node.name not in names:
                names.append(node.name)
    # Deduplicate preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def _file_has_pair(src: str, loop_name: str) -> bool:
    """Check file text contains both register("name" and heartbeat("name"."""
    # Literal visibility required by D2 — double-quoted form
    return f'register("{loop_name}"' in src and f'heartbeat("{loop_name}"' in src


def _scan_offenders() -> list[str]:
    """Scan bot/**/*.py (excl. watchdog + realtime) for loops missing wiring."""
    offenders: list[str] = []
    root = pathlib.Path("bot")
    for p in root.rglob("*.py"):
        rel = p.as_posix()
        if rel in _EXCLUDE:
            continue
        src = p.read_text(encoding="utf-8")
        if "@tasks.loop" not in src:
            continue
        loop_names = _loop_names_in_source(src, filename=rel)
        for name in loop_names:
            if not _file_has_pair(src, name):
                offenders.append(f"{rel}:{name} missing register+heartbeat")
    return offenders


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class TestWatchdogAdoptionGuard:
    """AST guard: every production tasks.loop must be watch-dog wired."""

    def test_guard_requires_register_and_heartbeat(self) -> None:
        offenders = _scan_offenders()
        assert offenders == [], f"Unwired loops remain: {offenders}"

    def test_self_test_detector_flags_missing_pair(self) -> None:
        """Non-tautological proof: synthetic loop without pair is flagged; with pair passes."""
        missing_src = """
from discord.ext import tasks
class Foo:
    @tasks.loop(seconds=60)
    async def my_loop(self):
        pass
"""
        names = _loop_names_in_source(missing_src, filename="synthetic_missing.py")
        assert "my_loop" in names, "Synthetic loop must be detected"
        assert not _file_has_pair(missing_src, "my_loop"), "Missing-pair must be flagged"
        # Purposely construct offenders for this synthetic src
        assert not _file_has_pair(missing_src, "my_loop"), "Detector must report missing"

        wired_src = """
from discord.ext import tasks
from bot.cogs.watchdog import get_watchdog
class Foo:
    @tasks.loop(seconds=60)
    async def my_loop(self):
        wd = get_watchdog(self.bot)
        if wd:
            wd.heartbeat("my_loop")
        pass
    async def cog_load(self):
        wd = get_watchdog(self.bot)
        if wd:
            wd.register("my_loop", 60)
"""
        assert _file_has_pair(wired_src, "my_loop"), "Wired pair must be detected"

    def test_watchdog_and_realtime_excluded(self) -> None:
        # watchdog.py contains _check loop but must be excluded
        assert "bot/cogs/watchdog.py" in _EXCLUDE
        assert "bot/core/realtime.py" in _EXCLUDE
        offenders = _scan_offenders()
        # If guard scanned correctly, watchdog's _check must not appear as offender
        assert not any("watchdog.py" in o for o in offenders)
        assert not any("realtime.py" in o for o in offenders)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.guilds = []
    bot.cache = MagicMock()
    bot.cache.size = 0
    bot.db = MagicMock()
    bot.guild_service = MagicMock()
    bot.infraction_service = MagicMock()
    bot.ticket_service = MagicMock()
    bot.logging_service = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.get_channel = MagicMock(return_value=None)
    return bot


# ---------------------------------------------------------------------------
# Wiring — heartbeat per tick + absent-safe + gated + running + WARNING
# ---------------------------------------------------------------------------


class TestWatchdogWiring:
    """Wiring: heartbeat per tick, absent-safe, gated, running, WARNING."""

    @pytest.mark.asyncio
    async def test_resource_log_loop_heartbeats_per_tick(self) -> None:
        from bot.cogs.core import CoreCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = CoreCog(bot)
        # Ensure business-logic helper doesn't hide heartbeat
        if hasattr(cog, "_log_resource_usage"):
            with patch.object(cog, "_log_resource_usage", new_callable=AsyncMock):
                await cog.resource_log_loop()
        else:
            await cog.resource_log_loop()
        watchdog.heartbeat.assert_called_with("resource_log_loop")

    @pytest.mark.asyncio
    async def test_decay_expiry_loop_heartbeats(self) -> None:
        from bot.cogs.sentinel import SentinelCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        # Sentinel decay loop needs db/infraction not None to pass early-return,
        # but heartbeat is BEFORE that check, so no extra setup.
        cog = SentinelCog(bot)
        bot.db = MagicMock()
        bot.infraction_service = MagicMock()
        cog._collect_guild_ids = MagicMock(return_value=[])  # type: ignore[method-assign]  # ty: allow assignment shape
        await cog.decay_expiry_loop()
        watchdog.heartbeat.assert_called_with("decay_expiry_loop")

    @pytest.mark.asyncio
    async def test_scheduled_close_loop_heartbeats(self) -> None:
        from bot.cogs.tickets import TicketsCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = TicketsCog(bot)
        bot.ticket_service = MagicMock()
        bot.ticket_service.get_due_scheduled_tickets = AsyncMock(return_value=[])
        bot.db = MagicMock()
        await cog.scheduled_close_loop()
        watchdog.heartbeat.assert_called_with("scheduled_close_loop")

    @pytest.mark.asyncio
    async def test_auto_close_stale_tickets_heartbeats(self) -> None:
        from bot.cogs.tickets import TicketsCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = TicketsCog(bot)
        bot.guild_service = MagicMock()
        bot.ticket_service = MagicMock()
        bot.ticket_service.get_stale_tickets = AsyncMock(return_value=[])
        bot.guilds = []
        await cog.auto_close_stale_tickets()
        watchdog.heartbeat.assert_called_with("auto_close_stale_tickets")

    @pytest.mark.asyncio
    async def test_integrity_sweep_loop_heartbeats(self) -> None:
        from bot.cogs.tickets import TicketsCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = TicketsCog(bot)
        bot.ticket_service = MagicMock()
        bot.ticket_service.sweep_integrity = AsyncMock()
        bot.guilds = []
        await cog.integrity_sweep_loop()
        watchdog.heartbeat.assert_called_with("integrity_sweep_loop")

    @pytest.mark.asyncio
    async def test_watchdog_absent_is_safe_noop(self) -> None:
        """When watchdog absent, loop body must not raise and business logic completes."""
        from bot.cogs.core import CoreCog

        bot = _make_bot()
        bot.get_cog.return_value = None
        cog = CoreCog(bot)
        # Wrap business logic to prove it still runs
        called = False

        async def _fake_log() -> None:
            nonlocal called
            called = True

        with patch.object(cog, "_log_resource_usage", side_effect=_fake_log):
            # Should not raise even though watchdog is None
            await cog.resource_log_loop()
        assert called, "Business logic must complete when watchdog absent"

    @pytest.mark.asyncio
    async def test_gated_off_no_register_for_scheduled_close(self) -> None:
        from bot.cogs.tickets import TicketsCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = TicketsCog(bot)
        # Mock loops
        cog.auto_close_stale_tickets = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        cog.integrity_sweep_loop = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        cog.scheduled_close_loop = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        with (
            patch.object(cog, "_sync_channel_cache", new_callable=AsyncMock),
            patch("bot.cogs.tickets.TICKET_TIMER_ENABLED", False),
        ):
            await cog.cog_load()
        # When gated off, scheduled_close must NOT be registered/started; others must
        cog.scheduled_close_loop.start.assert_not_called()
        watchdog.register.assert_any_call("auto_close_stale_tickets", 3600)
        watchdog.register.assert_any_call("integrity_sweep_loop", 3600)
        # Ensure scheduled not registered
        registered_names = [c.args[0] for c in watchdog.register.call_args_list]
        assert "scheduled_close_loop" not in registered_names

    @pytest.mark.asyncio
    async def test_gated_on_registers_scheduled_close(self) -> None:
        from bot.cogs.tickets import TicketsCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = TicketsCog(bot)
        cog.auto_close_stale_tickets = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        cog.integrity_sweep_loop = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        cog.scheduled_close_loop = MagicMock(is_running=MagicMock(return_value=False), start=MagicMock())
        with (
            patch.object(cog, "_sync_channel_cache", new_callable=AsyncMock),
            patch("bot.cogs.tickets.TICKET_TIMER_ENABLED", True),
        ):
            await cog.cog_load()
        cog.scheduled_close_loop.start.assert_called_once()
        watchdog.register.assert_any_call("scheduled_close_loop", 60)
        watchdog.register.assert_any_call("auto_close_stale_tickets", 3600)
        watchdog.register.assert_any_call("integrity_sweep_loop", 3600)

    @pytest.mark.asyncio
    async def test_resource_log_loop_running_after_cog_load(self) -> None:
        from bot.cogs.core import CoreCog

        bot = _make_bot()
        watchdog = MagicMock()
        bot.get_cog.return_value = watchdog
        cog = CoreCog(bot)
        # Replace real Loop with mock to observe start + is_running
        mock_loop = MagicMock(is_running=MagicMock(side_effect=[False, True]), start=MagicMock())
        cog.resource_log_loop = mock_loop
        await cog.cog_load()
        mock_loop.start.assert_called_once()
        # After cog_load, is_running should be True
        assert mock_loop.is_running() is True
        watchdog.register.assert_called_with("resource_log_loop", 300)

    @pytest.mark.asyncio
    async def test_check_once_warning_at_2x(self, caplog: pytest.LogCaptureFixture) -> None:
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        cog = WatchdogCog(bot)
        cog.register("resource_log_loop", 300)
        # Stale beyond 2x (600s)
        cog._last_heartbeat["resource_log_loop"] = time.monotonic() - 650
        with caplog.at_level(logging.WARNING, logger="bot.cogs.watchdog"):
            await cog._check_once()
        assert any("resource_log_loop" in r.getMessage() for r in caplog.records)

    def test_extensions_order_watchdog_first(self) -> None:
        from bot.bot import EXTENSIONS

        assert EXTENSIONS[0] == "bot.cogs.watchdog", "Watchdog must be EXTENSIONS[0]"

    def test_get_watchdog_helper_exists(self) -> None:
        import bot.cogs.watchdog as wd_mod

        assert hasattr(wd_mod, "get_watchdog"), "watchdog.py must expose get_watchdog"
        assert callable(wd_mod.get_watchdog)
        bot = MagicMock()
        sentinel = MagicMock()
        bot.get_cog.return_value = sentinel
        assert wd_mod.get_watchdog(bot) is sentinel
        bot.get_cog.return_value = None
        assert wd_mod.get_watchdog(bot) is None
