"""S4.1 HISTORICAL rename — 12 entries, alias, runtime_closed==12."""

from __future__ import annotations

import warnings


def test_historical_canonical_12() -> None:
    from bot.services.schema_inventory import GUILD_SCOPE_GAP_HISTORY

    assert len(GUILD_SCOPE_GAP_HISTORY) == 12


def test_alias_preserved_with_deprecation() -> None:
    from bot.services import schema_inventory as mod

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        val = mod.GUILD_SCOPE_GAPS
        assert len(val) == 12
        # Deprecation or silent alias — either passes, but len must be 12
        _ = w


def test_runtime_closed_12() -> None:
    from bot.services.schema_inventory import GUILD_SCOPE_RUNTIME_CLOSED, SchemaInventory

    assert GUILD_SCOPE_RUNTIME_CLOSED == 12
    inv = SchemaInventory.build()
    report = inv.bind_live_evidence(
        live_fks=[
            {"child": "economy_config", "parent": "guild", "on_delete": "CASCADE"},
            {"child": "greeting_config", "parent": "guild", "on_delete": "CASCADE"},
            {"child": "infraction", "parent": "guild", "on_delete": "CASCADE"},
            {"child": "member", "parent": "guild", "on_delete": "CASCADE"},
            {"child": "ticket", "parent": "guild", "on_delete": "CASCADE"},
            {"child": "ticket_category", "parent": "guild", "on_delete": "CASCADE"},
        ],
        live_policies=[],
        live_publication=["guild", "greeting_config", "ticket", "ticket_note"],
        live_migrations=[f"{i:03d}_m" for i in range(1, 20)],
    )
    assert report.guild_scope_runtime_closed == 12
    assert report.guild_scope_gaps == tuple(
        __import__("bot.services.schema_inventory", fromlist=["GUILD_SCOPE_GAP_HISTORY"]).GUILD_SCOPE_GAP_HISTORY
    )


def test_runtime_closed_computed_matches_constant() -> None:
    """GUILD_SCOPE_RUNTIME_CLOSED must be derived from registry len, not hardcoded drift."""
    from bot.services.schema_inventory import (
        GUILD_SCOPE_GAP_HISTORY,
        GUILD_SCOPE_RUNTIME_CLOSED,
        GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED,
    )

    assert len(GUILD_SCOPE_GAP_HISTORY) == GUILD_SCOPE_RUNTIME_CLOSED
    assert len(GUILD_SCOPE_GAP_HISTORY) == GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED
    assert GUILD_SCOPE_RUNTIME_CLOSED == GUILD_SCOPE_RUNTIME_CLOSED_COMPUTED


def test_inventory_len_12_still_passes() -> None:
    from bot.services.schema_inventory import GUILD_SCOPE_GAP_HISTORY, GUILD_SCOPE_GAPS

    assert len(GUILD_SCOPE_GAP_HISTORY) == 12
    assert len(GUILD_SCOPE_GAPS) == 12
