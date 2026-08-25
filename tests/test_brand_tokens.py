"""RED tests for neon brand tokens (PR1 task 1.1).

Asserts ``brand.ACCENT_A`` / ``brand.ACCENT_B`` neon palette, ``ACCENT``
unchanged, and ``GREETING_ACCENT`` stays an alias of ``ACCENT``.

S4 (cycle-5-quality-zero) adds the shared surface palette: legacy blurple
forms and transcript CSS tokens consolidated into ``bot/utils/brand.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeAlias
from unittest.mock import MagicMock

import pytest

from bot.cogs.core import _build_cog_help_embed
from bot.core.i18n import load_locales
from bot.services import greeting_renderer, rank_renderer, shared_assets
from bot.utils import brand

BOT_ROOT = Path(__file__).resolve().parent.parent / "bot"
_HEX_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,6}\b")


BrandTokenValue: TypeAlias = int | str | tuple[int, int, int, int]


class TestBrandTokenExports:
    """PR1 1.1 + S4 — every pinned brand export lives in one matrix.

    Neon palette (PR1), the GREETING_ACCENT alias (must equal ACCENT — no
    standalone constant), and all three legacy-blurple forms (S4) are
    value-pinned in a single parametrized token list.
    """

    @pytest.mark.parametrize(
        ("token", "value"),
        [
            ("ACCENT", 0xA855F7),
            ("ACCENT_A", 0xFF2E97),
            ("ACCENT_B", 0x00E5FF),
            # Alias of ACCENT — pinned to the same literal so a standalone
            # constant drift fails this case.
            ("GREETING_ACCENT", 0xA855F7),
            ("LEGACY_BLURPLE", 0x7289DA),
            ("LEGACY_BLURPLE_CSS", "#7289da"),
            ("LEGACY_BLURPLE_RGBA", (114, 137, 218, 255)),
        ],
    )
    def test_token_value(self, token: str, value: BrandTokenValue) -> None:
        assert getattr(brand, token) == value

    def test_neon_tokens_are_int(self) -> None:
        assert isinstance(brand.ACCENT_A, int)
        assert isinstance(brand.ACCENT_B, int)

    def test_legacy_blurple_forms_agree(self) -> None:
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


class TestRendererPaletteTokens:
    """S4.7 — renderer RGBA palette single-sourced in brand (byte-identical values)."""

    @pytest.mark.parametrize(
        ("token", "value"),
        [
            ("CARD_BG_TOP", (43, 45, 49, 255)),
            ("CARD_BG_BOTTOM", (30, 31, 34, 255)),
            ("PLACEHOLDER", (74, 78, 91, 255)),
            ("PLACEHOLDER_INNER", (56, 59, 68, 255)),
            ("PANEL_OVERLAY", (255, 255, 255, 18)),
            ("MUTED_TEXT", (185, 187, 190, 255)),
        ],
    )
    def test_token_value(self, token: str, value: tuple[int, int, int, int]) -> None:
        assert getattr(brand, token) == value

    def test_shared_assets_reuses_card_tokens(self) -> None:
        assert shared_assets.BG_TOP == brand.CARD_BG_TOP
        assert shared_assets.BG_BOTTOM == brand.CARD_BG_BOTTOM
        assert shared_assets.GREETING_PLACEHOLDER == brand.PLACEHOLDER
        assert shared_assets.GREETING_PLACEHOLDER_INNER == brand.PLACEHOLDER_INNER

    def test_rank_renderer_uses_shared_tokens(self) -> None:
        assert rank_renderer.LEVEL_COLOR == brand.LEGACY_BLURPLE_RGBA
        assert rank_renderer.XP_BAR_FILL == brand.LEGACY_BLURPLE_RGBA
        # Dedupe: XP text color == greeting count color == MUTED_TEXT.
        assert rank_renderer.XP_TEXT_COLOR == brand.MUTED_TEXT

    def test_greeting_renderer_count_color_dedupes_into_muted_text(self) -> None:
        assert greeting_renderer._GREETING_COUNT_COLOR == brand.MUTED_TEXT
        assert greeting_renderer._GREETING_PANEL == brand.PANEL_OVERLAY


class TestImgurFooterDropped:
    """S4.7 — the dead i.imgur.com footer icon URL is gone from CoreCog."""

    def test_no_imgur_url_in_bot_source(self) -> None:
        offenders = []
        for py_file in sorted(BOT_ROOT.rglob("*.py")):
            if "i.imgur.com" in py_file.read_text(encoding="utf-8"):
                offenders.append(str(py_file.relative_to(BOT_ROOT.parent)))
        assert not offenders, f"imgur footer URLs must be dropped: {offenders}"

    def test_help_cog_embed_footer_has_no_icon(self) -> None:
        load_locales(Path("bot/locales"))

        cmd = MagicMock()
        cmd.name = "ping"
        cmd.qualified_name = "ping"
        cmd.description = "latency"
        cmd.hidden = False

        mock_bot = MagicMock()
        mock_bot.get_cog.return_value.get_commands.return_value = [cmd]
        embed = _build_cog_help_embed(mock_bot, "Core", guild_id=123456789)
        assert embed is not None
        assert not embed.footer.icon_url, "footer must not carry an icon URL"
