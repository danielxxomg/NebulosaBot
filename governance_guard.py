"""Non-production SDD governance guard helpers.

Enforces the lifecycle rule that an OpenSpec change folder MUST NOT be
archived or claimed complete before it carries verified evidence
(``verify-report.md``), even when every task box is checked. Pure
filesystem tooling — no Supabase, Discord, or git mutation.
"""

from __future__ import annotations

from pathlib import Path

# Path where archived SDD changes live.
ARCHIVE_DIR = Path("openspec") / "changes" / "archive"

# Verification evidence file that MUST exist before an archive claim.
VERIFY_REPORT_FILENAME = "verify-report.md"


def _resolve_change_dir(change_dir: Path | str | None) -> Path:
    """Resolve a change folder name/path under ``openspec/changes``."""
    if change_dir is None:
        return Path("openspec") / "changes" / "product-artifact-audit"
    path = Path(change_dir)
    return path if path.is_absolute() else Path("openspec") / "changes" / path


def verify_evidence_present(change_dir: Path | str | None = None) -> bool:
    """Return whether the change folder carries its verification report.

    Both the active location and the archived location are considered so a
    claim can be validated before and after the folder move.
    """
    resolved = _resolve_change_dir(change_dir)
    return any((candidate / VERIFY_REPORT_FILENAME).is_file() for candidate in (resolved, ARCHIVE_DIR / resolved.name))


def archive_claim_allowed(
    change_dir: Path | str | None = None,
    *,
    tasks_checked: int = 0,
    tasks_total: int = 0,
) -> tuple[bool, str]:
    """Return whether an archive/completion claim may proceed for a change.

    The claim is allowed only when the change folder exists, every task box
    is checked, and the folder carries its verification report. Any missing
    gate returns ``(False, reason)`` with a non-empty explanation.

    Args:
        change_dir: Change folder name, relative path, or absolute path.
        tasks_checked: Number of completed task boxes in the tasks file.
        tasks_total: Total number of task boxes in the tasks file.

    Returns:
        ``(allowed, reason)``; *reason* is empty when allowed.
    """
    resolved = _resolve_change_dir(change_dir)
    if not resolved.is_dir():
        return False, f"change folder not found: {resolved.name}"

    incomplete = tasks_total - tasks_checked
    if incomplete > 0:
        return False, f"{incomplete} task(s) still unchecked in {resolved.name}/tasks.md"

    if not verify_evidence_present(resolved):
        return False, f"missing {VERIFY_REPORT_FILENAME} in {resolved.name}/"

    return True, ""


def build_tasks_boxes(tasks_md: str) -> tuple[int, int]:
    """Count checked and total task boxes in a tasks-file body.

    A task box is a line whose leading whitespace is followed by ``- [ ]`` or
    ``- [x]``. Non-task prose (headings, labels such as "Checklist") is not
    counted.
    """
    checked = 0
    total = 0
    for line in tasks_md.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("- [") or "] " not in stripped:
            continue
        total += 1
        if stripped.startswith("- [x]"):
            checked += 1
    return checked, total


__all__ = [
    "ARCHIVE_DIR",
    "VERIFY_REPORT_FILENAME",
    "archive_claim_allowed",
    "build_tasks_boxes",
    "verify_evidence_present",
]
