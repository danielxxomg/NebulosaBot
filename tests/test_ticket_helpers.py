"""Unit tests for bot.utils.ticket_helpers.sanitize_channel_name.

Covers:
    - Standard channel name generation
    - Unicode NFKD ASCII folding (accents, non-latin)
    - Whitespace → hyphen conversion
    - Non-[a-z0-9-] character stripping
    - Hyphen collapsing and stripping
    - Empty/blank input fallbacks
    - Long name truncation preserving -{number:04d} suffix
    - Edge cases: all-special chars, single char, max length boundary
"""

from __future__ import annotations

import pytest

from bot.utils.ticket_helpers import sanitize_channel_name


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
