"""RED tests for neon brand tokens (PR1 task 1.1).

Asserts ``brand.ACCENT_A`` / ``brand.ACCENT_B`` neon palette, ``ACCENT``
unchanged, and ``GREETING_ACCENT`` stays an alias of ``ACCENT``.

S4 (cycle-5-quality-zero) adds the shared surface palette: legacy blurple
forms and transcript CSS tokens consolidated into ``bot/utils/brand.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bot.utils import brand

BOT_ROOT = Path(__file__).resolve().parent.parent / "bot"
_HEX_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,6}\b")


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


class TestLegacyBlurpleForms:
    """S4 — legacy blurple lives once in brand, in every consumed form."""

    def test_canonical_int_form(self) -> None:
        assert brand.LEGACY_BLURPLE == 0x7289DA

    def test_css_string_form(self) -> None:
        assert brand.LEGACY_BLURPLE_CSS == "#7289da"

    def test_rgba_tuple_form(self) -> None:
        assert brand.LEGACY_BLURPLE_RGBA == (114, 137, 218, 255)

    def test_forms_agree(self) -> None:
        r, g, b, _a = brand.LEGACY_BLURPLE_RGBA
        assert (r << 16) | (g << 8) | b == brand.LEGACY_BLURPLE
        assert f"#{brand.LEGACY_BLURPLE:06x}" == brand.LEGACY_BLURPLE_CSS


class TestTranscriptSurfaceTokens:
    """S4.7 — transcript CSS palette tokenized; values byte-identical to pre-consolidation CSS."""

    @pytest.mark.parametrize(
        ("token", "value"),
        [
            ("TRANSCRIPT_BG", "#36393f"),
            ("TRANSCRIPT_HOVER", "#32353b"),
            ("TRANSCRIPT_AUTHOR", "#7289da"),
            ("TRANSCRIPT_MUTED", "#72767d"),
            ("TRANSCRIPT_BORDER", "#42464d"),
            ("TRANSCRIPT_TEXT", "#dcddde"),
            ("TRANSCRIPT_HEADER_TEXT", "#fff"),
        ],
    )
    def test_token_value(self, token: str, value: str) -> None:
        assert getattr(brand, token) == value

    def test_author_token_is_legacy_blurple(self) -> None:
        """The author color is exactly the legacy blurple, single-sourced."""
        assert brand.TRANSCRIPT_AUTHOR == brand.LEGACY_BLURPLE_CSS

    def test_no_hex_literals_in_transcript_service(self) -> None:
        """transcript_service.py must not carry raw hex colors outside brand.py."""
        src = (BOT_ROOT / "services" / "transcript_service.py").read_text(encoding="utf-8")
        offenders = [m.group(0) for m in _HEX_LITERAL_RE.finditer(src)]
        assert not offenders, f"hex literals must live in bot/utils/brand.py: {offenders}"
