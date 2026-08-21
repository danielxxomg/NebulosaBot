"""RED test: no neon hex literals outside brand.py (PR1 task 1.2).

The PR1 contract is that the neon palette values (``#FF2E97`` magenta /
``#00E5FF`` cyan) live ONLY in ``bot/utils/brand.py`` as ``ACCENT_A`` /
``ACCENT_B``. No production module under ``bot/`` may hard-code those hex
literals; they must read the tokens from ``brand``.

Note: ``bot/`` has pre-existing hex in ``shared_assets.py`` comments
(``#2b2d31`` background gradient) and ``transcript_service.py`` CSS — those
are NOT neon palette values and are pre-existing tech-debt outside the PR1
diff. This test guards the neon-specific invariant PR1 introduces.
"""

from __future__ import annotations

import re
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent.parent / "bot"
BRAND_PATH = BOT_DIR / "utils" / "brand.py"

NEON_HEX_PATTERN = re.compile(r"#(FF2E97|00E5FF)", re.IGNORECASE)


def _production_py_files() -> list[Path]:
    """All .py under bot/ except brand.py (the single source of truth)."""
    return [p for p in sorted(BOT_DIR.rglob("*.py")) if p != BRAND_PATH]


class TestNoNeonHexOutsideBrand:
    """1.2 — the neon palette hex values live only in brand.py."""

    def test_no_neon_hex_literal_outside_brand(self) -> None:
        offenders: list[str] = []
        for py_file in _production_py_files():
            text = py_file.read_text(encoding="utf-8")
            for match in NEON_HEX_PATTERN.finditer(text):
                offenders.append(f"{py_file.relative_to(BOT_DIR.parent)}: {match.group(0)}")
        assert not offenders, (
            f"neon hex literals found outside brand.py — must use brand.ACCENT_A/ACCENT_B:\n{offenders}"
        )

    def test_brand_contains_neon_hex_as_tokens(self) -> None:
        """brand.py MUST define the neon values as ACCENT_A / ACCENT_B."""
        text = BRAND_PATH.read_text(encoding="utf-8")
        assert "ACCENT_A" in text
        assert "ACCENT_B" in text
        assert "0xFF2E97" in text
        assert "0x00E5FF" in text
