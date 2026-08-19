"""S5.1 Strict TDD RED for production-live-close scoped catalog + JWKS dual + repair + threats."""

from __future__ import annotations

import pathlib
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1.1 RED: pg_policy JOIN pg_class/pg_namespace nspname='public' binding 9/7/0
# ---------------------------------------------------------------------------


class TestS5ScopingRed:
    def _read_catalog(self) -> str:
        return pathlib.Path("bot/services/live_catalog.py").read_text(encoding="utf-8")

    def test_policy_query_is_scoped_to_public_via_join(self) -> None:
        text = self._read_catalog()
        # Spec live-schema-verifier S5: MUST scope pg_policy to public via JOIN
        # Unscoped SELECT count(*) FROM pg_policy fails 9/7/0 -> 9/7/2 (cron)
        assert "nspname='public'" in text or 'nspname="public"' in text or "nspname" in text
        # Must join through pg_class/polrelid for policy scope
        assert "pg_policy" in text
        assert "pg_class" in text
        assert "pg_namespace" in text
        # The fetch_rls_counts_via_db body must contain the scoped JOIN, not a bare count
        assert "JOIN pg_class" in text

    def test_fk_query_is_scoped_to_public_via_join(self) -> None:
        text = self._read_catalog()
        assert "pg_constraint" in text
        assert "n.nspname='public'" in text or "nspname='public'" in text or "nspname" in text
        # Must join conrelid -> pg_class -> pg_namespace
        assert "conrelid" in text
        assert "relnamespace" in text

    def test_fk_sync_fetch_catalog_uses_scoped_sql(self) -> None:
        """_sync_fetch_catalog must execute scoped SQL (29->6)."""
        executed: list[str] = []

        class FakeCursor:
            def __enter__(self) -> FakeCursor:
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def execute(self, sql: str, *_: object, **__: object) -> None:
                executed.append(sql)

            def fetchall(self) -> list[tuple[str, ...]]:
                if executed and "pg_constraint" in executed[-1]:
                    return [("ticket", "guild", "CASCADE")]
                return []

            def fetchone(self) -> tuple[int, ...] | None:
                return (0,)

        class FakeConn:
            def __enter__(self) -> FakeConn:
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def cursor(self) -> FakeCursor:
                return FakeCursor()

        fake_connect = MagicMock(return_value=FakeConn())
        with patch("psycopg.connect", fake_connect):
            from bot.services.live_catalog import _sync_fetch_catalog

            _sync_fetch_catalog("postgresql://u:p@h/db")
        assert fake_connect.called
        fk_sql = next(s for s in executed if "pg_constraint" in s)
        assert "nspname" in fk_sql and "public" in fk_sql, "FK query must be scoped to public"
        assert "JOIN pg_class" in fk_sql

    def test_rls_counts_uses_scoped_policy_count(self) -> None:
        counts = iter([(9,), (7,), (0,)])
        cur = MagicMock()
        cur.fetchone.side_effect = lambda: next(counts)
        cur.execute.return_value = None
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = False
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = False
        with patch("psycopg.connect", return_value=conn):
            from bot.services.live_catalog import fetch_rls_counts_via_db

            enabled, forced, policies = fetch_rls_counts_via_db("postgresql://u:p@h/db")
        assert (enabled, forced, policies) == (9, 7, 0)
        # Last execute must be the scoped pg_policy count
        last_sql = str(cur.execute.call_args_list[-1][0][0])
        assert "nspname" in last_sql and "public" in last_sql


# ---------------------------------------------------------------------------
# 1.5 RED: JWKS dual ES256+RS256 kid=1, unknown kid refresh, HS256 rejected
# ---------------------------------------------------------------------------


def _ec_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub_pem = pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv_pem, pub_pem


def _rsa_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub_pem = pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv_pem, pub_pem


