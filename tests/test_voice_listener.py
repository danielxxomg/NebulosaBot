"""VoiceListener twins (tests-slim-fase-2 B3) — replaces tests/test_pr3_voice_listener_red.py.

Lean twin of the survivor's 17 tests: transition matrix (join/leave/move/mute/deafen),
config gate, guild-scoped debounce ``{gid}:{mid}`` with TTL + stale eviction, and the
read-only contract (source + runtime). Parametrize ids carry coverage names (D2/D3).
"""

from __future__ import annotations

import inspect
import pathlib
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.listeners.voice_listener import VoiceListener

_PROJECT_LISTENER = pathlib.Path("bot/listeners/voice_listener.py")


def _make_bot(log_enabled: bool = True, log_channel_id: str | None = "999") -> MagicMock:
    guild_service = AsyncMock()
    guild_service.get_config.return_value = MagicMock(log_enabled=log_enabled, log_channel_id=log_channel_id)
    bot = MagicMock()
    bot.guild_service = guild_service
    bot.logging_service = AsyncMock()
    return bot


def _member(guild_id: str = "111", member_id: int = 1, bot: bool = False) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.bot = bot
    m.guild = MagicMock()
    m.guild.id = int(guild_id)
    return m


def _state(channel: int | None = None, self_mute: bool = False, self_deaf: bool = False) -> MagicMock:
    vs = MagicMock(spec=discord.VoiceState)
    vs.channel = None if channel is None else MagicMock(id=channel, name=f"Ch{channel}")
    vs.self_mute = self_mute
    vs.self_deaf = self_deaf
    vs.mute = self_mute
    vs.deaf = self_deaf
    return vs


# ---------------------------------------------------------------------------
# Transition matrix — classification + logging path (survivor 3.4-3.7)
# ---------------------------------------------------------------------------


class TestVoiceListenerTransitions:
    @pytest.mark.parametrize(
        ("b", "a", "expected"),
        [
            pytest.param({"channel": None}, {"channel": 100}, "join", id="transition-join"),
            pytest.param({"channel": 100}, {"channel": None}, "leave", id="transition-leave"),
            pytest.param({"channel": 100}, {"channel": 200}, "move", id="transition-move"),
            pytest.param({"channel": 100}, {"channel": 100, "self_mute": True}, "mute", id="transition-mute"),
            pytest.param({"channel": 100}, {"channel": 100, "self_deaf": True}, "deafen", id="transition-deafen"),
        ],
    )
    async def test_transition_logged(self, b: dict[str, Any], a: dict[str, Any], expected: str) -> None:
        bot = _make_bot()
        await VoiceListener(bot).on_voice_state_update(_member(), _state(**b), _state(**a))
        bot.logging_service.log_voice_event.assert_awaited_once()
        args = bot.logging_service.log_voice_event.call_args.args
        assert args[0] == "111" and args[2] == expected  # guild-scoped: str(guild.id)

    async def test_move_forwards_full_states(self) -> None:
        bot = _make_bot()
        before, after = _state(100), _state(200)
        await VoiceListener(bot).on_voice_state_update(_member(), before, after)
        args = bot.logging_service.log_voice_event.call_args.args
        assert args[3] is before and args[4] is after

    async def test_same_channel_no_toggles_skips(self) -> None:
        bot = _make_bot()
        await VoiceListener(bot).on_voice_state_update(_member(), _state(100), _state(100))
        bot.logging_service.log_voice_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# Config gate + early exits (survivor 3.8-3.9)
# ---------------------------------------------------------------------------


class TestVoiceListenerConfigGate:
    @pytest.mark.parametrize(
        ("log_enabled", "log_channel_id"),
        [
            pytest.param(False, "999", id="gate-log_enabled-false-skips"),
            pytest.param(True, None, id="gate-log_channel_id-null-skips"),
        ],
    )
    async def test_config_gate_skips(self, log_enabled: bool, log_channel_id: str | None) -> None:
        bot = _make_bot(log_enabled=log_enabled, log_channel_id=log_channel_id)
        await VoiceListener(bot).on_voice_state_update(_member(), _state(), _state(100))
        bot.logging_service.log_voice_event.assert_not_awaited()

    async def test_bot_member_and_both_none_skip(self) -> None:
        """Early exits: bot members and null-to-null transitions never log."""
        cases: list[tuple[bool, int | None, int | None]] = [(True, None, 100), (False, None, None)]
        for is_bot, before_channel, after_channel in cases:
            bot = _make_bot()
            await VoiceListener(bot).on_voice_state_update(
                _member(bot=is_bot), _state(before_channel), _state(after_channel)
            )
            bot.logging_service.log_voice_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# Read-only contract — source + runtime (survivor 3.10)
