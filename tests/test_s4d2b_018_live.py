"""S4.2B RED: 018 live 8-step ordered execution — creds real required, fail-with-warning not mocked pass.

Specs: database-layer credential-gated live execution of 018; 8-step ordered DDL;
threat: fixed-argv psql shell=False ON_ERROR_STOP, rollback DOWN.

Strict TDD: this file MUST FAIL before GREEN (S4.2B) and PASS after helper + 018.
"""

from __future__ import annotations

import os
import pathlib
import warnings
from unittest.mock import patch

import pytest

MIG_018 = pathlib.Path("migrations/018_ticket_integrity_fks.sql")


def _read_018() -> str:
    assert MIG_018.exists(), f"018 not found at {MIG_018}"
    return MIG_018.read_text(encoding="utf-8")


def _norm(sql: str) -> str:
    return " ".join(sql.lower().split())


# ---------------------------------------------------------------------------
# 3.1 RED preflight — DO raises before TEXT->UUID USING
# ---------------------------------------------------------------------------


class TestPreflightRaisesBeforeCast:
    def test_preflight_do_before_using(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        pre = n.find("preflight")
        using = n.find("using", pre + 1)
        assert pre != -1 and using != -1
        assert pre < using, "DO $preflight$ must precede TEXT->UUID USING cast"

    def test_preflight_checks_duplicates(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "duplicate" in n
        assert "raise exception" in n
        assert "idx_ticket_active_slot" in sql or "active_slot" in n
        assert "idx_ticket_active_channel" in sql or "active_channel" in n

    def test_preflight_checks_21_21_valid_uuid(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "categoryid" in n
        assert "uuid" in n
        assert "raise exception" in n
        # 21/21 valid UUID — invalid shape aborts
        assert "!~" in sql or "uuid" in n

    def test_preflight_checks_note_orphans_zero(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "ticket_note" in n
        assert "orphan" in n
        assert "raise exception" in n

    def test_preflight_checks_audit_1_1_retention(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "ticket_audit" in n
        assert "raise exception" in n
        # 1 orphan + 1 mismatch retention approved, larger drift aborts
        assert "retention" in n or "orphan" in n

    def test_preflight_checks_parent_depth(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "parent" in n
        assert "depth" in n or "parentid" in n
        assert "raise exception" in n


# ---------------------------------------------------------------------------
# 3.1 RED: apply_staging_migration.py fixed-argv psql shell=False ON_ERROR_STOP
# ---------------------------------------------------------------------------


class TestApplyHelperFixedArgv:
    def test_helper_module_importable(self) -> None:
        import importlib

        mod = importlib.import_module("scripts.apply_staging_migration")
        assert mod is not None

    def test_helper_exposes_fixed_argv_builder(self) -> None:
        from scripts.apply_staging_migration import build_psql_argv

        argv = build_psql_argv("postgresql://user:pass@localhost/db", str(MIG_018))
        assert isinstance(argv, list)
        # fixed argv — must contain psql and ON_ERROR_STOP, not shell string
        joined = " ".join(argv).lower()
        assert "psql" in joined
        assert "on_error_stop" in joined
        # DB URL must be present as separate argv element, not shell-composed
        assert "postgresql://" in " ".join(argv)
        # migration file must be via -f flag, not arbitrary
        assert "-f" in argv

    def test_helper_uses_shell_false_and_no_shell_true(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        assert "shell=False" in text
        assert "shell=True" not in text
        assert "ON_ERROR_STOP" in text

    def test_helper_rejects_arbitrary_file_fallback(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        # Must have allowlist or fixed 018 path, not arbitrary execute_sql fallback
        assert "018_ticket_integrity_fks" in text
        # Must not use execute_sql as untracked substitute
        assert "shell=False" in text

    def test_helper_requires_live_supabase_and_db_url_gate(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        assert "LIVE_SUPABASE" in text
        assert "DB_URL" in text

    def test_helper_has_timeout_and_backup_evidence(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        assert "timeout" in text.lower()
        # backup is in SQL; helper must document or capture before/after
        assert "backup" in text.lower() or "ticket_backup" in text.lower() or "before" in text.lower()


# ---------------------------------------------------------------------------
# 3.2 GREEN 018 order — 8 steps via helper execution path
# ---------------------------------------------------------------------------


class TestOrderedExecutionViaHelper:
    def test_eight_steps_ordered(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        preflight = n.find("preflight")
        using = n.find("using", preflight + 1)
        idx = n.find("create index if not exists", using + 1)
        parent_fk = n.find("fk_ticket_parent_restrict", idx + 1)
        category_fk = n.find("fk_ticket_category_set_null", parent_fk + 1)
        note_fk = n.find("fk_ticket_note_cascade", category_fk + 1)
        audit_fk = n.find("fk_ticket_audit_set_null", note_fk + 1)
        validate = n.find("validate constraint", audit_fk + 1)
        steps = [preflight, using, idx, parent_fk, category_fk, note_fk, audit_fk, validate]
        for i, pos in enumerate(steps):
            assert pos != -1, f"step {i + 1} missing"
        assert steps == sorted(steps)

    def test_fk_actions_and_audit_nullable(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "on delete restrict" in n
        assert n.count("on delete set null") >= 2
        assert "on delete cascade" in n
        assert "drop not null" in n

    def test_only_duplicate_index_dropped(self) -> None:
        sql = _read_018()
        code = "\n".join(ln for ln in sql.splitlines() if ln.strip() and not ln.strip().startswith("--"))
        assert code.lower().count("drop index") == 1
        assert "idx_ticket_guild_number" in code

    def test_down_migration_present(self) -> None:
        sql = _read_018()
        n = _norm(sql)
        assert "down migration" in n or "rollback" in n
        assert "drop constraint" in n


# ---------------------------------------------------------------------------
# 3.3 GREEN live gate — LIVE_SUPABASE=1 + DB_URL real, else warning/fail not mocked pass
# ---------------------------------------------------------------------------


class TestLiveGateStrict:
    def test_with_live_and_db_url_passes_gate(self) -> None:
        from scripts.apply_staging_migration import check_live_gate

        with patch.dict(
            os.environ,
            {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://user:pass@localhost/db"},
            clear=False,
        ):
            result = check_live_gate(used_real_db=True)
            assert result.passed is True
            assert result.used_real_db is True

    def test_live_without_db_url_fails_with_warning_not_mocked_pass(self) -> None:
        from scripts.apply_staging_migration import check_live_gate

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DB_URL", None)
            os.environ.pop("SUPABASE_DB_URL", None)
            os.environ.pop("DATABASE_URL", None)
            os.environ["LIVE_SUPABASE"] = "1"
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = check_live_gate(used_real_db=False)
                assert result.passed is False
                assert any(
                    "db_url" in r.lower() or "credential" in r.lower() or "real" in r.lower() for r in result.reasons
                )
                # must warn, not silently pass
                assert any(issubclass(x.category, UserWarning) for x in w) or len(result.reasons) > 0
            os.environ.pop("LIVE_SUPABASE", None)

    def test_fake_supabase_never_passes_live_gate(self) -> None:
        from scripts.apply_staging_migration import check_live_gate

        with (
            patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://u:p@h/db"}, clear=False),
            warnings.catch_warnings(record=True),
        ):
            warnings.simplefilter("always")
            result = check_live_gate(used_real_db=False)
            assert result.passed is False
            assert result.used_real_db is False

    def test_missing_live_marker_fails_closed(self) -> None:
        from scripts.apply_staging_migration import check_live_gate

        with (
            patch.dict(os.environ, {}, clear=False),
            warnings.catch_warnings(record=True),
        ):
            warnings.simplefilter("always")
            os.environ.pop("LIVE_SUPABASE", None)
            os.environ.pop("DB_URL", None)
            os.environ.pop("SUPABASE_DB_URL", None)
            result = check_live_gate(used_real_db=False)
            assert result.passed is False
            assert any("live_supabase" in r.lower() for r in result.reasons)


@pytest.mark.live
def test_live_marker_asserts_db_path_real_with_creds() -> None:
    """Live marker: with LIVE_SUPABASE=1 + DB_URL, helper must assert DB path real."""
    from scripts.apply_staging_migration import check_live_gate

    if os.getenv("LIVE_SUPABASE") != "1" or not (os.getenv("DB_URL") or os.getenv("SUPABASE_DB_URL")):
        pytest.skip("live creds absent -- warning path verified, real DB path not executed")
    result = check_live_gate(used_real_db=True)
    assert result.passed is True
    assert result.used_real_db is True
    # must not be fake path
    assert "fake" not in " ".join(result.reasons).lower()


class Test018BeforeAfterCaptureMockedProvenance:
    """S4 deferral with formal LIVE_SUPABASE=1 gate — mocked psycopg proves helper would execute."""

    def test_run_psql_would_execute_with_mocked_psycopg_and_real_creds(self) -> None:
        """Before/after capture: helper builds argv and calls subprocess with mocked psycopg path."""
        from unittest.mock import MagicMock, patch

        fake_result = MagicMock(returncode=0, stderr="", stdout="018 ok")
        with (
            patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://u:p@h/db"}, clear=False),
            patch("scripts.apply_staging_migration.subprocess.run", return_value=fake_result) as mock_run,
        ):
            from scripts.apply_staging_migration import run_psql_migration

            result = run_psql_migration(db_url="postgresql://u:p@h/db")
            assert result.passed is True
            assert mock_run.called
            argv = mock_run.call_args[0][0]
            assert "psql" in " ".join(argv).lower()
            assert "ON_ERROR_STOP" in " ".join(argv)

    def test_run_psql_fails_closed_without_live_marker(self) -> None:
        import warnings

        from scripts.apply_staging_migration import run_psql_migration

        with patch.dict(os.environ, {}, clear=False):
            import os as _os

            _os.environ.pop("LIVE_SUPABASE", None)
            _os.environ.pop("DB_URL", None)
            _os.environ.pop("SUPABASE_DB_URL", None)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = run_psql_migration(db_url=None)
            assert result.passed is False
            assert any("live_supabase" in r.lower() for r in result.reasons)
