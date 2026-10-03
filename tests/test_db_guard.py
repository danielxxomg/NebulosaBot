"""Tests for database URL validation and error scrubbing guard utilities.

Verifies fail-closed URL validation (pooler marker required, postgres scheme,
non-empty) and credential/socket scrubbing for safe error propagation.
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from bot.utils.db_guard import (
    REASON_EMPTY_URL,
    REASON_INVALID_FORMAT,
    REASON_INVALID_SCHEME,
    REASON_MISSING_POOLER_MARKER,
    REASON_OK,
    DBUrlValidationResult,
    scrub_error,
    validate_db_url,
)
from scripts.apply_staging_migration import STDERR_LOG_LIMIT, run_psql_migration


class TestValidateDbUrl:
    """Test suite for validate_db_url fail-closed behavior."""

    @pytest.mark.parametrize(
        "empty_input",
        [
            None,
            "",
            "   ",
            "\t\n  \r",
        ],
    )
    def test_rejects_absent_empty_or_whitespace_url(self, empty_input: str | None) -> None:
        """Absent, empty, or whitespace-only URLs must fail with empty_url code."""
        result = validate_db_url(empty_input)
        assert isinstance(result, DBUrlValidationResult)
        assert not result.ok
        assert result.reason == REASON_EMPTY_URL

    @pytest.mark.parametrize(
        "invalid_scheme_url",
        [
            "http://aws-0.pooler.supabase.com:5432/postgres",
            "https://supabase.co:5432/postgres",
            "mysql://user:pass@pooler.supabase.com:5432/db",
            "sqlite:///path/to/db.sqlite3",
            "redis://user:pass@pooler.supabase.com:5432/0",
            "just_a_string_without_scheme",
            "://missing-scheme-pooler.supabase.com:5432",
        ],
    )
    def test_rejects_non_postgres_scheme(self, invalid_scheme_url: str) -> None:
        """Non-postgres schemes must fail with invalid_scheme code."""
        result = validate_db_url(invalid_scheme_url)
        assert not result.ok
        assert result.reason == REASON_INVALID_SCHEME

    @pytest.mark.parametrize(
        "non_pooler_url",
        [
            "postgresql://user:secret@localhost:5433/postgres",
            "postgresql://user:secret@db.example.com:6543/postgres",
            "postgres://user:secret@database.internal/postgres",
            "postgresql://user:secret@custom-host.org:9999/mydb",
        ],
    )
    def test_rejects_non_pooler_host_and_port(self, non_pooler_url: str) -> None:
        """URLs missing both 5432 port and pooler/supabase hostname marker must fail."""
        result = validate_db_url(non_pooler_url)
        assert not result.ok
        assert result.reason == REASON_MISSING_POOLER_MARKER

    @pytest.mark.parametrize(
        "valid_url",
        [
            "postgresql://postgres.xxx:mypass@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
            "postgres://postgres.xxx:mypass@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "postgresql://postgres:mypass@db.abcdefgh.supabase.co:5432/postgres",
            "postgresql://user:secret@localhost:5432/mydb",
            "postgresql://user:secret@internal-pooler.company.local:6432/mydb",
            "postgres://user:secret@pooler.staging:9000/db",
        ],
    )
    def test_accepts_valid_pooler_or_5432_url(self, valid_url: str) -> None:
        """URLs with pooler/supabase in hostname or port 5432 must pass."""
        result = validate_db_url(valid_url)
        assert result.ok
        assert result.reason == REASON_OK

    def test_result_carries_codes_and_never_leaks_input_url(self) -> None:
        """Validation result reason and representation must never echo the input URL."""
        secret_url = "postgresql://admin:super_secret_pw@unauthorized-host.org:9999/db"
        result = validate_db_url(secret_url)
        assert not result.ok
        assert result.reason == REASON_MISSING_POOLER_MARKER
        assert "super_secret_pw" not in result.reason
        assert "unauthorized-host.org" not in result.reason
        assert "super_secret_pw" not in str(result)
        assert "super_secret_pw" not in repr(result)

    def test_handles_malformed_url_gracefully(self) -> None:
        """Malformed URLs (e.g. invalid port number) return invalid_format or invalid_scheme."""
        result = validate_db_url("postgresql://user:pass@pooler.supabase.com:not_a_port/db")
        assert not result.ok
        assert result.reason in (REASON_INVALID_FORMAT, REASON_INVALID_SCHEME)


class TestScrubError:
    """Test suite for scrub_error redaction functionality."""

    def test_scrubs_uri_credentials(self) -> None:
        """Credentials in connection URIs must be redacted."""
        raw = "Failed to connect to postgresql://postgres:s3cr3t_p@ss@db.pooler.supabase.com:6543/postgres"
        scrubbed = scrub_error(raw)
        assert "s3cr3t_p@ss" not in scrubbed
        assert "p@ss" not in scrubbed
        assert "ss@" not in scrubbed
        assert "postgres" in scrubbed or "***" in scrubbed
        assert "@db.pooler.supabase.com:6543/postgres" in scrubbed

    def test_scrubs_password_containing_at_symbol_completely(self) -> None:
        """Password containing '@' must leave no secret fragment behind."""
        raw = "postgresql://user:s3cr3t_p@ss@pooler.supabase.com:5432/postgres"
        scrubbed = scrub_error(raw)
        assert "s3cr3t_p@ss" not in scrubbed
        assert "s3cr3t" not in scrubbed
        assert "p@ss" not in scrubbed
        assert "ss@" not in scrubbed
        assert "pooler.supabase.com:5432/postgres" in scrubbed
        assert scrubbed == "postgresql://***:***@pooler.supabase.com:5432/postgres"

    @pytest.mark.parametrize(
        "raw_userinfo",
        [
            "user:p?ss",  # raw '?' inside userinfo
            "user:p#ss",  # raw '#' inside userinfo
            "user:p?ss#frag",
            "user:p%20ss",  # percent-encoded space must still work
        ],
    )
    def test_scrubs_credentials_with_raw_delimiters_in_userinfo(self, raw_userinfo: str) -> None:
        """Raw '?' or '#' inside userinfo must not defeat credential redaction."""
        raw = f"postgres://{raw_userinfo}@pooler.supabase.com:5432/db"
        scrubbed = scrub_error(raw)
        assert "p?ss" not in scrubbed
        assert "p#ss" not in scrubbed
        assert "p%20ss" not in scrubbed
        assert "pooler.supabase.com:5432/db" in scrubbed

    def test_scrub_error_is_linear_on_long_non_uri_token(self) -> None:
        """A long alphabetic token with no URI delimiter must not trigger quadratic backtracking."""
        # The unanchored scheme prefix used to rescan the whole token at every start
        # position. Regression guard: a large alphabetic blob must scrub quickly.
        blob = "a" * 200_000
        start = time.perf_counter()
        scrub_error(blob)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"scrub_error took {elapsed:.3f}s on a {len(blob)}-char non-URI token"

    def test_scrubs_quoted_secret_params_containing_spaces(self) -> None:
        """Quoted secret parameter values containing spaces must be fully redacted."""
        raw = (
            'options: password="secret with spaces" '
            "token='token with spaces' "
            'key="key with spaces & symbols; inside" '
            "api_key='spaced api key' "
            "normal_param=unaffected"
        )
        scrubbed = scrub_error(raw)
        assert "secret with spaces" not in scrubbed
        assert "token with spaces" not in scrubbed
        assert "key with spaces" not in scrubbed
        assert "spaced api key" not in scrubbed
        assert "password=[REDACTED]" in scrubbed
        assert "token=[REDACTED]" in scrubbed
        assert "key=[REDACTED]" in scrubbed
        assert "api_key=[REDACTED]" in scrubbed
        assert "normal_param=unaffected" in scrubbed

    def test_scrubs_query_param_secrets(self) -> None:
        """Query parameters carrying secrets must have values redacted."""
        raw = "GET /v1/query?password=my_secret_pw&token=tok_987654&key=k_12345&secret=sec_abc&preserve=true"
        scrubbed = scrub_error(raw)
        assert "my_secret_pw" not in scrubbed
        assert "tok_987654" not in scrubbed
        assert "k_12345" not in scrubbed
        assert "sec_abc" not in scrubbed
        assert "preserve=true" in scrubbed

    def test_scrubs_key_value_secrets(self) -> None:
        """Key-value style secret options in libpq or log strings must be redacted."""
        raw = "Connection options: host=localhost password=super_hidden_pw sslmode=require"
        scrubbed = scrub_error(raw)
        assert "super_hidden_pw" not in scrubbed
        assert "host=localhost" in scrubbed
        assert "sslmode=require" in scrubbed

    def test_scrubs_unix_socket_paths(self) -> None:
        """PostgreSQL Unix socket file and directory paths must be redacted."""
        error_msg_var = (
            'pg_dump: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" '
            "failed: No such file or directory"
        )
        scrubbed_var = scrub_error(error_msg_var)
        assert "/var/run/postgresql/.s.PGSQL.5432" not in scrubbed_var
        assert "[REDACTED_SOCKET]" in scrubbed_var or "[REDACTED]" in scrubbed_var

        error_msg_tmp = 'psql: error: connection on socket "/tmp/.s.PGSQL.5432" failed'  # noqa: S108 -- test Unix socket path
        scrubbed_tmp = scrub_error(error_msg_tmp)
        assert "/tmp/.s.PGSQL.5432" not in scrubbed_tmp  # noqa: S108

    def test_scrub_never_leaks_input_url_with_credentials(self) -> None:
        """Input URLs with embedded credentials must not appear in cleartext."""
        sensitive_url = "postgres://root:very_sensitive_pass_12345@aws-0.pooler.supabase.com:5432/app"
        err = f"Error during execution: {sensitive_url}"
        scrubbed = scrub_error(err)
        assert "very_sensitive_pass_12345" not in scrubbed

    def test_leaves_benign_text_unmodified(self) -> None:
        """Text without credentials, secrets, or socket paths should remain intact."""
        plain = "psql: table 'tickets' already exists, skipping creation"
        assert scrub_error(plain) == plain

    def test_handles_empty_or_blank_input(self) -> None:
        """Empty string input returns empty string without error."""
        assert scrub_error("") == ""

    def test_scrub_before_truncate_preserves_boundary_secrets(self) -> None:
        """Secrets crossing or beyond the 2000-character boundary must not be resurrected by truncation."""
        secret_token = "s3cr3t_token_at_boundary_98765"
        # Place URI credential starting at position 1980, so truncation at 2000 would cut mid-credential
        prefix = "error_log_line: " * 123  # > 1950 chars
        raw = f"{prefix}postgresql://user:{secret_token}@aws-0.pooler.supabase.com:5432/app"
        assert len(raw) > 2000

        # Truncate-first (the historical flaw):
        flawed_truncate_first = scrub_error(raw[:2000])
        # Scrub-first (the hardened behavior):
        hardened_scrub_first = scrub_error(raw)[:2000]

        # In scrub-first, credentials are completely scrubbed before length truncation
        assert secret_token not in hardened_scrub_first
        assert "***:***@" in hardened_scrub_first
        # In flawed truncate-first, the secret was truncated before '@', leaking user info or secret prefix
        assert hardened_scrub_first != flawed_truncate_first

    def test_run_psql_migration_scrubs_before_truncating_stderr(self) -> None:
        """apply_staging_migration.run_psql_migration must scrub full stderr before truncating to 2000 chars."""
        secret = "super_secret_boundary_pass_999"
        # Construct stderr where credential ends after char 2000 in raw form,
        # but the replacement '***:***@' fits within the 2000 character limit.
        prefix = "A" * 1970
        stderr = f"{prefix}postgresql://user:{secret}@pooler.supabase.com:5432/db"
        fake_proc = MagicMock(returncode=1, stderr=stderr, stdout="")

        with (
            patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://u:p@pooler.supabase.com:5432/db"}),
            patch("scripts.apply_staging_migration.subprocess.run", return_value=fake_proc),
            pytest.raises(RuntimeError) as exc_info,
        ):
            run_psql_migration(db_url="postgresql://u:p@pooler.supabase.com:5432/db")

        msg = str(exc_info.value)
        assert secret not in msg
        # Must contain the redacted marker from scrub-before-truncate
        assert "***:***@" in msg

    def test_run_psql_migration_bounds_scrub_input_on_pathological_stderr(self) -> None:
        """run_psql_migration must bound sanitizer work so huge stderr cannot stall the failure path."""
        # Many short alphabetic lines: no URI delimiter, so the redaction regex has
        # nothing to match and would previously rescan the entire blob.
        stderr = "\n".join("a" * 200 for _ in range(20_000))
        assert len(stderr) > STDERR_LOG_LIMIT * 10
        fake_proc = MagicMock(returncode=1, stderr=stderr, stdout="")

        start = time.perf_counter()
        with (
            patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://u:p@pooler.supabase.com:5432/db"}),
            patch("scripts.apply_staging_migration.subprocess.run", return_value=fake_proc),
            pytest.raises(RuntimeError) as exc_info,
        ):
            run_psql_migration(db_url="postgresql://u:p@pooler.supabase.com:5432/db")
        elapsed = time.perf_counter() - start

        msg = str(exc_info.value)
        assert elapsed < 2.0, f"failure path took {elapsed:.3f}s on {len(stderr)} chars of stderr"
        assert len(msg) < STDERR_LOG_LIMIT + 200
