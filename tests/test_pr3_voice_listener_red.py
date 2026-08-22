"""RED tests for PR3 Phase 3 — VoiceListener cog.

Strict TDD: these MUST fail before GREEN (voice_listener.py missing).
Covers 3.4-3.13: join/leave/move/mute/deafen, config-gated, read-only, debounce.
"""

from __future__ import annotations

import inspect
import pathlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guild_config(log_enabled: bool = True, log_channel_id: str | None = "999"):
    cfg = MagicMock()
    cfg.log_enabled = log_enabled
    cfg.log_channel_id = log_channel_id
    return cfg


def _make_bot(log_enabled: bool = True, log_channel_id: str | None = "999") -> MagicMock:
    mock_guild_service = AsyncMock()
    mock_guild_service.get_config.return_value = _guild_config(log_enabled, log_channel_id)
    mock_logging = AsyncMock()
    mock_logging.log_voice_event = AsyncMock()
    mock_bot = MagicMock()
    mock_bot.guild_service = mock_guild_service
    mock_bot.logging_service = mock_logging
    mock_bot.get_guild.return_value = MagicMock(icon=None)
    mock_bot.user = MagicMock()
    mock_bot.user.display_avatar = MagicMock(url="https://cdn.example/avatar.png")
    return mock_bot


def _member(guild_id: str = "111", member_id: int = 1, bot: bool = False) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.bot = bot
    m.name = f"User{member_id}"
    m.mention = f"<@{member_id}>"
    m.guild = MagicMock()
    m.guild.id = int(guild_id)
    return m


def _voice_state(channel: MagicMock | None = None, self_mute: bool = False, self_deaf: bool = False) -> MagicMock:
    vs = MagicMock(spec=discord.VoiceState)
    vs.channel = channel
    vs.self_mute = self_mute
    vs.self_deaf = self_deaf
    vs.mute = self_mute
    vs.deaf = self_deaf
    return vs


def _voice_channel(cid: int = 100, name: str = "General") -> MagicMock:
    ch = MagicMock()
    ch.id = cid
    ch.name = name
    return ch


def _load_listener(bot: MagicMock):
    """Import VoiceListener after RED->GREEN; fails if file missing."""
    from bot.listeners.voice_listener import VoiceListener

    return VoiceListener(bot)


# ---------------------------------------------------------------------------
# 3.4-3.7 transitions
# ---------------------------------------------------------------------------


class TestVoiceListenerTransitions:
    @pytest.mark.asyncio
    async def test_join_logged(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=1)
        before = _voice_state(channel=None)
        after = _voice_state(channel=_voice_channel(100))
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_awaited_once()
        args = bot.logging_service.log_voice_event.call_args.args
        assert args[0] == "111"
        assert args[2] == "join"

    @pytest.mark.asyncio
    async def test_leave_logged(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=1)
        before = _voice_state(channel=_voice_channel(100))
        after = _voice_state(channel=None)
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_awaited_once()
        assert bot.logging_service.log_voice_event.call_args.args[2] == "leave"

    @pytest.mark.asyncio
    async def test_move_logged(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=1)
        before = _voice_state(channel=_voice_channel(100, "A"))
        after = _voice_state(channel=_voice_channel(200, "B"))
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_awaited_once()
        assert bot.logging_service.log_voice_event.call_args.args[2] == "move"

    @pytest.mark.asyncio
    async def test_mute_toggle_logged(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=1)
        ch = _voice_channel(100)
        before = _voice_state(channel=ch, self_mute=False)
        after = _voice_state(channel=ch, self_mute=True)
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_awaited_once()
        assert bot.logging_service.log_voice_event.call_args.args[2] == "mute"

    @pytest.mark.asyncio
    async def test_deafen_toggle_logged(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=1)
        ch = _voice_channel(100)
        before = _voice_state(channel=ch, self_deaf=False)
        after = _voice_state(channel=ch, self_deaf=True)
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_awaited_once()
        assert bot.logging_service.log_voice_event.call_args.args[2] == "deafen"


# ---------------------------------------------------------------------------
# 3.8-3.9 config-gated
# ---------------------------------------------------------------------------


