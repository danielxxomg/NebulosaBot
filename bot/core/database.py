"""Database — Supabase client wrapper for NebulosaBot.

Provides async access to the Supabase Postgres instance with health-check,
guild-config read/write, infraction CRUD, member management, and connection
lifecycle management.

This module is a thin facade that composes domain mixins from
``bot.core.db.*``.  Existing imports (``from bot.core.database import
Database``) continue to work unchanged.
"""

from __future__ import annotations

from typing import Any

from supabase import AsyncClientOptions, acreate_client

from bot.core.db.base import DatabaseBase
from bot.core.db.economy_db import EconomyDBMixin
from bot.core.db.greeting_db import GreetingDBMixin
from bot.core.db.guild_db import GuildDBMixin
from bot.core.db.infraction_db import InfractionDBMixin
from bot.core.db.member_db import MemberDBMixin
from bot.core.db.ticket_audit_db import TicketAuditDBMixin
from bot.core.db.ticket_category_db import TicketCategoryDBMixin
from bot.core.db.ticket_db import TicketDBMixin
from bot.core.db.ticket_note_db import TicketNoteDBMixin


async def create_realtime_client(supabase_url: str, supabase_key: str) -> Any:
    """Create the async Supabase client used by the Realtime subscriber.

    Both Realtime and :class:`Database` use ``acreate_client`` (async).
    Kept as a standalone coroutine so it can be injected as the subscriber's
    ``client_factory`` without binding to a ``Database`` instance.
    """
    return await acreate_client(
        supabase_url,
        supabase_key,
        AsyncClientOptions(schema="public"),
    )


class Database(
    DatabaseBase,
    GuildDBMixin,
    MemberDBMixin,
    InfractionDBMixin,
    TicketDBMixin,
    TicketNoteDBMixin,
    TicketCategoryDBMixin,
    TicketAuditDBMixin,
    EconomyDBMixin,
    GreetingDBMixin,
):
    """Async wrapper around a Supabase Python client.

    Instantiate with the project URL and API key (anon or service_role).
    Call ``connect()`` before any data-access methods.
    """

    pass