class TestJwksDualRed:
    def test_es256_live_key_verifies_kid1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _ec_pair()
        from bot.config import _verify_jwt_jwks

        iss, aud = "https://proj.supabase.co/auth/v1", "authenticated"
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", iss)
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", aud)
        token = pyjwt.encode(
            {"role": "service_role", "iss": iss, "aud": aud, "exp": int(time.time()) + 600},
            priv_pem,
            algorithm="ES256",
            headers={"kid": "1"},
        )
        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_jwks(token) == "service_role"

    def test_rs256_still_verifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        from bot.config import _verify_jwt_jwks

        iss, aud = "https://proj.supabase.co/auth/v1", "authenticated"
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", iss)
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", aud)
        token = pyjwt.encode(
            {"role": "service_role", "iss": iss, "aud": aud, "exp": int(time.time()) + 600},
            priv_pem,
            algorithm="RS256",
            headers={"kid": "1"},
        )
        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_jwks(token) == "service_role"

    def test_hs256_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        token = pyjwt.encode(
            {"role": "service_role", "iss": "https://proj.supabase.co/auth/v1",
             "aud": "authenticated", "exp": int(time.time()) + 600},
            "strong-secret-32bytes-for-hs256-test-x",
            algorithm="HS256",
        )
        from bot.config import _verify_jwt_jwks

        assert _verify_jwt_jwks(token) is None

    def test_unknown_kid_one_refresh_then_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, _ = _ec_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        token = pyjwt.encode(
            {"role": "service_role", "iss": "https://proj.supabase.co/auth/v1",
             "aud": "authenticated", "exp": int(time.time()) + 600},
            priv_pem,
            algorithm="ES256",
            headers={"kid": "unknown"},
        )
        from bot.config import _verify_jwt_jwks

        mc = MagicMock()
        mc.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.PyJWKClientError("kid not found")
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_jwks(token) is None
            assert mc.get_signing_key_from_jwt.call_count <= 2

    def test_jwks_allowlist_contains_both(self) -> None:
        from bot.config import _JWKS_ALGS

        assert "RS256" in _JWKS_ALGS and "ES256" in _JWKS_ALGS
        assert "HS256" not in _JWKS_ALGS


# ---------------------------------------------------------------------------
# 2.2 RED: repair allowlist 3 desync -> 19<->19 tracked
# ---------------------------------------------------------------------------


class TestRepairAllowlistRed:
    def test_repair_allowlist_is_3_names(self) -> None:
        from scripts.apply_staging_migration import REPAIR_DESYNC_ALLOWLIST

        assert len(REPAIR_DESYNC_ALLOWLIST) == 3
        assert set(REPAIR_DESYNC_ALLOWLIST) == {
            "greeting_onboarding_channel",
            "add_tables_to_realtime_publication",
            "add_realtime_publication_tables",
        }

    def test_build_repair_argv_fixed_shell_false(self) -> None:
        from scripts.apply_staging_migration import build_repair_argv

        argvs = build_repair_argv()
        assert len(argvs) == 3
        for argv in argvs:
            assert argv[0] == "supabase"
            assert "repair" in argv
            assert "--status" in argv and "applied" in argv
            assert "--version" in argv

    def test_repair_rejects_non_allowlisted(self) -> None:
        from scripts.apply_staging_migration import build_repair_argv

        with pytest.raises(ValueError, match="allowlist"):
            build_repair_argv(("evil_migration",))  # type: ignore[arg-type]

    def test_supabase_config_and_symlink_exist(self) -> None:
        assert pathlib.Path("supabase/config.toml").exists()
        # symlink supabase/migrations -> ../migrations (or dir)
        p = pathlib.Path("supabase/migrations")
        assert p.exists()
        # must resolve to real migrations dir with 018
        assert (pathlib.Path("migrations/018_ticket_integrity_fks.sql")).exists()


# ---------------------------------------------------------------------------
# 3.1 RED subprocess/shell threat guards
# ---------------------------------------------------------------------------