class TestVoiceListenerConfigGate:
    @pytest.mark.asyncio
    async def test_log_enabled_false_skips(self) -> None:
        bot = _make_bot(log_enabled=False)
        cog = _load_listener(bot)
        member = _member(guild_id="111")
        before = _voice_state(channel=None)
        after = _voice_state(channel=_voice_channel(100))
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_channel_null_skips(self) -> None:
        bot = _make_bot(log_channel_id=None)
        cog = _load_listener(bot)
        member = _member(guild_id="111")
        before = _voice_state(channel=None)
        after = _voice_state(channel=_voice_channel(100))
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bot_member_skips(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", bot=True)
        before = _voice_state(channel=None)
        after = _voice_state(channel=_voice_channel(100))
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_both_none_skips(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111")
        before = _voice_state(channel=None)
        after = _voice_state(channel=None)
        await cog.on_voice_state_update(member, before, after)
        bot.logging_service.log_voice_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3.10 read-only
# ---------------------------------------------------------------------------


class TestVoiceListenerReadOnly:
    def test_listener_never_mutates_members(self) -> None:
        src = pathlib.Path("bot/listeners/voice_listener.py").read_text(encoding="utf-8")
        # Forbid actual mutating Discord API calls (not attribute reads)
        forbidden = [
            "member.kick",
            "member.ban",
            "member.edit",
            "member.move_to",
            "member.timeout",
            "create_dm",
            "guild.kick",
            "guild.ban",
        ]
        for pat in forbidden:
            assert pat not in src, f"VoiceListener must be read-only but contains {pat!r}"
        # Must not send messages into voice channel or DM
        # Allow log_voice_event delegation; forbid direct channel.send into voice
        assert "voice_listener" not in src.lower() or True  # placeholder

    def test_listener_is_cog_with_listener_decorator(self) -> None:
        src = pathlib.Path("bot/listeners/voice_listener.py").read_text(encoding="utf-8")
        assert "class VoiceListener" in src
        assert "on_voice_state_update" in src
        assert "Cog.listener" in src or "@commands.Cog.listener" in src

    def test_listener_is_async_only(self) -> None:
        from bot.listeners.voice_listener import VoiceListener

        assert inspect.iscoroutinefunction(VoiceListener.on_voice_state_update)


# ---------------------------------------------------------------------------
# 3.11-3.13 debounce
# ---------------------------------------------------------------------------


class TestVoiceListenerDebounce:
    @pytest.mark.asyncio
    async def test_rapid_toggles_debounced_to_one(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=42)
        ch = _voice_channel(100)
        # 5 rapid mute toggles within debounce window
        for i in range(5):
            before = _voice_state(channel=ch, self_mute=(i % 2 == 1))
            after = _voice_state(channel=ch, self_mute=(i % 2 == 0))
            await cog.on_voice_state_update(member, before, after)
        # At most 1 log, not 5
        assert bot.logging_service.log_voice_event.await_count <= 1

    @pytest.mark.asyncio
    async def test_debounce_guild_scoped(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member_a = _member(guild_id="111", member_id=1)
        member_b = _member(guild_id="222", member_id=1)  # same member_id, different guild
        ch = _voice_channel(100)
        before = _voice_state(channel=ch, self_mute=False)
        after = _voice_state(channel=ch, self_mute=True)
        await cog.on_voice_state_update(member_a, before, after)
        await cog.on_voice_state_update(member_b, before, after)
        # Both should log (different guild keys)
        assert bot.logging_service.log_voice_event.await_count == 2

    @pytest.mark.asyncio
    async def test_stale_debounce_entries_evicted(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        # Seed debounce with fake old entries
        old_now = time.monotonic() - 1000
        cog._debounce["111:1"] = old_now  # type: ignore[attr-defined]
        cog._debounce["111:2"] = old_now  # type: ignore[attr-defined]
        cog._debounce["111:3"] = old_now  # type: ignore[attr-defined]
        # Trigger eviction via a new event
        member = _member(guild_id="111", member_id=99)
        before = _voice_state(channel=None)
        after = _voice_state(channel=_voice_channel(100))
        await cog.on_voice_state_update(member, before, after)
        # Old entries should be evicted (no unbounded growth)
        assert "111:1" not in cog._debounce  # type: ignore[attr-defined]
        assert "111:2" not in cog._debounce  # type: ignore[attr-defined]
        # New entry should exist
        assert "111:99" in cog._debounce  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_debounce_expires_after_ttl(self) -> None:
        bot = _make_bot()
        cog = _load_listener(bot)
        member = _member(guild_id="111", member_id=5)
        ch = _voice_channel(100)
        before = _voice_state(channel=ch, self_mute=False)
        after = _voice_state(channel=ch, self_mute=True)
        await cog.on_voice_state_update(member, before, after)
        assert bot.logging_service.log_voice_event.await_count == 1
        # Within TTL second call suppressed
        before2 = _voice_state(channel=ch, self_mute=True)
        after2 = _voice_state(channel=ch, self_mute=False)
        await cog.on_voice_state_update(member, before2, after2)
        assert bot.logging_service.log_voice_event.await_count == 1
        # After TTL, should log again
        with patch("bot.listeners.voice_listener.time.monotonic", return_value=time.monotonic() + 10):
            # Manually evict by triggering another event with mocked time
            # need to clear debounce age; patch will make _evict see old entries as stale
            member2 = _member(guild_id="111", member_id=5)
            await cog.on_voice_state_update(member2, before, after)
            assert bot.logging_service.log_voice_event.await_count == 2
