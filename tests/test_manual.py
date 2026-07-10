"""Integration tests for docs/MANUAL.md content.

Validates that the Spanish manual covers all required ticket UX behaviors
mandated by the ticket-ux-branding delta spec (docs-manual/spec.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

MANUAL = Path(__file__).resolve().parent.parent / "docs" / "MANUAL.md"


@pytest.fixture(scope="module")
def manual_text() -> str:
    """Read the MANUAL.md content once for all tests in this module."""
    assert MANUAL.exists(), f"Manual not found at {MANUAL}"
    return MANUAL.read_text(encoding="utf-8")


def test_manual_exists_and_non_empty(manual_text: str) -> None:
    """Manual MUST exist and be non-empty."""
    assert len(manual_text) > 0


def test_manual_has_close_confirmation_section(manual_text: str) -> None:
    """Manual MUST describe the close confirmation dialog behavior."""
    lower = manual_text.lower()
    # Must mention confirm/cancel dialog or ephemeral confirmation.
    assert any(
        phrase in lower
        for phrase in [
            "confirmar", "cancelar", "diálogo de confirmación",
            "confirm", "cancel",
        ]
    ), "Missing close confirmation dialog documentation"


def test_manual_has_countdown_documentation(manual_text: str) -> None:
    """Manual MUST describe the countdown behavior (5→1, single message edit)."""
    # Must mention countdown or the 5→1 sequence.
    assert any(
        phrase in manual_text.lower()
        for phrase in [
            "countdown", "cuenta regresiva", "5 a 1", "5→1",
            "5 a 1", "edita",
        ]
    ), "Missing countdown documentation"


def test_manual_has_unclaim_command(manual_text: str) -> None:
    """Manual MUST document /unclaim with claimer-or-mods permissions."""
    lower = manual_text.lower()
    assert "unclaim" in lower, "Missing /unclaim documentation"


def test_manual_has_claim_transfer(manual_text: str) -> None:
    """Manual MUST describe claim-on-claimed transfer confirmation flow."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "transferir", "transfer", "ya reclamado", "already claimed",
            "confirmación de transferencia", "transfer confirm",
        ]
    ), "Missing claim-on-claimed transfer documentation"


def test_manual_has_channel_naming_format(manual_text: str) -> None:
    """Manual MUST describe the {category}-{username}-{number} naming format."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "{category}-{username}-{number}", "categoría-usuario-número",
            "category-username-number", "formato del canal",
            "channel naming", "nomenclatura",
        ]
    ), "Missing channel naming format documentation"


def test_manual_has_branding_notes(manual_text: str) -> None:
    """Manual MUST mention brand palette or bot avatar footer as behavior notes."""
    lower = manual_text.lower()
    assert any(
        phrase in lower
        for phrase in [
            "púrpura", "violeta", "purple", "violet", "brand",
            "avatar del bot", "bot avatar", "paleta", "palette",
        ]
    ), "Missing branding notes"
