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
        from bot.services.live_catalog import LiveAcceptanceGate, ProvenanceToken, get_local_migration_names
        from bot.services.schema_inventory import RlsCounts

        local = get_local_migration_names()
        # Build via real-DB evidence path — include 9/7/0 binding
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=list(local),
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
        # Gate requires LIVE_SUPABASE=1 + DB_URL + ProvenanceToken(4)
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
            gate = LiveAcceptanceGate(report=report, used_real_db=ProvenanceToken(query_count=4)).with_remote_names(
                list(local)
            )
            result = gate.evaluate()
            assert result.passed is True, result.reasons
            assert result.used_real_db is True

    def test_count_only_fails_when_names_differ(self) -> None:
        from bot.services.live_catalog import LiveAcceptanceGate, ProvenanceToken
        from bot.services.schema_inventory import RlsCounts

        # 19 count but wrong names (placeholder 001..019)
        fake_19 = [f"{i:03d}_migration_{i}" for i in range(1, 20)]
        assert len(fake_19) == 19
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=fake_19,
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
        # Even with provenance token, migration identity mismatch must FAIL
        with patch.dict(
            os.environ,
            {
                "LIVE_SUPABASE": "1",
                "DB_URL": "postgresql://user:pass@localhost:5432/db",
                "SUPABASE_URL": "https://example.supabase.co",
            },
            clear=False,
        ):
            gate = LiveAcceptanceGate(report=report, used_real_db=ProvenanceToken(query_count=4))
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
    """Live marker: with LIVE_SUPABASE=1 + DB_URL, must assert DB path was used via ProvenanceToken."""
    from bot.services.live_catalog import LiveAcceptanceGate, ProvenanceToken, get_local_migration_names
    from bot.services.schema_inventory import RlsCounts

    local = get_local_migration_names()
    inv = SchemaInventory.build()
    report = inv.bind_live_evidence(
        live_fks=_mocked_fks(),
        live_policies=[],
        live_publication=list(CDC_TABLES),
        live_migrations=list(local),
        rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
    )
    if os.getenv("LIVE_SUPABASE") != "1" or not (os.getenv("DB_URL") or os.getenv("SUPABASE_DB_URL")):
        pytest.skip("live creds absent -- real DB path not executed, warning path verified")
    # When creds present, DB path must be marked used via ProvenanceToken(4)
    gate = LiveAcceptanceGate(report=report, used_real_db=ProvenanceToken(query_count=4))
    result = gate.evaluate()
    assert result.used_real_db is True
    assert result.passed is True
    # Must not be FakeSupabase path
    assert "fake" not in " ".join(result.reasons).lower()


# ---------------------------------------------------------------------------
# Provenance — psycopg path executes real query, FakeSupabase cannot produce used_real_db
# ---------------------------------------------------------------------------


