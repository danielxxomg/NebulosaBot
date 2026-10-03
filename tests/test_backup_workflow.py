"""Structural tests for .github/workflows/backup.yml.

Asserts weekly cron schedule, 30-day retention, preflight step before pg_dump,
encryption requirement, single reference to BACKUP_ENCRYPTION_KEY, and absence
of secret leakage in shell commands.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(".github/workflows/backup.yml")


def _load_workflow() -> dict[str, Any]:
    assert WORKFLOW_PATH.exists(), f"Workflow file {WORKFLOW_PATH} does not exist"
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content)
    assert isinstance(loaded, dict)
    return loaded


class TestBackupWorkflowStructure:
    """Validate structure and security posture of backup.yml workflow."""

    def test_workflow_file_exists(self) -> None:
        """Workflow file must exist at expected path."""
        assert WORKFLOW_PATH.is_file()

    def test_weekly_cron_schedule(self) -> None:
        """Schedule trigger must be configured for weekly run."""
        data = _load_workflow()
        on_candidate = data.get("on") or data.get(True)  # type: ignore[call-overload]
        on_block: dict[str, Any] = on_candidate if isinstance(on_candidate, dict) else {}
        schedule = on_block.get("schedule", [])
        assert len(schedule) >= 1
        cron_expr = schedule[0].get("cron")
        # 0 2 * * 0 is weekly on Sunday at 02:00 UTC
        assert cron_expr == "0 2 * * 0"

    def test_retention_days_is_thirty(self) -> None:
        """Artifact upload retention must be set to 30 days."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        upload_steps = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")]
        assert len(upload_steps) == 1
        upload_step = upload_steps[0]
        assert upload_step.get("with", {}).get("retention-days") == 30

    def test_preflight_step_exists_before_dump(self) -> None:
        """Preflight validation step must execute before dump step."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        step_names = [s.get("name", "") for s in steps]

        # Check preflight step exists
        preflight_idx = next(
            (idx for idx, name in enumerate(step_names) if "preflight" in name.lower()),
            None,
        )
        assert preflight_idx is not None, "Preflight step missing from workflow"

        # Check dump step exists and follows preflight
        dump_idx = next(
            (idx for idx, name in enumerate(step_names) if "dump" in name.lower() and "encrypt" not in name.lower()),
            None,
        )
        assert dump_idx is not None, "Dump step missing from workflow"
        assert preflight_idx < dump_idx, "Preflight step must execute before pg_dump"

        # Verify run 36835825347 root cause context in preflight step or comments
        raw_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "36835825347" in raw_text

    def test_artifact_upload_references_encrypted_file_only(self) -> None:
        """Artifact upload must only upload encrypted gpg file, never raw dump."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        upload_step = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        path_value = upload_step.get("with", {}).get("path")
        assert path_value == "dump.pgdump.gpg"
        assert not path_value.endswith(".pgdump") or path_value.endswith(".gpg")

    def test_backup_encryption_key_referenced_exactly_once(self) -> None:
        """BACKUP_ENCRYPTION_KEY secret must be referenced exactly once in workflow."""
        raw_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        matches = re.findall(r"secrets\.BACKUP_ENCRYPTION_KEY", raw_text)
        assert len(matches) == 1

    def test_no_echo_of_secrets(self) -> None:
        """Workflow must never echo secrets or env variables containing secrets."""
        raw_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        # Forbidden: echo $SUPABASE_DB_URL, echo $BACKUP_KEY, echo ${{ secrets... }}
        assert not re.search(r"echo\s+.*\$SUPABASE_DB_URL", raw_text)
        assert not re.search(r"echo\s+.*\$BACKUP_KEY", raw_text)
        assert not re.search(r"echo\s+.*\$\{\{\s*secrets\.", raw_text)

    def test_fails_if_encryption_key_missing(self) -> None:
        """Encryption step must check for missing BACKUP_ENCRYPTION_KEY and fail explicitly."""
        raw_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "BACKUP_ENCRYPTION_KEY secret is not set" in raw_text
        assert "exit 1" in raw_text
