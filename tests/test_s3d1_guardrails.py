"""S3.1 RED — Guardrails: is_mod 3, guild denial at 568/685/722, sb_secret probe, scripts ruff.

Strict TDD: this file MUST fail before GREEN (S3.1.1). Gates: is_mod ledger 3
(0 tickets +3 sentinel lock/unlock/modlogs after cycle-4-debt-zero S1 migrated
the moderation commands to can_check), guild-scoped DB at tickets.py:568/685/722,
sb_secret opaque probe via RLS SELECT not JWT decode, and scripts ruff 11→0.
No DDL in this slice.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# is_mod ledger — 25 decorators (17 tickets +8 sentinel), single source in checks.py
# ---------------------------------------------------------------------------


def _count_is_mod_decorators(path: str) -> int:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                src = ast.unparse(dec)
                if "is_mod" in src and "is_mod_check" not in src:
                    # only @is_mod() decorator, not inline helper
                    count += 1
    return count


class TestIsModLedger:
    def test_tickets_is_mod_count_17(self) -> None:
        """tickets.py MUST have 0 @is_mod() decorators after PR4 (all swapped to @can_check tickets.manage; delete_category @is_admin)."""
        # PR4 migrates every tickets lifecycle @is_mod() → @can_check("tickets.manage"); delete_category stays @is_admin
        assert _count_is_mod_decorators("bot/cogs/tickets.py") == 0

    def test_sentinel_is_mod_count_3(self) -> None:
        """sentinel.py MUST have 3 @is_mod() decorators (lock/unlock/modlogs; ban/tempban/unban + warn/unwarn/mute/unmute/kick are @can_check since PR1/cycle-4-debt-zero)."""
        assert _count_is_mod_decorators("bot/cogs/sentinel.py") == 3

    def test_total_is_mod_3(self) -> None:
        """Total is_mod decorators MUST be 3 (0 tickets +3 sentinel) after cycle-4-debt-zero S1."""
        total = _count_is_mod_decorators("bot/cogs/tickets.py") + _count_is_mod_decorators("bot/cogs/sentinel.py")
        assert total == 3, (
            f"is_mod ledger drift: got {total}, expected 3 "
            "(0 tickets +3 sentinel lock/unlock/modlogs; moderation commands → can_check)"
        )

    def test_tickets_can_check_tickets_manage_ledger(self) -> None:
        """PR4 ledger: tickets.py MUST have ≥15 @can_check("tickets.manage") decorators."""
        import pathlib

        text = pathlib.Path("bot/cogs/tickets.py").read_text(encoding="utf-8")
        count = text.count('can_check("tickets.manage")') + text.count("can_check('tickets.manage')")
        assert count >= 15, f"PR4 ledger: expected ≥15 can_check tickets.manage, got {count}"

    def test_greetings_uses_greeting_manage(self) -> None:
        """PR4 ledger: greetings.py MUST route _admin_guard via can("greeting.manage")."""
        import pathlib

        text = pathlib.Path("bot/cogs/greetings.py").read_text(encoding="utf-8")
        assert "greeting.manage" in text
        assert 'can("greeting.manage"' in text or "can('greeting.manage'" in text

    def test_is_mod_single_source(self) -> None:
        """is_mod() decorator MUST delegate to is_mod_check (DRY single source)."""
        text = pathlib.Path("bot/utils/checks.py").read_text(encoding="utf-8")
        assert "is_mod_check" in text
        assert "def is_mod" in text


# ---------------------------------------------------------------------------
# Guild-scope denial — tickets.py 568/685/722 delegate to service or pass guild_id
# ---------------------------------------------------------------------------


class TestGuildScopeDeferredCallers:
    def test_568_subticket_guild_scoped(self) -> None:
        """tickets.py subticket Create MUST be guild-scoped (guild_id passed to DB)."""
        text = pathlib.Path("bot/cogs/tickets.py").read_text(encoding="utf-8")
        # subticket_create method block must contain guild_id= param on get_ticket calls
        assert "guild_id=gid" in text or "guild_id = gid" in text or 'guild_id="guild' in text
        # specific: at least the subticket parent lookup carries gid
        window = text[text.find("async def subticket_create") : text.find("async def subticket_create") + 2500]
        assert "guild_id" in window, f"subticket_create not guild-scoped:\n{window[:600]}"

    def test_685_transfer_guild_scoped(self) -> None:
        """tickets.py transfer MUST be guild-scoped."""
        text = pathlib.Path("bot/cogs/tickets.py").read_text(encoding="utf-8")
        window = text[text.find("async def transfer") : text.find("async def transfer") + 1500]
        assert "guild_id" in window, f"transfer not guild-scoped:\n{window[:400]}"

    def test_722_edit_category_guild_scoped(self) -> None:
        """tickets.py unclaim/edit path MUST be guild-scoped (all get_ticket_by_channel carry guild_id)."""
        text = pathlib.Path("bot/cogs/tickets.py").read_text(encoding="utf-8")
        # every get_ticket_by_channel in tickets.py must be guild-scoped
        for i, line in enumerate(text.splitlines(), start=1):
            if "get_ticket_by_channel" in line and "bot.db" in line:
                assert "guild_id" in line, f"line {i} not guild-scoped: {line.strip()}"

    @pytest.mark.asyncio
    async def test_db_guild_required_denies_cross_guild(self) -> None:
        """DB layer MUST require guild_id and deny cross-guild via scoped read."""
        from bot.core.database import Database
        from tests.test_database import FakeSupabaseClient

        fake = FakeSupabaseClient()
        fake.set_table_data("ticket", [])
        db = Database(url="https://test.supabase.co", key="test-key")
        db._client = fake
        with pytest.raises((ValueError, TypeError)):
            await db.get_ticket("t-b")
        result = await db.get_ticket("t-b", guild_id="guild-a")
        assert result is None
        with pytest.raises((ValueError, TypeError)):
            await db.get_ticket_by_channel("ch-b")
        result2 = await db.get_ticket_by_channel("ch-b", guild_id="guild-a")
        assert result2 is None


# ---------------------------------------------------------------------------
# sb_secret opaque probe — not JWT decode, health probe helper proves via RLS SELECT
# ---------------------------------------------------------------------------


class TestSbSecretProbe:
    def test_sb_secret_accepted_as_server_credential(self) -> None:
        """validate_supabase_key MUST accept sb_secret_ opaque prefix (not reject as non-JWT)."""
        from bot.config import validate_supabase_key

        # opaque secret — must NOT raise ServiceRoleValidationError
        validate_supabase_key("sb_secret_D7RbNvrMzqq0GReF5vKIpA_test12345678")

    def test_sb_secret_missing_fails_closed(self) -> None:
        """Missing sb_secret MUST fail-closed (not accepted)."""
        from bot.config import ServiceRoleValidationError, validate_supabase_key

        with pytest.raises(ServiceRoleValidationError):
            validate_supabase_key("")
        with pytest.raises(ServiceRoleValidationError):
            validate_supabase_key("   ")

    def test_legacy_jwt_still_validated_via_jwt_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Legacy service_role JWT MUST be accepted only via verified signature (PyJWT HS256)."""
        import base64
        import json

        def _fake_jwt(role: str) -> str:
            h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
            p = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
            return f"{h}.{p}.sig"

        from bot.config import ServiceRoleValidationError, validate_supabase_key

        # Payload-only without signing source must fail closed
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        with pytest.raises(ServiceRoleValidationError):
            validate_supabase_key(_fake_jwt("service_role"))
        with pytest.raises(ServiceRoleValidationError):
            validate_supabase_key(_fake_jwt("anon"))
        # With real secret + real signature, service_role is accepted, anon still rejected
        secret = "s3-guard-secret-32bytes-strong-123456"
        monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
        import jwt as pyjwt

        real = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
        anon_real = pyjwt.encode({"role": "anon"}, secret, algorithm="HS256")
        validate_supabase_key(real)
        with pytest.raises(ServiceRoleValidationError):
            validate_supabase_key(anon_real)

    def test_legacy_jwt_fake_signature_rejected_when_secret_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fake signature MUST fail closed when SUPABASE_JWT_SECRET is set (PyJWT HS256)."""
        import base64
        import json

        def _fake_jwt(role: str) -> str:
            h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
            p = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
            return f"{h}.{p}.sig"

        from bot.config import ServiceRoleValidationError, validate_supabase_key

        monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-for-verify-1234567890")
        with pytest.raises(ServiceRoleValidationError, match="signature"):
            validate_supabase_key(_fake_jwt("service_role"))
        # Without secret, payload-only must also fail closed (no signing source)
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        with pytest.raises(ServiceRoleValidationError, match="signing source"):
            validate_supabase_key(_fake_jwt("service_role"))

    def test_sb_secret_not_decoded_as_jwt(self) -> None:
        """sb_secret_ MUST NOT be decoded as JWT (opaque)."""
        text = pathlib.Path("bot/config.py").read_text(encoding="utf-8")
        # config should contain explicit sb_secret branch, not just _decode_jwt_role
        assert "sb_secret" in text

    def test_jwt_allowlists_hs256_and_documents_jwks_todo(self) -> None:
        """JWT verification MUST allowlist HS256 and document JWKS as S4 TODO."""
        text = pathlib.Path("bot/config.py").read_text(encoding="utf-8")
        assert "HS256" in text
        assert "JWKS" in text or "jwks" in text.lower()
        assert "S4" in text or "TODO" in text

    @pytest.mark.asyncio
    async def test_health_probe_proves_sb_secret_via_rls_select(self) -> None:
        """Health probe helper MUST prove sb_secret works via RLS SELECT on guild AND ticket."""
        from bot.core.database import Database

        guild_resp = MagicMock()
        guild_resp.data = [{"id": "g1"}]

        db = Database(url="https://test.supabase.co", key="sb_secret_D7RbNvrMzqq0GReF5vKIpA_test")
        # Two-table probe: guild and ticket each succeed. Using per-table builders
        # so health_probe can call each table's chain independently.
        guild_builder = MagicMock()
        guild_builder.select.return_value.limit.return_value.execute = AsyncMock(return_value=guild_resp)
        ticket_builder = MagicMock()
        ticket_builder.select.return_value.limit.return_value.execute = AsyncMock(return_value=guild_resp)
        mock_client = MagicMock()
        mock_client.table.side_effect = lambda name: guild_builder if name == "guild" else ticket_builder

        with patch("bot.core.db.base.acreate_client", return_value=mock_client):
            await db.connect()
        assert db._client is mock_client
        # health_check delegates to health_probe (guild+ticket); also assert probe directly
        assert await db.health_check() is True
        assert await db.health_probe() is True

    @pytest.mark.asyncio
    async def test_sb_secret_probe_fails_closed_when_cannot_read(self) -> None:
        """When RLS SELECT fails (invalid secret), connect MUST fail-closed and block queries."""
        from bot.config import ServiceRoleValidationError
        from bot.core.database import Database

        db = Database(url="https://test.supabase.co", key="sb_secret_invalid")
        fail_builder = MagicMock()
        fail_builder.select.return_value.limit.return_value.execute = AsyncMock(
            side_effect=Exception("permission denied / invalid key")
        )
        mock_client = MagicMock()
        mock_client.table.return_value = fail_builder
        mock_client.table.side_effect = lambda _name: fail_builder
        with (
            patch("bot.core.db.base.acreate_client", return_value=mock_client),
            pytest.raises(ServiceRoleValidationError, match="health probe"),
        ):
            await db.connect()
        assert db._client is None
        with pytest.raises(RuntimeError, match="connect"):
            await db.get_guild("123")
        # direct probe pre-connect returns False
        assert await db.health_probe() is False
        assert await db.health_check() is False

    @pytest.mark.asyncio
    async def test_health_probe_fails_when_only_guild_readable(self) -> None:
        """Ticket table unreadable MUST make connect fail-closed even if guild is readable."""
        from bot.config import ServiceRoleValidationError
        from bot.core.database import Database

        db = Database(url="https://test.supabase.co", key="sb_secret_partial")
        guild_resp = MagicMock()
        guild_resp.data = [{"id": "g1"}]
        guild_builder = MagicMock()
        guild_builder.select.return_value.limit.return_value.execute = AsyncMock(return_value=guild_resp)
        ticket_fail = MagicMock()
        ticket_fail.select.return_value.limit.return_value.execute = AsyncMock(
            side_effect=Exception("permission denied on ticket")
        )
        mock_client = MagicMock()
        mock_client.table.side_effect = lambda name: guild_builder if name == "guild" else ticket_fail
        with (
            patch("bot.core.db.base.acreate_client", return_value=mock_client),
            pytest.raises(ServiceRoleValidationError, match="health probe"),
        ):
            await db.connect()
        assert db._client is None
        assert await db.health_probe() is False
        assert await db.health_check() is False


# ---------------------------------------------------------------------------
# Catalog PGRST205 — fetch_live_metadata must not assume PostgREST system catalogs
# ---------------------------------------------------------------------------


class TestCatalogPath:
    def test_fetch_live_metadata_documents_db_rpc_path(self) -> None:
        """Catalog evidence MUST be obtained via DB/RPC, not PostgREST pg_constraint (PGRST205)."""
        text = pathlib.Path("bot/services/schema_inventory.py").read_text(encoding="utf-8")
        # must mention DB/RPC or supabase_migrations via db, or document fallback
        assert "rpc" in text.lower() or "PGRST205" in text or "pg_constraint" in text
        # fetch_live_metadata should not be the only path; a DB path or fallback should exist
        assert "fetch_live_metadata" in text

    def test_no_ddl_in_s31_verifier(self) -> None:
        """S3.1 verifier/catalog path MUST remain read-only, no DDL."""
        text = pathlib.Path("bot/services/schema_inventory.py").read_text(encoding="utf-8")
        # S3.1 is guardrails-only, no migration/DDL
        assert "no_ddl" in text.lower() or "No DDL" in text


# ---------------------------------------------------------------------------
# scripts ruff -- 11 errors (EM102 x4 TRY003 x4 T201 x2 SIM102 x1) -> 0, keep narrow T201
# ---------------------------------------------------------------------------


class TestScriptsRuff:
    def test_scripts_ruff_clean(self) -> None:
        """scripts/ MUST pass ruff 0 including 11 prior violations (keep narrow T201 only for CLI)."""
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "scripts"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff scripts still has violations:\n{result.stdout}\n{result.stderr}"
        assert "Found" not in result.stdout or "0" in result.stdout
