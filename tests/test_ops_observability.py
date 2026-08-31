"""ops-observability RED suite — STRICT TDD.

Scenarios from ops-observability/spec.md:
- DSN present → sentry_sdk.init(dsn, send_default_pii=False, before_send=_scrub)
- DSN absent/empty/whitespace → no init, boot succeeds
- _scrub drops token/SUPABASE/DISCORD and raw message content (No PII)

Additionally: WatchdogCog — stall WARNING at 2x interval (monotonic+caplog),
zero discord mutations, isolation, cog_unload cancel.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import logging
import os
import pathlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import tasks

from bot.cogs.watchdog import WatchdogCog


class TestSentryGate:
    """Sentry env-gated init — ops-observability Requirement: Sentry env-gated init."""

    def test_dsn_absent_no_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        with patch("sentry_sdk.init") as mock_init:
            mod = importlib.import_module("bot.__main__")
            assert hasattr(mod, "_init_sentry") or hasattr(mod, "init_sentry"), (
                "bot.__main__ must expose _init_sentry/init_sentry for gate test"
            )
            fn = getattr(mod, "_init_sentry", None) or mod.init_sentry
            fn()
            mock_init.assert_not_called()

    def test_dsn_empty_no_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "")
        with patch("sentry_sdk.init") as mock_init:
            mod = importlib.import_module("bot.__main__")
            fn = getattr(mod, "_init_sentry", None) or mod.init_sentry
            fn()
            mock_init.assert_not_called()

    def test_dsn_whitespace_no_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "   \n")
        with patch("sentry_sdk.init") as mock_init:
            mod = importlib.import_module("bot.__main__")
            fn = getattr(mod, "_init_sentry", None) or mod.init_sentry
            fn()
            mock_init.assert_not_called()

    def test_dsn_present_calls_init_with_scrub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        dsn = "https://example@sentry.io/1"
        monkeypatch.setenv("SENTRY_DSN", dsn)
        with patch("sentry_sdk.init") as mock_init:
            mod = importlib.import_module("bot.__main__")
            fn = getattr(mod, "_init_sentry", None) or mod.init_sentry
            fn()
            mock_init.assert_called_once()
            kwargs = mock_init.call_args.kwargs
            assert kwargs.get("dsn") == dsn
            assert kwargs.get("send_default_pii") is False
            assert callable(kwargs.get("before_send"))

    def test_scrub_drops_token_supabase_discord_and_message(self) -> None:
        mod = importlib.import_module("bot.__main__")
        scrub = getattr(mod, "_scrub", None)
        assert callable(scrub), "bot.__main__ must expose _scrub(event, hint) -> event|None"
        # Event with secrets + message content
        event = {
            "extra": {"token": "abc", "SUPABASE_DB_URL": "postgres://...", "DISCORD_TOKEN": "tok"},
            "breadcrumbs": {"values": [{"message": "hello world"}]},
            "message": "raw user message",
            "exception": {"values": [{"value": "token leak"}]},
        }
        hint: dict = {}
        # Provide env values that should be scrubbed if they appear
        with patch.dict(os.environ, {"DISCORD_TOKEN": "tok", "SUPABASE_DB_URL": "postgres://..."}):
            result = scrub(event, hint)
        # scrub must drop/replace secrets and raw message; never return PII-bearing payload
        assert result is not None
        payload = str(result)
        assert "tok" not in payload
        assert "hello world" not in payload
        assert "raw user message" not in payload

    def test_scrub_returns_event_when_clean(self) -> None:
        mod = importlib.import_module("bot.__main__")
        scrub = getattr(mod, "_scrub", None)
        assert callable(scrub)
        event: dict = {"extra": {"safe": "ok"}, "message": "filtered?"}
        result = scrub(event, {})
        assert result is not None
        assert "filtered?" not in str(result)


class TestWatchdogCog:
    """Watchdog STALL + no-mutation + lifecycle — ops-observability Requirement: Watchdog observe+log only."""

    @pytest.mark.asyncio
    async def test_stall_logs_warning_at_2x_interval(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        cog = WatchdogCog(bot)
        # Register a loop named auto_close_stale_tickets with interval 60s
        cog.register("auto_close_stale_tickets", 60)
        # Force stale: last heartbeat is 130s ago (>2*60=120)
        stale_time = time.monotonic() - 130
        cog._last_heartbeat["auto_close_stale_tickets"] = stale_time
        with caplog.at_level(logging.WARNING, logger="bot.cogs.watchdog"):
            await cog._check_once()
        assert any("auto_close_stale_tickets" in r.getMessage() for r in caplog.records), caplog.records
        # Second triangulation: different interval, not yet stale → no warning
        caplog.clear()
        cog2 = WatchdogCog(MagicMock())
        cog2.register("integrity_sweep_loop", 60)
        cog2._last_heartbeat["integrity_sweep_loop"] = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="bot.cogs.watchdog"):
            await cog2._check_once()
        assert not any("integrity_sweep_loop" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_discord_mutations_on_check(self) -> None:
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        cog = WatchdogCog(bot)
        cog.register("x", 10)
        cog._last_heartbeat["x"] = time.monotonic() - 25
        # Attach a discord-like mock — any mutation call must be zero.
        discord_mock = MagicMock()
        cog.bot = discord_mock
        await cog._check_once()
        for name in ("kick", "ban", "move", "send", "add_roles", "remove_roles", "timeout"):
            mock_attr = getattr(discord_mock, name, None)
            if mock_attr is not None:
                assert not mock_attr.called, f"Watchdog mutated via {name}"

    def test_source_has_no_discord_mutations(self) -> None:
        src = pathlib.Path("bot/cogs/watchdog.py").read_text(encoding="utf-8")
        for token in ("discord.Member", "discord.Channel", ".kick(", ".ban(", ".move(", "add_roles", "remove_roles"):
            assert token not in src, f"watchdog must not contain {token}"
        assert "@tasks.loop" in src
        assert "before_loop" in src
        assert "cog_unload" in src
        assert "monotonic" in src

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_loop(self) -> None:
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        cog = WatchdogCog(bot)
        with (
            patch.object(cog._check, "is_running", return_value=True),
            patch.object(cog._check, "cancel") as cancel_mock,
        ):
            await cog.cog_unload()
            cancel_mock.assert_called_once()
        # Also verify non-running path does not cancel
        with (
            patch.object(cog._check, "is_running", return_value=False),
            patch.object(cog._check, "cancel") as cancel_mock2,
        ):
            await cog.cog_unload()
            cancel_mock2.assert_not_called()

    def test_register_and_heartbeat_monotonic(self) -> None:
        cog = WatchdogCog(MagicMock())
        before = time.monotonic()
        cog.register("a", 5)
        cog.heartbeat("a")
        ts = cog._last_heartbeat["a"]
        assert ts >= before

    def test_setup_registers_cog(self) -> None:
        mod = importlib.import_module("bot.cogs.watchdog")
        assert hasattr(mod, "setup"), "WatchdogCog must expose async def setup(bot)"
        assert inspect.iscoroutinefunction(mod.setup)


class TestLoopErrorRouting:
    """OO-R3 PRESERVED — tasks.loop body RuntimeError routes via logging, never stderr/print.

    Scenario: Raised loop body is logged (spec: ops-observability, spec.md:51-55).
    This is a regression guard — framework already logs via ``Loop._error``
    (``tasks/__init__.py:415`` ``_log.error(..., exc_info=exception)``) so the
    test is expected GREEN on first honest run. If it goes RED, the behavior
    regressed.
    """

    @pytest.mark.asyncio
    async def test_raised_loop_body_is_logged(
        self, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:  # noqa: ARG002
        """Real tasks.loop whose body raises RuntimeError is logged via logging at ERROR with exc_info.

        Also asserts no stderr/print leakage. Non-flaky: short 0.02s interval,
        poll until Loop.failed()/caplog, always cancel in finally.
        """

        @tasks.loop(seconds=0.02)
        async def boom_once() -> None:
            raise RuntimeError("boom under test")

        # Capture stderr explicitly to prove no print/stderr branch exists
        caplog.set_level(logging.ERROR, logger="discord.ext.tasks")
        boom_once.start()
        try:
            # Poll until the loop records an ERROR or transitions to failed()
            for _ in range(50):
                await asyncio.sleep(0.02)
                if boom_once.failed() or any(
                    r.levelno >= logging.ERROR for r in caplog.records if r.name == "discord.ext.tasks"
                ):
                    break

            error_records = [r for r in caplog.records if r.name == "discord.ext.tasks" and r.levelno >= logging.ERROR]
            assert len(error_records) >= 1, "Loop._error must log at ERROR via discord.ext.tasks logger"
            rec = error_records[0]
            assert rec.exc_info is not None and rec.exc_info[0] is not None, "Logged record must carry exc_info"
            assert issubclass(rec.exc_info[0], RuntimeError)
            assert "boom under test" in str(rec.exc_info[1])
            assert boom_once.failed() is True

            # No stderr/print path — the event is via logging, not raw stderr
            captured = capsys.readouterr()
            assert captured.err == ""
            assert captured.out == ""
        finally:
            boom_once.cancel()
            t = boom_once.get_task()
            if t is not None:
                with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                    await asyncio.wait_for(t, timeout=0.5)
            # Drain any pending loop scheduling so following tests are isolated
            await asyncio.sleep(0.05)
