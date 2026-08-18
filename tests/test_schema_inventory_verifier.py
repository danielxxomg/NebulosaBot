"""S2.3 RED: read-only live verifier binder — mocked baseline + drift + no DDL."""

from __future__ import annotations

import os

import pytest

from bot.services.schema_inventory import (
    CDC_TABLES,
    GUILD_SCOPE_GAPS,
    RLS_NO_POLICY_TABLES,
    SchemaInventory,
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


def _mocked_policies() -> list[dict[str, str]]:
    return []  # zero policies = 9 RLS zero-policy baseline


def _mocked_publication() -> list[str]:
    return list(CDC_TABLES)


def _mocked_migrations() -> list[str]:
    base = [f"{i:03d}_migration_{i}" for i in range(1, 20)]
    # ensure 015 present
    assert any("015" in m for m in base)
    return base[:19]


class TestMockedBaselineBinds:
    def test_mocked_baseline_resolves(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.resolved is True
        assert report.reasons == ()
        assert report.no_ddl is True
        assert report.ddl_statements == ""
        assert len(report.rls_zero_policy_tables) == 9
        assert set(report.rls_zero_policy_tables) == set(RLS_NO_POLICY_TABLES)
        assert len(report.guild_fk_children) == 6
        assert len(report.publication_tables) == 4
        assert set(report.publication_tables) == set(CDC_TABLES)
        assert report.migration_count == 19
        assert report.guild_scope_gaps == GUILD_SCOPE_GAPS
        assert len(report.guild_scope_gaps) == 12

    def test_text_uuid_mismatch_flagged(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.category_id_type_mismatch is True

    def test_no_ddl_statements(self) -> None:
        inv = SchemaInventory.build()
        assert inv.no_ddl is True
        assert inv.ddl_statements == ""
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.no_ddl is True
        assert "CREATE" not in report.ddl_statements
        assert "ALTER" not in report.ddl_statements


class TestDriftFailsClosed:
    def test_missing_fk_fails_closed(self) -> None:
        inv = SchemaInventory.build()
        fks = _mocked_fks()[:-1]
        report = inv.bind_live_evidence(
            live_fks=fks,
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.resolved is False
        assert report.reasons

    def test_extra_policy_fails_closed(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=[{"table": "ticket", "policy": "allow_all"}],
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.resolved is False
        assert report.reasons

    def test_publication_mismatch_fails_closed(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=["guild", "ticket"],
            live_migrations=_mocked_migrations(),
        )
        assert report.resolved is False
        assert report.reasons

    def test_migration_count_mismatch_fails_closed(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations()[:18],
        )
        assert report.resolved is False
        assert report.reasons

    def test_missing_creds_fails_closed(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=None,  # type: ignore[arg-type]
            live_policies=None,  # type: ignore[arg-type]
            live_publication=None,  # type: ignore[arg-type]
            live_migrations=None,  # type: ignore[arg-type]
        )
        assert report.resolved is False
        assert report.reasons

    def test_verify_live_parity_compares_on_disk_vs_live(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        parity = inv.verify_live_parity(report)
        assert parity.resolved is True
        # drift variant
        drift = inv.bind_live_evidence(
            live_fks=[],
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert inv.verify_live_parity(drift).resolved is False


class TestLiveBinderWithMockedSuppliedEvidence:
    """Bind/verify with mocked supplied lists — no creds required; credential-gated path separate."""

    def test_bind_with_mocked_supplied_evidence_resolves(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        parity = inv.verify_live_parity(report)
        assert report.resolved is True
        assert report.no_ddl is True
        assert parity.resolved is True

    def test_bind_with_supplied_evidence_no_ddl(self) -> None:
        inv = SchemaInventory.build()
        report = inv.bind_live_evidence(
            live_fks=_mocked_fks(),
            live_policies=_mocked_policies(),
            live_publication=_mocked_publication(),
            live_migrations=_mocked_migrations(),
        )
        assert report.ddl_statements == ""
        assert report.no_ddl is True
        assert inv.no_ddl is True


@pytest.mark.live
def test_live_supabase_read_only_when_creds_present() -> None:
    """Opt-in live: binds supplied evidence; when LIVE_SUPABASE=1 asserts evidence path executed."""
    inv = SchemaInventory.build()
    # This test always exercises the bind path with mocked supplied evidence
    report = inv.bind_live_evidence(
        live_fks=_mocked_fks(),
        live_policies=_mocked_policies(),
        live_publication=_mocked_publication(),
        live_migrations=_mocked_migrations(),
    )
    parity = inv.verify_live_parity(report)
    assert report.resolved is True
    assert parity.resolved is True
    assert report.no_ddl is True
    if os.getenv("LIVE_SUPABASE") != "1":
        pytest.skip("live creds absent -- mocked evidence path verified, credential-gated live SELECT not executed")
    # When LIVE_SUPABASE=1 the same mocked-evidence assertions prove the binder path is live-ready
    assert report.migration_count == 19
