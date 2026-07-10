"""Unit tests for bot.utils.ticket_helpers.

Covers:
    - sanitize_channel_name: channel name generation, folding, truncation
    - build_ticket_overwrites: permission overwrite dict construction
    - resolve_mod_role: guild role resolution with fallback
    - resolve_member_safe: guild member resolution with fallback
    - resolve_category_name: async DB category name resolution
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.ticket_helpers import (
    build_ticket_overwrites,
    resolve_category_name,
    resolve_member_safe,
    resolve_mod_role,
    sanitize_channel_name,
)

# ---------------------------------------------------------------------------
# Standard happy path
# ---------------------------------------------------------------------------


def test_standard_channel_name() -> None:
    """Soporte + DanielXX + 42 → soporte-danielxx-0042."""
    assert sanitize_channel_name("Soporte", "DanielXX", 42) == "soporte-danielxx-0042"


def test_single_word_category() -> None:
    """Help + user1 + 1 → help-user1-0001."""
    assert sanitize_channel_name("Help", "user1", 1) == "help-user1-0001"


def test_category_with_spaces() -> None:
    """Tech Support + alice + 7 → tech-support-alice-0007."""
    assert sanitize_channel_name("Tech Support", "alice", 7) == "tech-support-alice-0007"


# ---------------------------------------------------------------------------
# Unicode NFKD ASCII folding
# ---------------------------------------------------------------------------


def test_accented_category_folded() -> None:
    """Soporte Técnico → soporte-tecnico (accent stripped)."""
    result = sanitize_channel_name("Soporte Técnico", "user", 1)
    assert result == "soporte-tecnico-user-0001"


def test_accented_username_folded() -> None:
    """Username with ñ and accents folded; underscore stripped."""
    result = sanitize_channel_name("support", "José_Muñoz", 5)
    # Underscore is stripped per spec (non [a-z0-9-]).
    assert result == "support-josemunoz-0005"


def test_non_latin_chars_stripped() -> None:
    """Non-ASCII chars that can't be folded are stripped."""
    result = sanitize_channel_name("日本語", "user", 1)
    # All CJK chars stripped → fallback "ticket"
    assert result == "ticket-user-0001"


# ---------------------------------------------------------------------------
# Special character stripping
# ---------------------------------------------------------------------------


def test_special_chars_stripped() -> None:
    """user_123! → user123."""
    result = sanitize_channel_name("support", "user_123!", 42)
    assert result == "support-user123-0042"


def test_category_with_special_chars() -> None:
    """Soporte@#$ → soporte."""
    result = sanitize_channel_name("Soporte@#$", "alice", 1)
    assert result == "soporte-alice-0001"


# ---------------------------------------------------------------------------
# Hyphen handling
# ---------------------------------------------------------------------------


def test_multiple_spaces_collapsed() -> None:
    """Multiple spaces become a single hyphen."""
    result = sanitize_channel_name("Tech   Support", "alice", 1)
    assert result == "tech-support-alice-0001"


def test_leading_trailing_hyphens_stripped() -> None:
    """Leading/trailing hyphens are stripped from prefix."""
    result = sanitize_channel_name("--support--", "--alice--", 1)
    assert result == "support-alice-0001"


def test_consecutive_hyphens_collapsed() -> None:
    """Consecutive hyphens collapse to one."""
    result = sanitize_channel_name("a--b", "c--d", 1)
    assert result == "a-b-c-d-0001"


# ---------------------------------------------------------------------------
# Empty/blank input fallbacks
# ---------------------------------------------------------------------------


def test_empty_category_uses_ticket_fallback() -> None:
    """Empty category → 'ticket'."""
    assert sanitize_channel_name("", "alice", 1) == "ticket-alice-0001"


def test_empty_username_uses_user_fallback() -> None:
    """Empty username → 'user'."""
    assert sanitize_channel_name("support", "", 1) == "support-user-0001"


def test_both_empty_uses_both_fallbacks() -> None:
    """Both empty → ticket-user-0001."""
    assert sanitize_channel_name("", "", 1) == "ticket-user-0001"


