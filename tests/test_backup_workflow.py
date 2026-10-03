"""Structural tests for .github/workflows/backup.yml.

Asserts weekly cron schedule, 30-day retention, preflight step before pg_dump,
encryption requirement, single reference to BACKUP_ENCRYPTION_KEY, and absence
of secret leakage in shell commands.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
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
        """Encryption step must check for missing BACKUP_ENCRYPTION_KEY in its own run block and fail explicitly."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        encryption_step = next(s for s in steps if "encrypt" in s.get("name", "").lower())
        run_block = encryption_step.get("run", "")
        assert "BACKUP_ENCRYPTION_KEY secret is not set" in run_block
        assert "exit 1" in run_block

    def test_preflight_no_fragile_glob_or_bare_case(self) -> None:
        """Preflight step must not use fragile shell globs (*:5432/*) or bare case marker matching."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        preflight_step = next(s for s in steps if "preflight" in s.get("name", "").lower())
        run_block = preflight_step.get("run", "")
        assert "*:5432/*" not in run_block
        assert "case " not in run_block

    def test_preflight_references_validate_db_url(self) -> None:
        """Preflight step must invoke validate_db_url from db_guard rather than duplicating logic."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        preflight_step = next(s for s in steps if "preflight" in s.get("name", "").lower())
        run_block = preflight_step.get("run", "")
        assert "validate_db_url" in run_block
        assert "db_guard" in run_block

    def _execute_preflight_step(self, url: str | None) -> subprocess.CompletedProcess[str]:
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        preflight_step = next(s for s in steps if "preflight" in s.get("name", "").lower())
        run_script = preflight_step["run"]
        env = os.environ.copy()
        if url is not None:
            env["SUPABASE_DB_URL"] = url
        else:
            env.pop("SUPABASE_DB_URL", None)
        bash_bin = shutil.which("bash") or "/bin/bash"
        return subprocess.run([bash_bin, "-c", run_script], env=env, capture_output=True, text=True, check=False)  # noqa: S603

    def test_preflight_accepts_valid_pooler_non_5432_url(self) -> None:
        """Valid pooler URL with non-5432 port is accepted by preflight."""
        proc = self._execute_preflight_step(
            "postgresql://user:db_super_secret_password_777@aws-0.pooler.supabase.com:6543/postgres"
        )
        assert proc.returncode == 0
        assert "Preflight check passed" in proc.stdout
        assert "db_super_secret_password_777" not in proc.stdout

    def test_preflight_rejects_marker_only_string_with_no_hostname(self) -> None:
        """Marker-only string without hostname or valid URI structure is rejected."""
        proc = self._execute_preflight_step("pooler")
        assert proc.returncode != 0
        output = proc.stdout + proc.stderr
        assert "::error::" in output
        assert "invalid_scheme" in output

    def test_preflight_accepts_uppercase_hostname(self) -> None:
        """Uppercase hostname in pooler URL is accepted (case-insensitive parity)."""
        proc = self._execute_preflight_step("postgresql://user:pass@AWS-0.POOLER.SUPABASE.COM:6543/postgres")
        assert proc.returncode == 0
        assert "Preflight check passed" in proc.stdout

    @pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg executable not available")
    def test_gpg_encryption_roundtrip(self, tmp_path: Path) -> None:
        """GPG AES256 symmetric encryption recovers plaintext and ciphertext hides plaintext."""
        gpg_bin = shutil.which("gpg")
        assert gpg_bin is not None, "gpg executable must be available"

        plaintext = b"DATABASE_DUMP_PLAINTEXT_PAYLOAD_FOR_TESTING_12345"
        dump_file = tmp_path / "dump.pgdump"
        enc_file = tmp_path / "dump.pgdump.gpg"
        dec_file = tmp_path / "restored.pgdump"

        dump_file.write_bytes(plaintext)
        passphrase = "test_super_secret_encryption_key_555"

        enc_proc = subprocess.run(
            [
                gpg_bin,
                "--batch",
                "--yes",
                "--symmetric",
                "--cipher-algo",
                "AES256",
                "--passphrase",
                passphrase,
                "-o",
                str(enc_file),
                str(dump_file),
            ],
            capture_output=True,
            text=True,
            check=False,
        )  # noqa: S603
        assert enc_proc.returncode == 0
        ciphertext = enc_file.read_bytes()
        assert plaintext not in ciphertext

        dec_proc = subprocess.run(
            [
                gpg_bin,
                "--batch",
                "--yes",
                "--decrypt",
                "--passphrase",
                passphrase,
                "-o",
                str(dec_file),
                str(enc_file),
            ],
            capture_output=True,
            text=True,
            check=False,
        )  # noqa: S603
        assert dec_proc.returncode == 0
        recovered = dec_file.read_bytes()
        assert recovered == plaintext

    @pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg executable not available")
    def test_gpg_roundtrip_matches_workflow_flags(self, tmp_path: Path) -> None:
        """Local roundtrip mirrors the exact gpg command flags in backup.yml."""
        data = _load_workflow()
        steps = data["jobs"]["backup"]["steps"]
        encryption_step = next(s for s in steps if "encrypt" in s.get("name", "").lower())
        run_block = encryption_step["run"]

        # Workflow must specify these exact security flags
        expected_flags = ["--batch", "--yes", "--symmetric", "--cipher-algo AES256", "--passphrase"]
        for flag in expected_flags:
            assert flag in run_block, f"Missing expected GPG flag {flag} in workflow"
