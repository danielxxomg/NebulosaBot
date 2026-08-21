"""RED tests for neon brand tokens (PR1 task 1.1).

Asserts ``brand.ACCENT_A`` / ``brand.ACCENT_B`` neon palette, ``ACCENT``
unchanged, and ``GREETING_ACCENT`` stays an alias of ``ACCENT``.
"""

from __future__ import annotations

from bot.utils import brand


class TestNeonBrandTokens:
    """PR1 1.1 — neon palette tokens present with binding hex values."""

    def test_accent_a_is_magenta(self) -> None:
        assert brand.ACCENT_A == 0xFF2E97

    def test_accent_b_is_cyan(self) -> None:
        assert brand.ACCENT_B == 0x00E5FF

    def test_accent_unchanged(self) -> None:
        assert brand.ACCENT == 0xA855F7

    def test_greeting_accent_is_alias_of_accent(self) -> None:
        """GREETING_ACCENT must stay == ACCENT (no standalone constant)."""
        assert brand.GREETING_ACCENT == brand.ACCENT

    def test_neon_tokens_are_int(self) -> None:
        assert isinstance(brand.ACCENT_A, int)
        assert isinstance(brand.ACCENT_B, int)
