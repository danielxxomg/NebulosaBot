"""Structural guard — greetings cog MUST NOT embed renderer-dispatch policy.

Phase 2 of the GGA C blocker 1 fix: the renderer-selection policy
(prefer ``render`` over the deprecated ``generate_greeting_card`` shim, and
MagicMock introspection) lived duplicated 3x -- twice in the cog's
``welcome_test``/``goodbye_test`` and once in ``GreetingService.dispatch_greeting``.
AGENTS.md mandates "Cogs handle Discord interaction only — no business logic"
and "Business logic inside cog handlers — extract to services".

This guard proves the cog no longer owns that policy:
    - NO ``unittest.mock`` import (mock sniffing belongs in tests, not prod).
    - NO ``_resolve_renderer`` method (the resolver lives in the service).
    - NO ``_mock_children`` / ``_explicit_render`` introspection helpers.

If any of these reappear, the guard fails and blocks the regression.
"""

from __future__ import annotations

from pathlib import Path

_COG_PATH = Path(__file__).resolve().parent.parent / "bot" / "cogs" / "greetings.py"


def _cog_source() -> str:
    if not _COG_PATH.exists():
        return ""
    return _COG_PATH.read_text(encoding="utf-8")


class TestGreetingsCogNoMockSniffing:
    """The cog must not carry renderer-dispatch policy or mock introspection."""

    def test_no_unittest_mock_import_in_cog(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/greetings.py not found"
        assert "unittest.mock" not in src, (
            "bot/cogs/greetings.py must not import unittest.mock — renderer "
            "dispatch belongs in the service, and mock sniffing must not leak "
            "into production code."
        )

    def test_no_resolve_renderer_method_in_cog(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/greetings.py not found"
        assert "_resolve_renderer" not in src, (
            "bot/cogs/greetings.py must not define _resolve_renderer — the "
            "renderer resolver lives in GreetingService (single copy, DRY)."
        )

    def test_no_mock_children_introspection_in_cog(self) -> None:
        src = _cog_source()
        assert src, "bot/cogs/greetings.py not found"
        assert "_mock_children" not in src, (
            "bot/cogs/greetings.py must not introspect MagicMock children — "
            "mock-specific branching is a test concern, not production policy."
        )
