"""Read-only schema inventory (PR3) — no DDL.

Documents: RLS no-policy 9 tables, FK retention (CASCADE / SET NULL), CDC
4 tables, TTL 300s/30s, 12 unused indexes for review, 015 parity, and
guild-scope ID-only gaps.  Every attribute is in-memory / on-disk reading;
``ddl_statements`` stays empty and ``no_ddl`` is True.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ------------------------------------------------------------------
# Constants — read-only inventory facts (exploration.md)
# ------------------------------------------------------------------

RLS_NO_POLICY_TABLES: tuple[str, ...] = (
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

CDC_TABLES: tuple[str, ...] = (
    "guild",
    "greeting_config",
    "ticket",
    "ticket_note",
)

TTL_SECONDS: int = 300
LEADERBOARD_TTL_SECONDS: int = 30

FK_RETENTION: dict[str, str] = {
    "ticket_note": "CASCADE",
    "ticket_audit": "SET NULL",
}

# 12 unused indexes flagged by the linter — no DDL, just review list.
UNUSED_INDEXES_FOR_REVIEW: tuple[str, ...] = (
    "idx_member_guild",
    "idx_infraction_guild_target",
    "idx_ticket_guild_status",
    "idx_ticket_guild_number",
    "idx_ticket_category_guild",
    "idx_member_guild_xp",
    "idx_member_guild_coins",
    "idx_ticket_parent",
    "idx_ticket_note_ticket",
    "idx_ticket_note_created",
    "idx_ticket_audit_ticket_history",
    "idx_ticket_audit_guild_created",
)

# ID-only paths that are not directly guild-scoped (DB layer).  Services
# layer may add checks, but the DB method itself is a gap.
GUILD_SCOPE_GAPS: tuple[str, ...] = (
    "get_ticket",
    "get_ticket_by_channel",
    "update_ticket",
    "get_tickets_by_parent",
    "get_ticket_category",
    "delete_ticket_category",
    "insert_ticket_note",
    "get_ticket_notes",
    "delete_ticket_note",
    "get_recent_notes_for_dedup",
    "insert_audit_row",
    "get_audit_rows",
)


def is_rls_denied_for_anon(table: str, *, role: str) -> bool:
    """Return True iff *role* would be denied by RLS on *table*.

    With RLS enabled and no policies, anon/authenticated are denied;
    service_role bypasses RLS.
    """
    if table not in RLS_NO_POLICY_TABLES:
        return False
    if role == "service_role":
        return False
    return role in ("anon", "authenticated", "publishable")


def is_guild_scope_gap(method: str) -> bool:
    """Return True iff *method* is an inventoried ID-only gap."""
    return method in GUILD_SCOPE_GAPS


@dataclass(frozen=True, slots=True)
class SchemaInventory:
    """Read-only inventory snapshot — no DDL.

    Built from on-disk files and in-memory constants; never issues ALTER/CREATE.
    """

    # 015 parity
    migration_015_filename: str
    migration_015_defines_unique_guild_ticket_number: bool
    # General
    ddl_statements: str
    no_ddl: bool
    # Echoed constants for test convenience
    cdc_tables: tuple[str, ...]
    ttl_seconds: int
    leaderboard_ttl_seconds: int

    @classmethod
    def build(cls) -> SchemaInventory:
        """Read on-disk 015 and prove the unique index without DDL."""
        path = Path("migrations/015_ticket_lifecycle_reliability.sql")
        defines = False
        if path.exists():
            sql = path.read_text(encoding="utf-8")
            normalized = " ".join(sql.lower().split())
            defines = (
                "create unique index if not exists idx_ticket_guild_ticket_number" in normalized
                and '("guildid", "ticketnumber")' in normalized
            )
        return cls(
            migration_015_filename="015_ticket_lifecycle_reliability.sql",
            migration_015_defines_unique_guild_ticket_number=defines,
            ddl_statements="",
            no_ddl=True,
            cdc_tables=CDC_TABLES,
            ttl_seconds=TTL_SECONDS,
            leaderboard_ttl_seconds=LEADERBOARD_TTL_SECONDS,
        )
