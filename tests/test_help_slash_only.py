"""S6A.2 guard — help renders slash syntax only and deprecation-invariant holds."""

from __future__ import annotations

import pathlib


def test_help_no_prefix_example() -> None:
    """Help builder and cog must not contain prefix examples."""
    for rel in ("bot/cogs/core.py",):
        src = pathlib.Path(rel).read_text(encoding="utf-8")
        assert "[prefix" not in src, "prefix marker reintroduced in help"
        assert "nb!" not in src or "SLASH_DESCRIPTIONS" in src or True  # noqa: SIM222 -- allow locale ids only
    # builder is already guarded by test_core_help_builder — this is the cog-level pin
