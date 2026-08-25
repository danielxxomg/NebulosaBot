"""Unit tests for bot.utils.brand — brand color tokens.

Verifies that brand.py exports the 6 required color constants
with the correct hex values from the purple/violet palette.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from bot.utils import brand

# Palette matrix: every exported token with its pinned hex value.
_TOKEN_MATRIX = [
    pytest.param("PRIMARY", 0x9B5DE5, id="primary"),
    pytest.param("ACCENT", 0xA855F7, id="accent"),
    pytest.param("SUCCESS", 0x10B981, id="success"),
    pytest.param("WARNING", 0xF59E0B, id="warning"),
    pytest.param("ERROR", 0xEF4444, id="error"),
    pytest.param("INFO", 0x8B5CF6, id="info"),
]


class TestBrandModuleExports:
    """Verify brand.py exports all 6 color constants."""

    def test_brand_module_importable(self) -> None:
        """bot.utils.brand must be importable."""
        mod = importlib.import_module("bot.utils.brand")
        assert mod is not None

    @pytest.mark.parametrize(("token", "expected"), _TOKEN_MATRIX)
    def test_export_value(self, token: str, expected: int) -> None:
        """brand.py must export the token pinned to its palette value."""
        value = getattr(brand, token)
        assert value == expected, f"{token} must be {expected:#x}"
        assert isinstance(value, int), f"{token} must be int"


class TestNoHardcodedHexColors:
    """No production module under bot/ may use hardcoded hex color literals."""

    def test_no_hardcoded_hex_in_embed_colors(self) -> None:
        """Scan bot/**/*.py (excluding brand.py) for hex color literals in embed color assignments.

        Spec (brand-tokens/spec.md — no hardcoded hex scenario): "THEN zero
        matches are found in embed color assignments."
        """
        bot_dir = Path(__file__).resolve().parent.parent / "bot"
        hex_pattern = re.compile(r"0x[0-9A-Fa-f]{6}\b")
        violations: list[str] = []

        for py_file in sorted(bot_dir.rglob("*.py")):
            if py_file.name == "brand.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                # Only flag lines that look like color assignments
                if "color" in line.lower() and hex_pattern.search(line):
                    violations.append(f"{py_file.relative_to(bot_dir.parent)}:{lineno}: {line.strip()}")

        assert not violations, "Hardcoded hex colors found in production code:\n" + "\n".join(violations)
