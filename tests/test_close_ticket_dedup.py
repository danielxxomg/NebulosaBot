"""Dedup guard — close_ticket dual-branch must delegate to _finalize_close (S5.6).

The two branches (guild-scoped fast path vs pre-read fallback) previously
duplicated post-transition logic (denied/success audit, zombie-aware channel
discard skip, _clear_scheduled_fields). RED: this test fails until the dedup
lands — it probes that _finalize_close exists and that both paths share it
without duplicating the audit body.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "bot" / "services" / "ticket_lifecycle_service.py"


def _has_finalize() -> bool:
    src = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_finalize_close":
            return True
        if isinstance(node, ast.FunctionDef) and node.name == "_finalize_close":
            return True
    return False


def _close_ticket_src() -> str:
    src = SERVICE_PATH.read_text(encoding="utf-8")
    start = src.find("async def close_ticket")
    assert start != -1, "close_ticket method must exist"
    end = src.find("\n    async def ", start + 1)
    if end == -1:
        end = start + 8000
    return src[start:end]


def test_finalize_close_exists() -> None:
    """RED until S5.6 lands: _finalize_close must exist."""
    assert _has_finalize(), "TicketLifecycleService._finalize_close(...) not found — S5.6 dedup not yet extracted"


def test_close_ticket_delegates_to_finalize() -> None:
    """Both branches must call _finalize_close instead of inlining audit logic.

    Ensures the fast-path and fallback do not duplicate the full audit/skip/clear body.
    """
    src = _close_ticket_src()
    # must reference _finalize_close at least twice (two branches) or once via shared path
    assert "_finalize_close" in src, "close_ticket must delegate to _finalize_close"
    # The old duplicated strings should appear only inside _finalize_close, not twice in close_ticket
    # Count audit insert occurrences inside close_ticket window
    # After dedup, close_ticket should contain at most 1 insert_audit_row occurrence (denied path)
    # Success/zombie paths live in _finalize_close
    # We assert the duplicated success audit string appears <=1 time in close_ticket body
    # Count denied audit rows — after dedup there should be at most 2 (one per branch)
    denied_hits = src.count('"denied"')
    # Success/close audit rows should have been moved to _finalize_close, so at most 0 remain in close_ticket
    # Count success inserts via '"success"' after denied split — approximate
    success_in_close = src.count('"success"')
    assert success_in_close == 0, (
        f"close_ticket still inlines success audits ({success_in_close} hits) — must live only in _finalize_close"
    )
    assert denied_hits <= 2, f"close_ticket denied audits duplicated beyond branches ({denied_hits} hits)"


def test_finalize_hosts_zombie_and_clear() -> None:
    """_finalize_close must host zombie-aware skip and _clear_scheduled_fields."""
    src = SERVICE_PATH.read_text(encoding="utf-8")
    idx = src.find("def _finalize_close")
    assert idx != -1, "_finalize_close not found"
    block = src[idx : idx + 6000]
    assert "zombie" in block.lower(), "_finalize_close must handle zombie-aware skip"
    assert "_clear_scheduled_fields" in block or "clear_scheduled" in block.lower(), (
        "_finalize_close must call _clear_scheduled_fields"
    )
