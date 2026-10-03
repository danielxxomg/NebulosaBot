"""Structural tests for docs/runbooks/reset-procedure.md.

Asserts the existence of the runbook, no-execution disclaimer, the three distinct
phases (Phase 1 inventory, Phase 2 approval gate, Phase 3 fresh-guild verification),
and specific operational gotchas.
"""

from __future__ import annotations

from pathlib import Path

RUNBOOK_PATH = Path("docs/runbooks/reset-procedure.md")


class TestResetProcedureDoc:
    """Validate structure and required sections in reset procedure runbook."""

    def test_runbook_file_exists(self) -> None:
        """Runbook markdown file must exist at expected path."""
        assert RUNBOOK_PATH.is_file(), f"Runbook {RUNBOOK_PATH} does not exist"

    def test_contains_no_execution_disclaimer(self) -> None:
        """Runbook must clearly state that procedures/queries are for documentation only."""
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "DISCLAIMER" in content
        assert "DO NOT EXECUTE" in content or "no-execution" in content.lower()

    def test_contains_three_phases(self) -> None:
        """Runbook must contain Phase 1, Phase 2, and Phase 3 headings."""
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "Phase 1" in content
        assert "Phase 2" in content
        assert "Phase 3" in content

    def test_contains_human_approval_gate(self) -> None:
        """Phase 2 must define an explicit human approval gate and checklist."""
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "Approval Gate" in content or "approval gate" in content
        assert "Checklist" in content or "checklist" in content
        assert "Guild ID" in content
        assert "Panel" in content

    def test_phase_3_covers_fresh_guild_and_dashboard_consequences(self) -> None:
        """Phase 3 must cover ensure_guild_exists, active=true, and dashboard 404 consequence."""
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "ensure_guild_exists" in content
        assert "active = true" in content or "active=true" in content
        assert "404" in content
        assert "on_ready" in content

    def test_states_exact_tables_decision_is_open(self) -> None:
        """Runbook must explicitly state that the exact candidate tables list is still open."""
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "STILL OPEN" in content or "still open" in content.lower()
