"""Unit tests for bot.utils.brand — brand color tokens.

Verifies that brand.py exports the 6 required color constants
with the correct hex values from the purple/violet palette.
"""

from __future__ import annotations

import importlib


class TestBrandModuleExports:
    """Verify brand.py exports all 6 color constants."""

    def test_brand_module_importable(self) -> None:
        """bot.utils.brand must be importable."""
        mod = importlib.import_module("bot.utils.brand")
        assert mod is not None

    def test_exports_primary(self) -> None:
        """brand.py must export PRIMARY (#9B5DE5)."""
        from bot.utils.brand import PRIMARY
        assert PRIMARY == 0x9B5DE5

    def test_exports_accent(self) -> None:
        """brand.py must export ACCENT (#A855F7)."""
        from bot.utils.brand import ACCENT
        assert ACCENT == 0xA855F7

    def test_exports_success(self) -> None:
        """brand.py must export SUCCESS (#10B981)."""
        from bot.utils.brand import SUCCESS
        assert SUCCESS == 0x10B981

    def test_exports_warning(self) -> None:
        """brand.py must export WARNING (#F59E0B)."""
        from bot.utils.brand import WARNING
        assert WARNING == 0xF59E0B

    def test_exports_error(self) -> None:
        """brand.py must export ERROR (#EF4444)."""
        from bot.utils.brand import ERROR
        assert ERROR == 0xEF4444

    def test_exports_info(self) -> None:
        """brand.py must export INFO (#8B5CF6)."""
        from bot.utils.brand import INFO
        assert INFO == 0x8B5CF6

    def test_all_six_tokens_present(self) -> None:
        """brand.py __all__ or dir() must contain all 6 tokens."""
        from bot.utils import brand
        tokens = {"PRIMARY", "ACCENT", "SUCCESS", "WARNING", "ERROR", "INFO"}
        for token in tokens:
            assert hasattr(brand, token), f"Missing token: {token}"
            assert isinstance(getattr(brand, token), int), f"{token} must be int"
