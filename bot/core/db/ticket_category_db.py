"""TicketCategoryDBMixin — ticket_category table operations for the Database facade."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bot.core.db.base import _unwrap

logger = logging.getLogger(__name__)


class TicketCategoryDBMixin:
    """Ticket category CRUD operations.

    Uses ``self._client`` from :class:`DatabaseBase`.
    """

    async def insert_ticket_category(
        self: Any,
        guild_id: str,
        name: str,
        emoji: str | None = None,
        description: str | None = None,
        position: int = 0,
    ) -> dict[str, Any]:
        """Insert a ticket category and return the persisted row.

        Generates a v4 UUID for the primary key. The ``created_at`` timestamp
        is set by the database default clause.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        category_id = str(uuid.uuid4())
        row = {
            "id": category_id,
            "guildId": guild_id,
            "name": name,
            "emoji": emoji,
            "description": description,
            "position": position,
            "active": True,
        }
        logger.debug("DB insert_ticket_category(%s) name=%r", category_id, name)
        response = await self._client.table("ticket_category").insert(row).execute()
        rows = _unwrap(response)
        return rows[0] if rows else {}

    async def get_ticket_categories(self: Any, guild_id: str) -> list[dict[str, Any]]:
        """Return all active ticket categories for a guild, ordered by position."""
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB get_ticket_categories(guild=%s)", guild_id)
        response = await (
            self._client.table("ticket_category")
            .select("*")
            .eq("guildId", guild_id)
            .eq("active", True)
            .order("position")
            .execute()
        )
        return _unwrap(response)

    async def get_ticket_category(self: Any, category_id: str, *, guild_id: str | None = None) -> dict[str, Any] | None:
        """Fetch a ticket category by its UUID primary key.

        Guild-scoped as ``WHERE guildId=:gid AND id=:cid`` so cross-guild
        reads return ``None``. A missing ``guild_id`` raises
        ``ValueError("guild_id required")``. Temporary ``None`` default
        preserves backward compatibility for in-flight callers — mypy will
        flag missing guild_id at call sites until they are migrated.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

        logger.debug("DB get_ticket_category(%r, guild=%s)", category_id, guild_id)
        query = self._client.table("ticket_category").select("*").eq("id", category_id).eq("guildId", guild_id)
        response = await query.execute()
        rows = _unwrap(response)
        return rows[0] if rows else None

    async def delete_ticket_category(self: Any, category_id: str, *, guild_id: str | None = None) -> None:
        """Delete a ticket category by its UUID primary key.

        Guild-scoped as ``WHERE guildId=:gid AND id=:cid`` so a foreign
        guild's category is untouched. A missing ``guild_id`` raises
        ``ValueError("guild_id required")``. Temporary ``None`` default
        preserves backward compatibility for in-flight callers.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)
        if guild_id is None:
            msg = "guild_id required"
            raise ValueError(msg)

        logger.debug("DB delete_ticket_category(%s, guild=%s)", category_id, guild_id)
        query = self._client.table("ticket_category").delete().eq("id", category_id).eq("guildId", guild_id)
        await query.execute()

    async def count_open_tickets_by_category(self: Any, guild_id: str, category_id: str) -> int:
        """Return the number of open/claimed tickets referencing *category_id*.

        Uses ``count="exact"`` to avoid fetching all rows — the server
        returns the count directly.  Scoped by *guild_id* so one guild
        cannot see another guild's ticket counts.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB count_open_tickets_by_category(%s, %s)", guild_id, category_id)
        response = await (
            self._client.table("ticket")
            .select("id", count="exact")
            .eq("guildId", guild_id)
            .eq("categoryId", category_id)
            .in_("status", ["open", "claimed"])
            .execute()
        )
        return response.count or 0

    async def update_ticket_category_field_definitions(
        self: Any,
        guild_id: str,
        category_id: str,
        field_definitions: list[dict[str, Any]],
    ) -> None:
        """Update ``fieldDefinitions`` for a ticket category, scoped by guildId and id.

        The guild scope prevents one guild from modifying another guild's
        categories even if the category ID is known.
        """
        if self._client is None:
            msg = "Database.connect() must be called first"
            raise RuntimeError(msg)

        logger.debug("DB update_ticket_category_field_definitions(guild=%s, cat=%s)", guild_id, category_id)
        await (
            self._client.table("ticket_category")
            .update({"fieldDefinitions": field_definitions})
            .eq("id", category_id)
            .eq("guildId", guild_id)
            .execute()
        )
