"""PR3 5.2 RED: guild-scope inventory + migration 015 parity inventory (read-only, no DDL)."""

from __future__ import annotations

from pathlib import Path


class TestGuildScopeInventory:
    def test_guild_scope_gaps_enumerates_id_only_methods(self) -> None:
        """Inventory MUST flag ID-only DB methods as guild-scope gaps."""
        from bot.services.schema_inventory import GUILD_SCOPE_GAPS

        # At least the core ticket ID-only methods must be present.
        core_required = {
            "get_ticket",
            "get_ticket_by_channel",
            "update_ticket",
            "get_tickets_by_parent",
        }
        assert core_required.issubset(set(GUILD_SCOPE_GAPS))
        # Category/note/audit family must also be represented.
        assert "get_ticket_category" in GUILD_SCOPE_GAPS
        assert "delete_ticket_category" in GUILD_SCOPE_GAPS
        assert "insert_ticket_note" in GUILD_SCOPE_GAPS or "get_ticket_notes" in GUILD_SCOPE_GAPS

    def test_guild_scope_gaps_includes_category_note_audit_families(self) -> None:
        """Category / note / audit ID-only families MUST be inventoried."""
        from bot.services.schema_inventory import GUILD_SCOPE_GAPS

        gaps = set(GUILD_SCOPE_GAPS)
        assert any("category" in m.lower() for m in gaps), "category methods missing from gaps"
        assert any("note" in m.lower() for m in gaps), "note methods missing from gaps"
        assert any("audit" in m.lower() for m in gaps), "audit methods missing from gaps"

    def test_inventory_helpers_exist(self) -> None:
        """SchemaInventory MUST expose helper to classify a method as gap."""
        from bot.services.schema_inventory import is_guild_scope_gap

        assert is_guild_scope_gap("get_ticket") is True
        assert is_guild_scope_gap("get_ticket_by_number") is False
        assert is_guild_scope_gap("get_guild") is False


class TestMigration015ParityInventory:
    def test_015_migration_file_exists(self) -> None:
        """Migration 015 file MUST exist on disk (parity inventory)."""
        path = Path("migrations/015_ticket_lifecycle_reliability.sql")
        assert path.exists(), f"{path} not found"
        text = path.read_text(encoding="utf-8")
        assert len(text.strip()) > 0

    def test_015_defines_unique_guild_ticket_number(self) -> None:
        """Migration 015 MUST define unique (guildId, ticketNumber)."""
        path = Path("migrations/015_ticket_lifecycle_reliability.sql")
        sql = path.read_text(encoding="utf-8")
        normalized = " ".join(sql.lower().split())
        assert "create unique index if not exists idx_ticket_guild_ticket_number" in normalized
        assert '("guildid", "ticketnumber")' in normalized

    def test_schema_inventory_reports_015_parity(self) -> None:
        """SchemaInventory MUST report 015 parity without applying DDL."""
        from bot.services.schema_inventory import SchemaInventory

        inv = SchemaInventory.build()
        # build() is read-only, no DDL — should return an object with 015 facts.
        assert hasattr(inv, "migration_015_filename")
        assert inv.migration_015_filename == "015_ticket_lifecycle_reliability.sql"
        assert hasattr(inv, "migration_015_defines_unique_guild_ticket_number")
        assert inv.migration_015_defines_unique_guild_ticket_number is True
        assert "CREATE" not in inv.ddl_statements and "ALTER" not in inv.ddl_statements


class TestReadOnlyInventoryContract:
    def test_schema_inventory_cdc_and_ttl_documented(self) -> None:
        """Inventory MUST document CDC 4 tables and TTL 300s/30s."""
        from bot.services.schema_inventory import CDC_TABLES, LEADERBOARD_TTL_SECONDS, TTL_SECONDS

        assert set(CDC_TABLES) == {"guild", "greeting_config", "ticket", "ticket_note"}
        assert TTL_SECONDS == 300
        assert LEADERBOARD_TTL_SECONDS == 30

    def test_schema_inventory_fk_retention_policy(self) -> None:
        """ticket_note CASCADE vs ticket_audit SET NULL MUST be documented."""
        from bot.services.schema_inventory import FK_RETENTION

        assert FK_RETENTION["ticket_note"] == "CASCADE"
        assert FK_RETENTION["ticket_audit"] == "SET NULL"

    def test_schema_inventory_unused_indexes_flagged(self) -> None:
        """12 unused indexes MUST be flagged for review (no DDL)."""
        from bot.services.schema_inventory import UNUSED_INDEXES_FOR_REVIEW

        assert len(UNUSED_INDEXES_FOR_REVIEW) == 12
        # At least the duplicate ticket-number index must be flagged.
        assert "idx_ticket_guild_number" in UNUSED_INDEXES_FOR_REVIEW

    def test_schema_inventory_no_ddl(self) -> None:
        """SchemaInventory MUST be read-only — no DDL statements."""
        from bot.services.schema_inventory import SchemaInventory

        inv = SchemaInventory.build()
        assert inv.no_ddl is True
        assert inv.ddl_statements == ""
