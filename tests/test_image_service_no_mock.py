"""Structural guard — image_service.py MUST NOT embed MagicMock introspection.

GGA C Round 4 blocker 1: ``generate_greeting_card`` imported
``unittest.mock.MagicMock`` in production and branched on
``isinstance(cls_fetch, MagicMock)`` to honor legacy tests that patched
``ImageService._fetch_avatar``.  That made production code aware of test
mechanics and mutated ``shared_assets`` module globals for the call duration
(thread-unsafe).  AGENTS.md mandates async-safe, no blocking patterns, and
mock-specific branching belongs in tests, not production.

This guard proves the shim no longer carries that policy:
    - NO ``unittest.mock`` import in image_service.py.
    - NO ``_mock_children`` / ``isinstance(... MagicMock ...)`` sniffing.

Legacy tests that need to stub avatar fetching now patch
``bot.services.shared_assets._fetch_avatar`` directly (the real call target).
"""

from __future__ import annotations

from pathlib import Path

_SERVICE_PATH = Path(__file__).resolve().parent.parent / "bot" / "services" / "image_service.py"


def _service_source() -> str:
    if not _SERVICE_PATH.exists():
        return ""
    return _SERVICE_PATH.read_text(encoding="utf-8")


class TestImageServiceNoMockSniffing:
    """The greeting-card shim must not carry MagicMock introspection."""

    def test_no_unittest_mock_import_in_service(self) -> None:
        src = _service_source()
        assert src, "bot/services/image_service.py not found"
        assert "unittest.mock" not in src, (
            "bot/services/image_service.py must not import unittest.mock — "
            "mock sniffing is a test concern and must not leak into the "
            "production rendering path."
        )

    def test_no_mock_children_introspection_in_service(self) -> None:
        src = _service_source()
        assert src, "bot/services/image_service.py not found"
        assert "_mock_children" not in src, (
            "bot/services/image_service.py must not introspect MagicMock "
            "children — mock-specific branching is a test concern, not "
            "production policy."
        )

    def test_no_isinstance_magickmock_sniffing_in_service(self) -> None:
        src = _service_source()
        assert src, "bot/services/image_service.py not found"
        assert "isinstance" not in src or "MagicMock" not in src, (
            "bot/services/image_service.py must not branch on "
            "``isinstance(..., MagicMock)`` — production code must not be "
            "aware of test doubles."
        )