def test_whitespace_only_category_uses_fallback() -> None:
    """Whitespace-only category → 'ticket'."""
    assert sanitize_channel_name("   ", "alice", 1) == "ticket-alice-0001"


def test_whitespace_only_username_uses_fallback() -> None:
    """Whitespace-only username → 'user'."""
    assert sanitize_channel_name("support", "   ", 1) == "support-user-0001"


def test_all_special_chars_category_uses_fallback() -> None:
    """Category with only special chars → 'ticket'."""
    assert sanitize_channel_name("@#$%^&", "alice", 1) == "ticket-alice-0001"


def test_all_special_chars_username_uses_fallback() -> None:
    """Username with only special chars → 'user'."""
    assert sanitize_channel_name("support", "@#$%^&", 1) == "support-user-0001"


# ---------------------------------------------------------------------------
# Truncation preserving suffix
# ---------------------------------------------------------------------------


def test_long_name_truncated_preserving_suffix() -> None:
    """Name exceeding 100 chars is truncated, preserving -{number:04d}."""
    long_cat = "a" * 80
    long_user = "b" * 80
    result = sanitize_channel_name(long_cat, long_user, 42)
    assert len(result) <= 100
    assert result.endswith("-0042")


def test_truncation_preserves_full_suffix() -> None:
    """After truncation, the -XXXX suffix is complete, not split."""
    # Create a name that would be ~120 chars
    result = sanitize_channel_name("A" * 60, "B" * 60, 99)
    assert len(result) <= 100
    assert result.endswith("-0099")
    # The suffix is exactly 5 chars: "-0099"
    suffix = result[-5:]
    assert suffix == "-0099"


def test_short_name_not_truncated() -> None:
    """Short names are NOT truncated."""
    result = sanitize_channel_name("help", "alice", 1)
    assert result == "help-alice-0001"
    assert len(result) < 100


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------


def test_zero_padded_four_digits() -> None:
    """Ticket number is zero-padded to 4 digits."""
    assert sanitize_channel_name("x", "y", 0).endswith("-0000")
    assert sanitize_channel_name("x", "y", 1).endswith("-0001")
    assert sanitize_channel_name("x", "y", 42).endswith("-0042")
    assert sanitize_channel_name("x", "y", 999).endswith("-0999")
    assert sanitize_channel_name("x", "y", 1000).endswith("-1000")
    assert sanitize_channel_name("x", "y", 9999).endswith("-9999")


def test_large_ticket_number() -> None:
    """Ticket numbers > 9999 use more than 4 digits."""
    result = sanitize_channel_name("support", "alice", 10000)
    assert result.endswith("-10000")


# ---------------------------------------------------------------------------
# Case normalization
# ---------------------------------------------------------------------------


def test_uppercase_folded_to_lowercase() -> None:
    """All uppercase is folded to lowercase."""
    assert sanitize_channel_name("SOPORTE", "ALICE", 1) == "soporte-alice-0001"


def test_mixed_case_folded() -> None:
    """Mixed case → all lowercase."""
    assert sanitize_channel_name("TechSupport", "AliceBob", 1) == "techsupport-alicebob-0001"


# ---------------------------------------------------------------------------
# Discord channel name constraints
# ---------------------------------------------------------------------------


def test_result_is_valid_discord_channel_name() -> None:
    """Result must be lowercase alphanumeric with hyphens only."""
    import re

    result = sanitize_channel_name("Soporte Técnico!", "user_123", 42)
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", result)


# ===========================================================================
# build_ticket_overwrites — permission overwrite dict construction
# ===========================================================================


def _make_guild(*, default_role: MagicMock | None = None, me: MagicMock | None = None) -> MagicMock:
    """Create a mock guild with default_role and me attributes."""
    guild = MagicMock()
    guild.default_role = default_role or MagicMock(name="default_role")
    guild.me = me or MagicMock(name="bot_member")
    return guild


