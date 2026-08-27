"""S6A.1 guard — zero hybrid declarations remain in S6A-touched archetypes."""

from __future__ import annotations

import pathlib

S6A_FILES = [
    "bot/cogs/core.py",
    "bot/cogs/sentinel.py",
    "bot/cogs/utility.py",
    "bot/cogs/tickets.py",
    "bot/cogs/ticket_admin_flow.py",
    "bot/cogs/ticket_integrity_flow.py",
    "bot/cogs/ticket_lifecycle_flow.py",
    "bot/cogs/ticket_notes_flow.py",
]


def test_zero_hybrid_in_s6a_archetypes() -> None:
    """S6A scope: none of the migrated archetypes may declare hybrid commands."""
    offenders: list[str] = []
    for rel in S6A_FILES:
        src = pathlib.Path(rel).read_text(encoding="utf-8")
        if "hybrid_command" in src or "hybrid_group" in src:
            offenders.append(rel)
    assert offenders == [], f"hybrid declarations remain in S6A archetypes: {offenders}"
