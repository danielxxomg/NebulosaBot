"""PR3 5.1 RED: service_role validation + RLS negative tests (mock-only, no live creds)."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.database import Database

# ---------------------------------------------------------------------------
# helpers — fake JWTs
# ---------------------------------------------------------------------------


def _fake_jwt(role: str) -> str:
    """Return a minimal unsigned JWT with the given role claim."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.fake-signature"


SERVICE_ROLE_JWT = _fake_jwt("service_role")
ANON_JWT = _fake_jwt("anon")
AUTHENTICATED_JWT = _fake_jwt("authenticated")
PUBLISHABLE_KEY = "sb_publishable_fake1234567890"


# 9 public tables that are RLS-enabled with no policies (exploration.md)
RLS_TABLES: tuple[str, ...] = (
    "guild",
    "member",
    "infraction",
    "ticket",
    "ticket_category",
    "economy_config",
    "greeting_config",
    "ticket_note",
    "ticket_audit",
)


# ---------------------------------------------------------------------------
# 5.1a — Database.connect() fail-closed on non-service_role
# ---------------------------------------------------------------------------


class TestServiceRoleConnect:
    @pytest.mark.asyncio
    async def test_service_role_connect_succeeds_with_valid_key(self) -> None:
        """Database.connect() MUST succeed when key is verifiable service_role."""
        from bot.core.db.base import ServiceRoleValidationError  # noqa: F401  # ensure symbol exists

        db = Database(url="https://test.supabase.co", key=SERVICE_ROLE_JWT)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "1"}]
        mock_client.table.return_value.select.return_value.limit.return_value.execute = AsyncMock(
            return_value=mock_response
        )
        secret = "s3-guard-secret-32bytes-strong-123456"
        with patch.dict("os.environ", {"SUPABASE_JWT_SECRET": secret}):
            import jwt as pyjwt  # type: ignore[import-untyped]

            # Re-sign with the same secret so PyJWT verification passes
            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            db._key = signed  # type: ignore[attr-defined]
            with patch("bot.core.db.base.acreate_client", return_value=mock_client):
                await db.connect()
            assert db._client is mock_client

    @pytest.mark.asyncio
    async def test_service_role_connect_fails_closed_with_anon_key(self) -> None:
        """Database.connect() MUST raise ServiceRoleValidationError for anon key."""
        from bot.core.db.base import ServiceRoleValidationError

        db = Database(url="https://test.supabase.co", key=ANON_JWT)
        with pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    @pytest.mark.asyncio
    async def test_service_role_connect_fails_closed_with_authenticated_key(self) -> None:
        """Database.connect() MUST raise for authenticated role."""
        from bot.core.db.base import ServiceRoleValidationError

        db = Database(url="https://test.supabase.co", key=AUTHENTICATED_JWT)
        with pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    @pytest.mark.asyncio
    async def test_service_role_connect_fails_closed_with_missing_key(self) -> None:
        """Database.connect() MUST fail-closed when key is empty."""
        from bot.core.db.base import ServiceRoleValidationError

        db = Database(url="https://test.supabase.co", key="")
        with pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    @pytest.mark.asyncio
    async def test_service_role_connect_fails_closed_with_publishable_key(self) -> None:
        """Database.connect() MUST fail-closed for publishable key."""
        from bot.core.db.base import ServiceRoleValidationError

        db = Database(url="https://test.supabase.co", key=PUBLISHABLE_KEY)
        with pytest.raises(ServiceRoleValidationError):
            await db.connect()
        assert db._client is None

    def test_service_role_validation_rejects_anon_jwt(self) -> None:
        """validate_service_role_key helper MUST reject anon JWT."""
        from bot.core.db.base import ServiceRoleValidationError, validate_service_role_key

        with pytest.raises(ServiceRoleValidationError):
            validate_service_role_key(ANON_JWT)

    def test_service_role_validation_accepts_service_role_jwt(self) -> None:
        """validate_service_role_key helper MUST accept verified service_role JWT."""
        from bot.core.db.base import validate_service_role_key

        secret = "s3-guard-secret-32bytes-strong-123456"
        import os

        os.environ["SUPABASE_JWT_SECRET"] = secret
        try:
            import jwt as pyjwt  # type: ignore[import-untyped]

            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            validate_service_role_key(signed)
        finally:
            os.environ.pop("SUPABASE_JWT_SECRET", None)

    def test_service_role_validation_helper_via_config(self) -> None:
        """BotConfig layer MUST also validate service_role via helper."""
        from bot.config import ServiceRoleValidationError as ConfigError
        from bot.config import validate_supabase_key

        with pytest.raises(ConfigError):
            validate_supabase_key(ANON_JWT)
        secret = "s3-guard-secret-32bytes-strong-123456"
        import os

        os.environ["SUPABASE_JWT_SECRET"] = secret
        try:
            import jwt as pyjwt  # type: ignore[import-untyped]

            signed = pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256")
            validate_supabase_key(signed)
        finally:
            os.environ.pop("SUPABASE_JWT_SECRET", None)


# ---------------------------------------------------------------------------
# 5.1b — RLS negative: anon client denied on all 9 tables
# ---------------------------------------------------------------------------


class TestRlsAnonDenied:
    @pytest.mark.parametrize("table", RLS_TABLES)
    def test_rls_anon_denied_on_9_tables(self, table: str) -> None:
        """Any direct anon/publishable query to 9 tables MUST be denied."""
        from bot.services.schema_inventory import is_rls_denied_for_anon

        assert is_rls_denied_for_anon(table, role="anon") is True
        assert is_rls_denied_for_anon(table, role="authenticated") is True

    def test_rls_service_role_not_denied(self) -> None:
        """Service_role MUST NOT be flagged as RLS-denied (it bypasses RLS)."""
        from bot.services.schema_inventory import is_rls_denied_for_anon

        for table in RLS_TABLES:
            assert is_rls_denied_for_anon(table, role="service_role") is False

    def test_rls_explicit_9_tables_contract(self) -> None:
        """Inventory MUST enumerate exactly the 9 RLS no-policy tables."""
        from bot.services.schema_inventory import RLS_NO_POLICY_TABLES

        assert set(RLS_NO_POLICY_TABLES) == set(RLS_TABLES)
        assert len(RLS_NO_POLICY_TABLES) == 9