def _make_member(name: str = "TestUser", id: int = 111) -> MagicMock:
    """Create a mock member."""
    member = MagicMock(name=name)
    member.id = id
    return member


def _make_role(name: str = "ModRole", id: int = 222) -> MagicMock:
    """Create a mock role."""
    role = MagicMock(name=name)
    role.id = id
    return role


class TestBuildTicketOverwrites:
    """Characterization: build_ticket_overwrites with valid guild/author/mod."""

    def test_valid_guild_author_and_mod(self) -> None:
        """With author and mod_role, returns 4-principal overwrite dict."""
        guild = _make_guild()
        author = _make_member()
        mod = _make_role()
        overwrites = build_ticket_overwrites(guild, author, mod)
        # 4 principals: default_role, bot, author, mod
        assert len(overwrites) == 4
        assert guild.default_role in overwrites
        assert guild.me in overwrites
        assert author in overwrites
        assert mod in overwrites

    def test_default_role_denied_read(self) -> None:
        """Default role gets read_messages=False."""
        guild = _make_guild()
        overwrites = build_ticket_overwrites(guild, _make_member(), _make_role())
        perm = overwrites[guild.default_role]
        assert perm.read_messages is False

    def test_bot_gets_read_and_send(self) -> None:
        """Bot member gets read_messages=True, send_messages=True."""
        guild = _make_guild()
        overwrites = build_ticket_overwrites(guild, _make_member(), _make_role())
        perm = overwrites[guild.me]
        assert perm.read_messages is True
        assert perm.send_messages is True

    def test_author_gets_read_and_send(self) -> None:
        """Author gets read_messages=True, send_messages=True."""
        guild = _make_guild()
        author = _make_member()
        overwrites = build_ticket_overwrites(guild, author, _make_role())
        perm = overwrites[author]
        assert perm.read_messages is True
        assert perm.send_messages is True

    def test_mod_gets_read_and_send(self) -> None:
        """Mod role gets read_messages=True, send_messages=True."""
        guild = _make_guild()
        mod = _make_role()
        overwrites = build_ticket_overwrites(guild, _make_member(), mod)
        perm = overwrites[mod]
        assert perm.read_messages is True
        assert perm.send_messages is True

    def test_missing_author_returns_3_principals(self) -> None:
        """With author=None, returns 3 principals (no author entry)."""
        guild = _make_guild()
        overwrites = build_ticket_overwrites(guild, None, _make_role())
        assert len(overwrites) == 3
        assert guild.default_role in overwrites
        assert guild.me in overwrites

    def test_missing_mod_returns_3_principals(self) -> None:
        """With mod_role=None, returns 3 principals (no mod entry)."""
        guild = _make_guild()
        overwrites = build_ticket_overwrites(guild, _make_member(), None)
        assert len(overwrites) == 3
        assert guild.default_role in overwrites
        assert guild.me in overwrites

    def test_both_none_returns_2_principals(self) -> None:
        """With both None, returns 2 principals (default_role + bot)."""
        guild = _make_guild()
        overwrites = build_ticket_overwrites(guild, None, None)
        assert len(overwrites) == 2
        assert guild.default_role in overwrites
        assert guild.me in overwrites


# ===========================================================================
# resolve_mod_role — guild role resolution with fallback
# ===========================================================================


class TestResolveModRole:
    """Characterization: resolve_mod_role with valid/invalid/missing role."""

    def test_valid_role_id_found(self) -> None:
        """Valid int role_id that resolves → returns the role."""
        guild = MagicMock()
        expected_role = _make_role()
        guild.get_role.return_value = expected_role
        result = resolve_mod_role(guild, 123456)
        assert result is expected_role
        guild.get_role.assert_called_once_with(123456)

    def test_valid_string_role_id(self) -> None:
        """String digit role_id → converts to int and resolves."""
        guild = MagicMock()
        expected_role = _make_role()
        guild.get_role.return_value = expected_role
        result = resolve_mod_role(guild, "123456")
        assert result is expected_role
        guild.get_role.assert_called_once_with(123456)

    def test_invalid_id_returns_none(self) -> None:
        """Non-numeric role_id (e.g. 'abc') → returns None, no exception."""
        guild = MagicMock()
        result = resolve_mod_role(guild, "abc")
        assert result is None
        guild.get_role.assert_not_called()

    def test_none_id_returns_none(self) -> None:
        """None role_id → returns None."""
        guild = MagicMock()
        result = resolve_mod_role(guild, None)
        assert result is None

    def test_role_not_found_returns_none(self) -> None:
        """Valid ID but get_role returns None → returns None."""
        guild = MagicMock()
        guild.get_role.return_value = None
        result = resolve_mod_role(guild, 999)
        assert result is None


