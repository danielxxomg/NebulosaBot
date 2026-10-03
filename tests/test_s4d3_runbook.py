"""S4.3 RED: docs-only runbook + EXPLAIN + JWT rotation — no DDL/code moves.

Specs: proposal S4.3, design S4.3, tasks 4.1-4.3. Runbook must document
credential window/revocation, EXPLAIN ANALYZE BUFFERS, JWT JWKS rotation,
018 8-step + rollback + lock_timeout, GUILD_SCOPE_GAP_HISTORY.

Strict TDD: this file MUST FAIL before GREEN (runbook absent) and PASS after.
"""

from __future__ import annotations

import pathlib

RUNBOOK = pathlib.Path("docs/runbooks/staging-live-parity.md")
ALT_RUNBOOK = pathlib.Path("docs/staging-live-parity.md")


def _read_runbook() -> str:
    """Read the parity runbook, accepting either the canonical or legacy path.

    Returns:
        str: Full runbook text.

    Raises:
        AssertionError: When neither the canonical nor the legacy path exists.
    """
    if RUNBOOK.exists():
        return RUNBOOK.read_text(encoding="utf-8")
    if ALT_RUNBOOK.exists():
        return ALT_RUNBOOK.read_text(encoding="utf-8")
    msg = f"runbook not found at {RUNBOOK} or {ALT_RUNBOOK}"
    raise AssertionError(msg)


def _norm(text: str) -> str:
    """Normalize runbook text for whitespace- and case-insensitive matching.

    Args:
        text: Raw runbook content.

    Returns:
        str: Lowercased text with all whitespace runs collapsed to single spaces.
    """
    return " ".join(text.lower().split())


class TestRunbookExists:
    """Assert the parity runbook exists at a known path and carries real content."""

    def test_runbook_file_exists(self) -> None:
        assert RUNBOOK.exists() or ALT_RUNBOOK.exists(), f"runbook missing: {RUNBOOK} or {ALT_RUNBOOK}"

    def test_runbook_is_not_empty(self) -> None:
        text = _read_runbook()
        assert len(text.strip()) > 100


class TestCredentialWindowAndGates:
    """Assert the runbook documents the credential window, tracked psql call and quality gates."""

    def test_live_supabase_and_db_url_documented(self) -> None:
        text = _read_runbook()
        assert "LIVE_SUPABASE=1" in text
        assert "DB_URL" in text

    def test_supabase_db_url_variants_documented(self) -> None:
        text = _read_runbook()
        # S4.2 needs DB_URL / SUPABASE_DB_URL / DATABASE_URL variants
        assert "SUPABASE_DB_URL" in text or "DATABASE_URL" in text

    def test_credential_window_and_revocation(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "credential" in n or "creds" in n
        assert "revok" in n or "revoke" in n or "rotate" in n

    def test_backup_and_down_and_restore_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "backup" in n
        assert "down" in n or "rollback" in n
        assert "restore" in n

    def test_tracked_psql_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "psql" in n
        assert "018_ticket_integrity_fks" in text or "018" in text

    def test_ty_ruff_pytest_gates_documented(self) -> None:
        text = _read_runbook()
        assert "ty" in text.lower()
        assert "ruff" in text.lower()
        assert "pytest" in text.lower()

    def test_live_command_documented(self) -> None:
        text = _read_runbook()
        assert "LIVE_SUPABASE=1" in text
        assert "uv run pytest" in text
        assert "--run-live" in text or "run-live" in text or "-m live" in text


class Test018DdlSteps:
    """Assert the runbook documents the 8-step ordered DDL contract and its rollback matrix."""

    def test_eight_steps_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        # Must mention 8-step ordered contract
        assert "8" in text or "eight" in n
        assert "preflight" in n
        assert "using" in n or "cast" in n or "text->uuid" in n or "text → uuid" in n

    def test_lock_timeout_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "lock_timeout" in n or "lock timeout" in n or "statement_timeout" in n

    def test_only_duplicate_dropped_documented(self) -> None:
        text = _read_runbook()
        assert "idx_ticket_guild_number" in text

    def test_backup_table_name_documented(self) -> None:
        text = _read_runbook()
        assert "ticket_backup_categoryid_text_20260818" in text or "ticket_backup" in text.lower()


class TestExplainWorkload:
    """Assert the runbook documents the EXPLAIN ANALYZE BUFFERS index-retention policy."""

    def test_explain_analyze_buffers_documented(self) -> None:
        text = _read_runbook()
        assert "EXPLAIN" in text
        assert "ANALYZE" in text
        assert "BUFFERS" in text

    def test_zero_scans_alone_not_drop(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "pg_stat_user_indexes" in text or "pg_stat" in n
        assert "zero" in n or "0 scans" in n or "scan count" in n or "cumulative" in n
        assert "not" in n or "reject" in n or "retain" in n

    def test_idx_ticket_channel_retained(self) -> None:
        text = _read_runbook()
        assert "idx_ticket_channel" in text
        n = _norm(text)
        assert "retain" in n or "remain" in n or "not drop" in n or "only" in n

    def test_twelve_unused_indexes_noted(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        # Must note the 12 unused indexes or EXPLAIN workload for remaining
        assert "12" in text or "twelve" in n or "unused" in n


class TestJwtRotationDocs:
    """Assert the runbook documents JWKS-based RS256 rotation and HS256 rejection."""

    def test_jwks_uri_documented(self) -> None:
        text = _read_runbook()
        assert "jwks_uri" in text.lower() or "jwks_url" in text.lower() or "JWKS" in text

    def test_bounded_kid_refresh_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "kid" in n
        assert "refresh" in n or "bounded" in n or "retry" in n

    def test_rs256_documented(self) -> None:
        text = _read_runbook()
        assert "RS256" in text

    def test_hs256_allowlist_retained(self) -> None:
        text = _read_runbook()
        assert "HS256" in text
        assert "SUPABASE_JWT_SECRET" in text or "allowlist" in text.lower() or "legacy" in text.lower()

    def test_iss_aud_exp_role_documented(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "iss" in n
        assert "aud" in n
        assert "exp" in n
        assert "role" in n

    def test_alg_confusion_blocked_noted(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "alg" in n or "algorithm" in n
        assert "confusion" in n or "reject" in n or "fail" in n or "block" in n


class TestHistoricalRenameNote:
    """Assert the runbook explains the GUILD_SCOPE_GAP_HISTORY rename rationale."""

    def test_guild_scope_gap_history_documented(self) -> None:
        text = _read_runbook()
        assert "GUILD_SCOPE_GAP_HISTORY" in text

    def test_historical_note_present(self) -> None:
        text = _read_runbook()
        n = _norm(text)
        assert "historical" in n or "history" in n or "rename" in n

    def test_runtime_closed_12_documented(self) -> None:
        text = _read_runbook()
        assert "12" in text
        n = _norm(text)
        assert "runtime" in n or "closed" in n or "closure" in n


class TestRollbackHonesty:
    """Assert the runbook does not promise a rollback path that no longer exists."""

    def test_migration_025_drop_and_irreversibility_documented(self) -> None:
        """Runbook must explicitly state migration 025 dropped the backup table making DOWN irreversible."""
        text = _read_runbook()
        n = _norm(text)
        assert "025" in text
        assert "irreversible" in n
        assert "pre-window" in n or "database backup" in n
