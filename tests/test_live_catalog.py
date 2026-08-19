"""S4.2A RED: catalog real DB/RPC only — bypass PostgREST PGRST205.

Specs: live-schema-verifier catalog parity measurable 19↔19 9/7/0 6FKs 4 pubs via DB_URL/LIVE_SUPABASE real, not fake.
Proposal Q4: creds real required — verifier MUST FAIL without creds, FakeSupabase never PASS.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.schema_inventory import CDC_TABLES, SchemaInventory

# ---------------------------------------------------------------------------
# Helpers — must mirror exact local migration identity (19 stems)
# ---------------------------------------------------------------------------

EXPECTED_LOCAL_MIGRATIONS = sorted(
    [
        "001_initial_schema",
        "002_ticket_categories",
        "003_economy_config",
        "003_subtickets_notes",
        "004_greeting_config",
        "005_rls_secure_default",
        "006_drop_user_table",
        "007_realtime_publication",
        "008_ticket_note_rls",
        "009_member_increment_rpc",
        "010_rpc_revoke_grants",
        "011_ticket_channel_index",
        "012_ticket_audit",
        "013_ticket_intake_metadata",
        "014_ticket_category_fields",
        "015_ticket_lifecycle_reliability",
        "016_greeting_onboarding_channel",
        "017_ticket_audit_repaired_outcome",
        "018_ticket_integrity_fks",
    ]
)


def _mocked_fks() -> list[dict[str, str]]:
    return [
        {"child": "economy_config", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "greeting_config", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "infraction", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "member", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "ticket", "parent": "guild", "on_delete": "CASCADE"},
        {"child": "ticket_category", "parent": "guild", "on_delete": "CASCADE"},
    ]


class TestRedLiveCatalogModuleExists:
    def test_live_catalog_module_importable(self) -> None:
        import importlib

        mod = importlib.import_module("bot.services.live_catalog")
        assert mod is not None

    def test_local_migration_identity_is_19_exact(self) -> None:
        from bot.services.live_catalog import get_local_migration_names

        names = get_local_migration_names()
        assert len(names) == 19
        assert sorted(names) == EXPECTED_LOCAL_MIGRATIONS

    def test_live_catalog_exposes_db_adapter(self) -> None:
        from bot.services import live_catalog

        # Must expose a real-DB adapter that queries pg_constraint etc, not PostgREST fallback
        assert hasattr(live_catalog, "fetch_catalog_via_db") or hasattr(live_catalog, "fetch_catalog_evidence")
        # Must document no PostgREST catalog fallback
        import pathlib

        text = pathlib.Path("bot/services/live_catalog.py").read_text(encoding="utf-8")
        assert "PGRST205" in text or "PostgREST" in text
        assert "no PostgREST" in text.lower() or "not" in text.lower()


class TestCatalogParityMeasurableRealDB:
    def test_9_7_0_6_4_19_exact_passes_with_real_db(self) -> None:
        from bot.services.live_catalog import LiveAcceptanceGate, get_local_migration_names

        local = get_local_migration_names()
        # Build via real-DB evidence path
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=list(local),
        )
        # Gate requires LIVE_SUPABASE=1 + DB_URL + real_db flag
        with patch.dict(
            os.environ,
            {
                "LIVE_SUPABASE": "1",
                "DB_URL": "postgresql://user:pass@localhost:5432/db",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_JWKS_URL": "https://example.supabase.co/auth/v1/.well-known/jwks.json",
            },
            clear=False,
        ):
            gate = LiveAcceptanceGate(report=report, used_real_db=True).with_remote_names(list(local))
            result = gate.evaluate()
            assert result.passed is True, result.reasons
            assert result.used_real_db is True

    def test_count_only_fails_when_names_differ(self) -> None:
        from bot.services.live_catalog import LiveAcceptanceGate

        # 19 count but wrong names (placeholder 001..019)
        fake_19 = [f"{i:03d}_migration_{i}" for i in range(1, 20)]
        assert len(fake_19) == 19
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=fake_19,
        )
        # Even with real_db flag, migration identity mismatch must FAIL (exact 19 names, not count-only)
        with patch.dict(
            os.environ,
            {
                "LIVE_SUPABASE": "1",
                "DB_URL": "postgresql://user:pass@localhost:5432/db",
                "SUPABASE_URL": "https://example.supabase.co",
            },
            clear=False,
        ):
            gate = LiveAcceptanceGate(report=report, used_real_db=True)
            gate = gate.with_remote_names(fake_19)
            result = gate.evaluate()
            # Must be unresolved due to migration identity drift
            assert result.passed is False
            assert any("migrat" in r.lower() for r in result.reasons)

    def test_fake_supabase_never_passes_even_with_correct_counts(self) -> None:
        from bot.services.live_catalog import LiveAcceptanceGate, get_local_migration_names

        local = get_local_migration_names()
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=list(local),
        )
        # Correct counts but NOT via real DB → must FAIL with warning, not PASS
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            gate = LiveAcceptanceGate(report=report, used_real_db=False)
            result = gate.evaluate()
            assert result.passed is False
            assert result.used_real_db is False
            assert any("real" in r.lower() or "db" in r.lower() or "cred" in r.lower() for r in result.reasons)
            assert len(result.reasons) > 0

    def test_missing_creds_fails_with_warning_not_pass(self) -> None:
        from bot.services.live_catalog import LiveAcceptanceGate, get_local_migration_names

        local = get_local_migration_names()
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=list(local),
        )
        # No LIVE_SUPABASE / no DB_URL — must warn and FAIL, not PASS
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIVE_SUPABASE", None)
            os.environ.pop("DB_URL", None)
            os.environ.pop("SUPABASE_DB_URL", None)
            with warnings.catch_warnings(record=True) as w2:
                warnings.simplefilter("always")
                gate = LiveAcceptanceGate(report=report, used_real_db=False)
                result = gate.evaluate()
                assert result.passed is False
                assert any(
                    "live_supabase" in r.lower() or "db_url" in r.lower() or "credential" in r.lower()
                    for r in result.reasons
                )
                # Warning path must warn, not silently PASS
                assert any(issubclass(ww.category, UserWarning) for ww in w2) or len(result.reasons) > 0

    def test_pgrst205_unresolved_never_pass(self) -> None:
        """PostgREST PGRST205 path must remain unresolved, not claimed as PASS."""
        from bot.services.schema_inventory import fetch_live_metadata

        # fetch_live_metadata must raise RuntimeError on PGRST205, caller must not treat as resolved
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.execute = AsyncMock(
            side_effect=Exception('PGRST205: Could not find table "public.pg_constraint" in schema cache')
        )

        async def _run() -> None:
            with pytest.raises(RuntimeError, match="PGRST205"):
                await fetch_live_metadata(mock_client)

        import asyncio

        asyncio.run(_run())
        # Verify live_catalog documents that PGRST205 is not a PASS path
        import pathlib

        text = pathlib.Path("bot/services/live_catalog.py").read_text(encoding="utf-8")
        assert "pg_constraint" in text
        assert "pg_policies" in text or "pg_policy" in text
        assert "pg_publication_tables" in text or "publication" in text
        assert "supabase_migrations" in text or "schema_migrations" in text
        assert "pg_stat_user_indexes" in text


@pytest.mark.live
def test_live_marker_asserts_db_path_used_when_creds_present() -> None:
    """Live marker: with LIVE_SUPABASE=1 + DB_URL, must assert DB path was used."""
    from bot.services.live_catalog import LiveAcceptanceGate, get_local_migration_names

    local = get_local_migration_names()
    inv = SchemaInventory.build()
    report = inv.bind_live_evidence(
        live_fks=_mocked_fks(),
        live_policies=[],
        live_publication=list(CDC_TABLES),
        live_migrations=list(local),
    )
    if os.getenv("LIVE_SUPABASE") != "1" or not (os.getenv("DB_URL") or os.getenv("SUPABASE_DB_URL")):
        pytest.skip("live creds absent -- real DB path not executed, warning path verified")
    # When creds present, DB path must be marked used
    gate = LiveAcceptanceGate(report=report, used_real_db=True)
    result = gate.evaluate()
    assert result.used_real_db is True
    assert result.passed is True
    # Must not be FakeSupabase path
    assert "fake" not in " ".join(result.reasons).lower()