# ===========================================================================
# resolve_member_safe — guild member resolution with fallback
# ===========================================================================


class TestResolveMemberSafe:
    """Characterization: resolve_member_safe with valid/invalid/missing member."""

    def test_valid_member_found(self) -> None:
        """Valid int member_id that resolves → returns the member."""
        guild = MagicMock()
        expected = _make_member()
        guild.get_member.return_value = expected
        result = resolve_member_safe(guild, 42)
        assert result is expected
        guild.get_member.assert_called_once_with(42)

    def test_valid_string_member_id(self) -> None:
        """String digit member_id → converts to int and resolves."""
        guild = MagicMock()
        expected = _make_member()
        guild.get_member.return_value = expected
        result = resolve_member_safe(guild, "42")
        assert result is expected
        guild.get_member.assert_called_once_with(42)

    def test_invalid_id_returns_none(self) -> None:
        """Non-numeric member_id (e.g. 'abc') → returns None, no exception."""
        guild = MagicMock()
        result = resolve_member_safe(guild, "abc")
        assert result is None
        guild.get_member.assert_not_called()

    def test_none_id_returns_none(self) -> None:
        """None member_id → returns None."""
        guild = MagicMock()
        result = resolve_member_safe(guild, None)
        assert result is None

    def test_member_not_found_returns_none(self) -> None:
        """Valid ID but get_member returns None → returns None."""
        guild = MagicMock()
        guild.get_member.return_value = None
        result = resolve_member_safe(guild, 999)
        assert result is None


# ===========================================================================
# resolve_category_name — async DB category name resolution
# ===========================================================================


class TestResolveCategoryName:
    """Characterization: resolve_category_name with DB lookup."""

    @pytest.mark.asyncio
    async def test_valid_category_found(self) -> None:
        """Valid category_id with matching DB row → returns row name."""
        db = MagicMock()
        db.get_ticket_category = AsyncMock(return_value={"name": "Soporte", "color": 3447003})
        result = await resolve_category_name(db, "cat-uuid-123")
        assert result == "Soporte"
        db.get_ticket_category.assert_called_once_with("cat-uuid-123")

    @pytest.mark.asyncio
    async def test_missing_category_returns_fallback(self) -> None:
        """DB returns None → returns default fallback 'ticket'."""
        db = MagicMock()
        db.get_ticket_category = AsyncMock(return_value=None)
        result = await resolve_category_name(db, "nonexistent-uuid")
        assert result == "ticket"

    @pytest.mark.asyncio
    async def test_custom_fallback(self) -> None:
        """Custom fallback provided when DB returns None."""
        db = MagicMock()
        db.get_ticket_category = AsyncMock(return_value=None)
        result = await resolve_category_name(db, "nonexistent-uuid", fallback="default")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_none_category_id_returns_fallback(self) -> None:
        """None category_id → returns fallback without hitting DB."""
        db = MagicMock()
        db.get_ticket_category = AsyncMock()
        result = await resolve_category_name(db, None)
        assert result == "ticket"
        db.get_ticket_category.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_returns_fallback(self) -> None:
        """DB raises exception → returns fallback, no exception propagated."""
        db = MagicMock()
        db.get_ticket_category = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await resolve_category_name(db, "cat-uuid-123")
        assert result == "ticket"
