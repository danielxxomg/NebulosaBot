"""RED governance tests for the product-artifact-audit change (task 0.2).

Proves the lifecycle guard: a change folder MUST NOT be archived or claimed
complete before it carries verification evidence (``verify-report.md``), even
when every task box is checked. The guard lives in the non-production
``governance_guard`` module so SDD archive tooling and reviewers can reuse it.
"""

from __future__ import annotations

from pathlib import Path

from governance_guard import archive_claim_allowed, verify_evidence_present

# A tasks file that claims every box checked (mirrors the historical
# reconciliation change that claimed full completion without verification).
_FULLY_CHECKED_TASKS = """\
# Tasks: Example Change

- [x] 1.1 RED contract test
- [x] 1.2 GREEN implementation
- [x] 2.1 RED sweep test
- [x] 2.2 GREEN sweep wiring
"""

# A tasks file with unfinished work.
_PARTIAL_TASKS = """\
# Tasks: Example Change

- [x] 1.1 RED contract test
- [ ] 1.2 GREEN implementation
"""


def test_verify_evidence_present_requires_file(tmp_path: Path) -> None:
    """A change folder without verify-report.md MUST report missing evidence."""
    change_dir = tmp_path / "example-change"
    change_dir.mkdir()
    (change_dir / "tasks.md").write_text(_FULLY_CHECKED_TASKS, encoding="utf-8")

    assert verify_evidence_present(change_dir) is False

    (change_dir / "verify-report.md").write_text("# Verify", encoding="utf-8")
    assert verify_evidence_present(change_dir) is True


def test_archive_claim_blocked_when_evidence_missing(tmp_path: Path) -> None:
    """All boxes checked WITHOUT verify-report.md MUST block the archive claim."""
    change_dir = tmp_path / "example-change"
    change_dir.mkdir()
    (change_dir / "tasks.md").write_text(_FULLY_CHECKED_TASKS, encoding="utf-8")

    allowed, reason = archive_claim_allowed(change_dir, tasks_checked=4, tasks_total=4)

    assert allowed is False
    assert "verify-report.md" in reason


def test_archive_claim_blocked_when_tasks_incomplete(tmp_path: Path) -> None:
    """Unchecked task boxes MUST block the archive claim even with evidence."""
    change_dir = tmp_path / "example-change"
    change_dir.mkdir()
    (change_dir / "tasks.md").write_text(_PARTIAL_TASKS, encoding="utf-8")
    (change_dir / "verify-report.md").write_text("# Verify", encoding="utf-8")

    allowed, reason = archive_claim_allowed(change_dir, tasks_checked=1, tasks_total=2)

    assert allowed is False
    assert "unchecked" in reason


def test_archive_claim_allowed_with_evidence_and_all_checked(tmp_path: Path) -> None:
    """Fully checked tasks WITH verify-report.md MAY proceed."""
    change_dir = tmp_path / "example-change"
    change_dir.mkdir()
    (change_dir / "tasks.md").write_text(_FULLY_CHECKED_TASKS, encoding="utf-8")
    (change_dir / "verify-report.md").write_text("# Verify", encoding="utf-8")

    allowed, reason = archive_claim_allowed(change_dir, tasks_checked=4, tasks_total=4)

    assert allowed is True
    assert reason == ""


def test_archive_claim_rejects_missing_change_folder(tmp_path: Path) -> None:
    """A missing change folder MUST be reported, never silently allowed."""
    missing = tmp_path / "does-not-exist"

    allowed, reason = archive_claim_allowed(missing, tasks_checked=0, tasks_total=0)

    assert allowed is False
    assert "not found" in reason


def test_build_tasks_boxes_counts_only_task_lines() -> None:
    """Only task-box lines are counted; prose and headers are ignored."""
    body = """\
# Tasks: Example

## Checklist

- [x] 1.1 RED test
- [x] 1.2 GREEN implementation
Some prose sentence that is not a task box.
- [ ] 2.1 RED sweep test
"""
    from governance_guard import build_tasks_boxes

    checked, total = build_tasks_boxes(body)

    assert checked == 2
    assert total == 3