class TestSubprocessShellThreat:
    def test_non_018_rejected(self) -> None:
        from scripts.apply_staging_migration import build_psql_argv

        with pytest.raises(ValueError, match="untracked"):
            build_psql_argv("postgresql://u:p@h/db", "migrations/001_initial_schema.sql")  # type: ignore[arg-type]

    def test_shell_false_and_on_error_stop(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        assert "shell=False" in text
        assert "ON_ERROR_STOP" in text
        assert "shell=True" not in text

    def test_non_zero_exit_raises_and_backup_retained(self) -> None:
        import os
        from unittest.mock import MagicMock, patch

        fake = MagicMock(returncode=1, stderr="lock_timeout abort", stdout="")
        with (
            patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://u:p@h/db"}, clear=False),
            patch("scripts.apply_staging_migration.subprocess.run", return_value=fake),
        ):
            from scripts.apply_staging_migration import run_psql_migration

            with pytest.raises(RuntimeError, match="psql migration failed"):
                run_psql_migration(db_url="postgresql://u:p@h/db")
        # backup table proven in SQL, not dropped on failure
        sql = pathlib.Path("migrations/018_ticket_integrity_fks.sql").read_text(encoding="utf-8")
        assert "ticket_backup_categoryid_text_20260818" in sql

    def test_repair_subprocess_uses_shell_false(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        # repair path also shell=False
        assert text.count("shell=False") >= 2

    def test_timeout_and_backup_present(self) -> None:
        text = pathlib.Path("scripts/apply_staging_migration.py").read_text(encoding="utf-8")
        assert "timeout" in text.lower()
        assert "ticket_backup_categoryid_text_20260818" in text or "BACKUP_TABLE" in text


# ---------------------------------------------------------------------------
# 3.2 RED process integration: creds gate, preflight fail no cast, lock_timeout abort
# ---------------------------------------------------------------------------


class TestProcessIntegrationRed:
    def test_missing_live_or_db_url_fails_gate(self) -> None:
        import os
        import warnings

        from scripts.apply_staging_migration import check_live_gate

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIVE_SUPABASE", None)
            os.environ.pop("DB_URL", None)
            os.environ.pop("SUPABASE_DB_URL", None)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = check_live_gate(used_real_db=False)
            assert result.passed is False
            assert any("live_supabase" in r.lower() or "db_url" in r.lower() for r in result.reasons)

    def test_preflight_fail_no_cast(self) -> None:
        sql = pathlib.Path("migrations/018_ticket_integrity_fks.sql").read_text(encoding="utf-8")
        n = " ".join(sql.lower().split())
        assert n.find("preflight") < n.find("using"), "preflight must precede USING cast"
        assert "raise exception" in n

    def test_lock_timeout_5s_present(self) -> None:
        sql = pathlib.Path("migrations/018_ticket_integrity_fks.sql").read_text(encoding="utf-8")
        assert "lock_timeout" in sql.lower()
        assert "5s" in sql

    def test_down_migration_present(self) -> None:
        sql = pathlib.Path("migrations/018_ticket_integrity_fks.sql").read_text(encoding="utf-8")
        assert "DOWN" in sql or "down migration" in sql.lower() or "rollback" in sql.lower()
        assert "DROP CONSTRAINT" in sql


# ---------------------------------------------------------------------------
# 3.3 RED evidence wiring — LiveEvidenceReport 9/7/0 6FKs 4pubs 19<->19 + EXPLAIN receipt
# ---------------------------------------------------------------------------


class TestEvidenceWiringRed:
    def test_before_after_evidence_and_explain_receipt(self) -> None:
        from bot.services.live_catalog import evaluate_index_policy

        # EXPLAIN with BUFFERS must allow duplicate drop
        explain = "EXPLAIN (ANALYZE, BUFFERS) Index Only Scan using idx_ticket_guild_ticket_number"
        ok, _ = evaluate_index_policy(scans=0, explain_output=explain)
        assert ok is True
        # zero scans without EXPLAIN must reject
        not_ok, reason = evaluate_index_policy(scans=0, explain_output=None)
        assert not_ok is False and "EXPLAIN" in reason

    def test_capture_live_evidence_callable(self) -> None:
        from scripts.apply_staging_migration import capture_live_evidence_via_db

        bound, explain = capture_live_evidence_via_db("postgresql://u:p@h/db")
        assert bound is not None
        assert "EXPLAIN" in str(explain) and "BUFFERS" in str(explain)
        assert "idx_ticket_guild_ticket_number" in str(explain)