# ---------------------------------------------------------------------------

_VERBS = ("kick", "ban", "edit", "move_to", "timeout")
_FORBIDDEN_MUTATIONS = (
    [f"member.{v}" for v in _VERBS]
    + [f"guild.{v}" for v in _VERBS if v in ("kick", "ban")]
    + ["bot.kick", "bot.ban", "create_dm", ".send("]
)

_MUTATION_TARGETS = ("kick", "ban", "edit", "move_to", "timeout", "create_dm", "send")


class TestVoiceListenerReadOnly:
    def test_listener_never_mutates_members(self) -> None:
        """Source guard: no mutating Discord API calls in listener source."""
        src = _PROJECT_LISTENER.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_MUTATIONS:
            assert pat not in src, f"VoiceListener must be read-only but contains {pat!r}"

    async def test_listener_makes_no_mutation_calls_at_runtime(self) -> None:
        """Runtime guard: a join must await only log_voice_event — no mutations."""
        bot = _make_bot()
        cog = VoiceListener(bot)
        member = _member()
        targets = ((member, _MUTATION_TARGETS), (member.guild, ("kick", "ban")), (bot, ("kick", "ban")))
        for owner, names in targets:
            for name in names:
                setattr(owner, name, AsyncMock())
        await cog.on_voice_state_update(member, _state(), _state(100))
        bot.logging_service.log_voice_event.assert_awaited_once()
        for owner, names in targets:
            for name in names:
                getattr(owner, name).assert_not_awaited()

    def test_listener_is_async_cog_listener(self) -> None:
        src = _PROJECT_LISTENER.read_text(encoding="utf-8")
        assert "class VoiceListener" in src
        assert "on_voice_state_update" in src
        assert "Cog.listener" in src or "@commands.Cog.listener" in src
        assert inspect.iscoroutinefunction(VoiceListener.on_voice_state_update)


# ---------------------------------------------------------------------------
# Debounce — guild-scoped {gid}:{mid} key, TTL, stale eviction (survivor 3.11-3.13)
# ---------------------------------------------------------------------------


class TestVoiceListenerDebounce:
    async def test_rapid_toggles_debounced_to_one(self) -> None:
        bot = _make_bot()
        cog = VoiceListener(bot)
        member = _member(member_id=42)
        for i in range(5):
            await cog.on_voice_state_update(
                member, _state(100, self_mute=i % 2 == 1), _state(100, self_mute=i % 2 == 0)
            )
        assert bot.logging_service.log_voice_event.await_count <= 1

    async def test_debounce_guild_scoped(self) -> None:
        """Same member id in two guilds → distinct {gid}:{mid} keys, both log."""
        bot = _make_bot()
        cog = VoiceListener(bot)
        await cog.on_voice_state_update(_member(guild_id="111"), _state(), _state(100))
        await cog.on_voice_state_update(_member(guild_id="222"), _state(), _state(100))
        assert bot.logging_service.log_voice_event.await_count == 2

    async def test_stale_debounce_entries_evicted(self) -> None:
        bot = _make_bot()
        cog = VoiceListener(bot)
        old = time.monotonic() - 1000
        cog._debounce.update({"111:1": old, "111:2": old, "111:3": old})
        await cog.on_voice_state_update(_member(member_id=99), _state(), _state(100))
        assert "111:1" not in cog._debounce and "111:2" not in cog._debounce
        assert "111:99" in cog._debounce

    async def test_debounce_expires_after_ttl(self) -> None:
        bot = _make_bot()
        cog = VoiceListener(bot)
        member = _member(member_id=5)
        await cog.on_voice_state_update(member, _state(100), _state(100, self_mute=True))
        assert bot.logging_service.log_voice_event.await_count == 1
        await cog.on_voice_state_update(member, _state(100, self_mute=True), _state(100))
        assert bot.logging_service.log_voice_event.await_count == 1  # within TTL suppressed
        with patch("bot.listeners.voice_listener.time.monotonic", return_value=time.monotonic() + 10):
            await cog.on_voice_state_update(member, _state(100), _state(100, self_mute=True))
            assert bot.logging_service.log_voice_event.await_count == 2  # after TTL logs again