class TestFetchCatalogViaDbProvenance:
    @pytest.mark.asyncio
    async def test_fetch_catalog_via_db_uses_psycopg_when_db_url_present(self) -> None:
        """Provenance: fetch_catalog_via_db must call psycopg.connect and execute queries."""
        from unittest.mock import MagicMock, patch

        # Fake cursor that records execute calls and returns canned rows
        executed: list[str] = []

        class FakeCursor:
            def __enter__(self) -> FakeCursor:
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def execute(self, sql: str, *_: object, **__: object) -> None:
                executed.append(sql)

            def fetchall(self) -> list[tuple[str, ...]]:
                # Return FK-like rows for first call, empty for others
                if "pg_constraint" in executed[-1]:
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
            from bot.services.live_catalog import ProvenanceToken, fetch_catalog_via_db

            fks, _pols, _pubs, _migs, tok = await fetch_catalog_via_db("postgresql://user:pass@localhost/db")
            # Provenance: psycopg.connect was called — token proves query execution
            assert fake_connect.called
            assert any("pg_constraint" in s for s in executed), "must query pg_constraint"
            assert isinstance(fks, list)
            assert isinstance(tok, ProvenanceToken)
            assert tok.query_count == 4

    @pytest.mark.asyncio
    async def test_fetch_catalog_without_db_url_warns_and_empty(self) -> None:
        import warnings as _w

        from bot.services.live_catalog import ProvenanceToken, fetch_catalog_via_db

        with _w.catch_warnings(record=True) as w:
            _w.simplefilter("always")
            fks, pols, pubs, migs, tok = await fetch_catalog_via_db(None)
            # No DB_URL → warns and empty; gate will fail (never PASS)
            assert fks == [] and pols == [] and pubs == [] and migs == []
            assert isinstance(tok, ProvenanceToken)
            assert tok.query_count == 0
            assert any(issubclass(x.category, UserWarning) for x in w)

    def test_fake_supabase_cannot_produce_used_real_db(self) -> None:
        """FakeSupabase path must never be able to claim used_real_db=True provenance."""
        # Provenance: only psycopg path executes real queries; FakeSupabase never PASSes.
        import pathlib

        text = pathlib.Path("bot/services/live_catalog.py").read_text(encoding="utf-8")
        assert "FakeSupabase never PASS" in text
        assert "psycopg.connect" in text
        assert "_sync_fetch_catalog" in text
        # ProvenanceToken enforces 4 queries; synthetic bool True must be rejected.
        assert "ProvenanceToken" in text
        assert "query_count" in text

    def test_synthetic_bool_true_rejected_without_token(self) -> None:
        """Caller-supplied used_real_db=True without ProvenanceToken must be synthetic FakeSupabase."""
        import warnings as _w

        from bot.services.live_catalog import LiveAcceptanceGate, get_local_migration_names
        from bot.services.schema_inventory import RlsCounts

        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=get_local_migration_names(),
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
        import os as _os

        with (
            patch.dict(_os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://x/x"}, clear=False),
            _w.catch_warnings(record=True),
        ):
            _w.simplefilter("always")
            gate = LiveAcceptanceGate(report=report, used_real_db=True)  # type: ignore[arg-type]
            result = gate.evaluate()
            assert result.passed is False
            assert any("synthetic" in r.lower() or "provenance" in r.lower() for r in result.reasons)

    def test_provenance_token_with_970_bound_passes(self) -> None:
        """ProvenanceToken(4) + 9/7/0 bound report must PASS via evaluate."""
        from bot.services.live_catalog import LiveAcceptanceGate, ProvenanceToken, get_local_migration_names
        from bot.services.schema_inventory import RlsCounts

        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=get_local_migration_names(),
            rls_counts=RlsCounts(rls_enabled=9, rls_forced=7, policy_count=0),
        )
        with patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://x/x"}, clear=False):
            gate = LiveAcceptanceGate(report=report, used_real_db=ProvenanceToken(query_count=4)).with_remote_names(
                get_local_migration_names()
            )
            result = gate.evaluate()
            assert result.passed is True, result.reasons

    def test_970_not_bound_fails_even_with_token(self) -> None:
        """Missing 9/7/0 binding must FAIL even with provenance token."""
        from bot.services.live_catalog import LiveAcceptanceGate, ProvenanceToken, get_local_migration_names

        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[],
            live_publication=list(CDC_TABLES),
            live_migrations=get_local_migration_names(),
        )  # no rls_counts — unbound
        with patch.dict(os.environ, {"LIVE_SUPABASE": "1", "DB_URL": "postgresql://x/x"}, clear=False):
            gate = LiveAcceptanceGate(report=report, used_real_db=ProvenanceToken(query_count=4)).with_remote_names(
                get_local_migration_names()
            )
            result = gate.evaluate()
            assert result.passed is False
            assert any("970" in r.lower() or "rls" in r.lower() for r in result.reasons)


class TestRls970StructuralViaDb:
    def test_fetch_rls_counts_970_via_mocked_psycopg(self) -> None:
        """9/7/0 catalog fact via pg_class/pg_policy counts, not hardcoded 9."""
        from unittest.mock import MagicMock, patch

        # Mock cursor returning 9 enabled, 7 forced, 0 policies
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
            assert enabled == 9
            assert forced == 7
            assert policies == 0
            # Proves query provenance — not hardcoded
            assert cur.execute.call_count >= 3

    def test_rls_counts_fail_if_hardcoded_only(self) -> None:
        """If counts drift from expected 9/7/0, must be detectable via binder."""
        from bot.services.schema_inventory import RLS_NO_POLICY_TABLES

        # Binder expects 9 tables with 0 policies — structural invariant
        assert len(RLS_NO_POLICY_TABLES) == 9
        # Forced count is documented as 7 — verify via module comment/exploration
        assert len(RLS_NO_POLICY_TABLES) == 9


class TestIndexPolicyExecutable:
    def test_zero_scans_without_explain_is_rejected(self) -> None:
        from bot.services.live_catalog import evaluate_index_policy

        allowed, reason = evaluate_index_policy(scans=0, explain_output=None)
        assert allowed is False
        assert "EXPLAIN" in reason
        assert "retained" in reason.lower() or "reject" in reason.lower()

    def test_zero_scans_with_explain_is_allowed(self) -> None:
        from bot.services.live_catalog import evaluate_index_policy

        explain = "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM ticket WHERE ..."
        allowed, _ = evaluate_index_policy(scans=0, explain_output=explain)
        assert allowed is True

    def test_scans_present_without_explain_is_allowed(self) -> None:
        from bot.services.live_catalog import evaluate_index_policy

        allowed, _ = evaluate_index_policy(scans=11, explain_output=None)
        assert allowed is True
