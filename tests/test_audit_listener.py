"""Unit tests for bot.listeners.audit_listener — AuditListener + SentinelCog refactor.

Covers:
    - AuditListener early exits: bot messages, DM, can_log_in_channel filter
    - Each event type routes to correct LoggingService method
    - Role change detection via LoggingService
    - SentinelCog refactor: handlers call log_moderation_action (approval tests)

Strict TDD: RED phase — tests written BEFORE implementation exists.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.sentinel import SentinelCog
from bot.core.cache import TTLCache
from bot.listeners.audit_listener import AuditListener, setup, teardown
from bot.services.integrity_report import evaluate_live_preflight
from bot.services.ticket_service import TicketService

# ---------------------------------------------------------------------------
# AuditListener helpers
# ---------------------------------------------------------------------------


def make_mock_logging_service() -> MagicMock:
    """Return a mock LoggingService with all async log methods."""
    svc = MagicMock()
    svc.log_message_edit = AsyncMock()
    svc.log_message_delete = AsyncMock()
    svc.log_member_join = AsyncMock()
    svc.log_member_leave = AsyncMock()
    svc.log_member_update = AsyncMock()
    svc.log_channel_create = AsyncMock()
    svc.log_channel_delete = AsyncMock()
    svc.log_moderation_action = AsyncMock()
    svc.can_log_in_channel = MagicMock(return_value=True)
    return svc


def make_mock_message(
    message_id: int = 111,
    content: str = "test message",
    author_id: int = 222,
    author_name: str = "TestUser",
    author_bot: bool = False,
    guild_id: int = 123456789,
    channel_id: int = 555555,
    channel_name: str = "general",
) -> MagicMock:
    """Build a mock discord.Message."""
    msg = MagicMock(spec=discord.Message)
    msg.id = message_id
    msg.content = content
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.author.name = author_name
    msg.author.bot = author_bot
    msg.author.mention = f"<@{author_id}>"
    msg.guild = MagicMock(spec=discord.Guild)
    msg.guild.id = guild_id
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.name = channel_name
    return msg


def make_mock_channel(
    channel_id: int = 555555,
    name: str = "general",
    guild_id: int = 123456789,
) -> MagicMock:
    """Build a mock discord.abc.GuildChannel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.guild = MagicMock(spec=discord.Guild)
    channel.guild.id = guild_id
    return channel


def make_mock_member(
    member_id: int = 333,
    name: str = "TestUser",
    guild_id: int = 123456789,
    role_names: tuple[str, ...] = ("Member",),
) -> MagicMock:
    """Build a mock discord.Member with roles."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.name = name
    member.mention = f"<@{member_id}>"
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = guild_id
    member.roles = []
    for rname in role_names:
        role = MagicMock()
        role.name = rname
        member.roles.append(role)
    return member


# ---------------------------------------------------------------------------
# AuditListener Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_logging() -> MagicMock:
    """Mock LoggingService for AuditListener."""
    return make_mock_logging_service()


@pytest.fixture
def mock_bot(mock_logging: MagicMock) -> MagicMock:
    """Mock NebulosaBot with logging_service."""
    bot = MagicMock(spec=commands.Bot)
    bot.logging_service = mock_logging
    bot.user = MagicMock()
    bot.user.id = 999999999
    return bot


@pytest.fixture
def listener(mock_bot: MagicMock) -> commands.Cog:
    """Create an AuditListener with mocked bot.

    Module is imported dynamically since the file does not exist yet (RED phase).
    """

    return AuditListener(mock_bot)


# ---------------------------------------------------------------------------
# AuditListener: on_message_edit early exits
# ---------------------------------------------------------------------------


class TestOnMessageEditEarlyExits:
    """Bot + DM + channel filter early exits for on_message_edit."""

    @pytest.mark.asyncio
    async def test_skip_bot_messages(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Bot-authored message edits must be skipped."""
        before = make_mock_message(author_bot=True, author_id=888)
        after = make_mock_message(author_bot=True, author_id=888, content="edited")

        await listener.on_message_edit(before, after)  # type: ignore[union-attr]

        mock_logging.log_message_edit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_dm_messages(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """DM message edits (no guild) must be skipped."""
        before = make_mock_message()
        before.guild = None
        after = make_mock_message()
        after.guild = None

        await listener.on_message_edit(before, after)  # type: ignore[union-attr]

        mock_logging.log_message_edit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_when_channel_not_loggable(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Messages in channels invisible to @everyone must be skipped."""
        mock_logging.can_log_in_channel.return_value = False
        before = make_mock_message()
        after = make_mock_message(content="edited")

        await listener.on_message_edit(before, after)  # type: ignore[union-attr]

        mock_logging.log_message_edit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_log_message_edit_on_valid_message(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Valid guild message edit must call log_message_edit with correct args."""
        before = make_mock_message(content="original")
        after = make_mock_message(content="edited")

        await listener.on_message_edit(before, after)  # type: ignore[union-attr]

        mock_logging.log_message_edit.assert_awaited_once_with(
            "123456789",
            before,
            after,
        )


# ---------------------------------------------------------------------------
# AuditListener: on_message_delete early exits
# ---------------------------------------------------------------------------


class TestOnMessageDeleteEarlyExits:
    """Bot + DM early exits for on_message_delete."""

    @pytest.mark.asyncio
    async def test_skip_bot_messages(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Bot-authored message deletes must be skipped."""
        message = make_mock_message(author_bot=True, author_id=888)

        await listener.on_message_delete(message)  # type: ignore[union-attr]

        mock_logging.log_message_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_dm_messages(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """DM message deletes (no guild) must be skipped."""
        message = make_mock_message()
        message.guild = None

        await listener.on_message_delete(message)  # type: ignore[union-attr]

        mock_logging.log_message_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_log_message_delete_on_valid_message(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Valid guild message delete must call log_message_delete with correct args."""
        message = make_mock_message(content="deleted content")

        await listener.on_message_delete(message)  # type: ignore[union-attr]

        mock_logging.log_message_delete.assert_awaited_once_with(
            "123456789",
            message,
        )


# ---------------------------------------------------------------------------
# AuditListener: on_member_update
# ---------------------------------------------------------------------------


class TestOnMemberUpdate:
    """Member update listener — delegates role diff to LoggingService."""

    @pytest.mark.asyncio
    async def test_calls_log_member_update(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Member update must delegate to log_member_update.

        Role diff is handled internally by LoggingService.log_member_update.
        The listener always calls the service for guild members.
        """
        before = make_mock_member(role_names=("Member",))
        after = make_mock_member(role_names=("Member", "Moderator"))

        await listener.on_member_update(before, after)  # type: ignore[union-attr]

        mock_logging.log_member_update.assert_awaited_once_with(
            "123456789",
            before,
            after,
        )

    @pytest.mark.asyncio
    async def test_calls_log_member_update_even_when_roles_unchanged(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Even if roles are unchanged, the listener delegates.

        LoggingService handles the no-op internally — the listener
        does not duplicate role-diff logic.
        """
        before = make_mock_member(role_names=("Member",))
        after = make_mock_member(role_names=("Member",))

        await listener.on_member_update(before, after)  # type: ignore[union-attr]

        # Listener always calls — LoggingService decides whether to send.
        mock_logging.log_member_update.assert_awaited_once_with(
            "123456789",
            before,
            after,
        )


# ---------------------------------------------------------------------------
# AuditListener: on_member_join
# ---------------------------------------------------------------------------


class TestOnMemberJoin:
    """Member join listener — delegates to log_member_join."""

    @pytest.mark.asyncio
    async def test_skip_bot_members(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Bot member joins must be skipped."""
        member = make_mock_member(member_id=888, name="BotUser")
        member.bot = True

        await listener.on_member_join(member)  # type: ignore[union-attr]

        mock_logging.log_member_join.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_log_member_join_on_valid_member(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Valid member join must call log_member_join with correct args."""
        member = make_mock_member(member_id=333, name="NewUser")
        member.bot = False

        await listener.on_member_join(member)  # type: ignore[union-attr]

        mock_logging.log_member_join.assert_awaited_once_with(
            "123456789",
            member,
        )


# ---------------------------------------------------------------------------
# AuditListener: on_member_remove
# ---------------------------------------------------------------------------


class TestOnMemberRemove:
    """Member leave listener — delegates to log_member_leave."""

    @pytest.mark.asyncio
    async def test_skip_bot_members(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Bot member leaves must be skipped."""
        member = make_mock_member(member_id=888, name="BotUser")
        member.bot = True

        await listener.on_member_remove(member)  # type: ignore[union-attr]

        mock_logging.log_member_leave.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_log_member_leave_on_valid_member(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Valid member leave must call log_member_leave with correct args."""
        member = make_mock_member(member_id=444, name="LeavingUser")
        member.bot = False

        await listener.on_member_remove(member)  # type: ignore[union-attr]

        mock_logging.log_member_leave.assert_awaited_once_with(
            "123456789",
            member,
        )


# ---------------------------------------------------------------------------
# AuditListener: on_guild_channel_create / delete
# ---------------------------------------------------------------------------


class TestOnGuildChannelCreate:
    """Channel creation listener."""

    @pytest.mark.asyncio
    async def test_calls_log_channel_create(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Channel creation must call log_channel_create with correct args."""
        channel = make_mock_channel(name="new-channel")

        await listener.on_guild_channel_create(channel)  # type: ignore[union-attr]

        mock_logging.log_channel_create.assert_awaited_once_with(
            "123456789",
            channel,
        )


class TestOnGuildChannelDelete:
    """Channel deletion listener."""

    @pytest.mark.asyncio
    async def test_calls_log_channel_delete(
        self,
        listener: commands.Cog,
        mock_logging: MagicMock,
    ) -> None:
        """Channel deletion must call log_channel_delete with correct args."""
        channel = make_mock_channel(name="deleted-channel")

        await listener.on_guild_channel_delete(channel)  # type: ignore[union-attr]

        mock_logging.log_channel_delete.assert_awaited_once_with(
            "123456789",
            channel,
        )


# ---------------------------------------------------------------------------
# product-artifact-audit PR4 — on_guild_channel_delete repair routing (task 4.1)
# ---------------------------------------------------------------------------


class TestChannelDeleteRepairRouting:
    """on_guild_channel_delete routes matching active tickets to the coordinator.

    The listener preserves deletion logging AND supplies guild/channel facts
    to the shared repair path. It performs no direct mutation itself and never
    fabricates an authorizing actor (the gateway event carries no audit-log
    actor); a matching ticket MAY be closed through TicketService's
    evidence-gated repair path — that sanctioned close-via-service behavior
    must be documented honestly (cycle-5 S3.7), not denied.
    """

    def test_docstring_documents_sanctioned_close_via_service_honestly(self) -> None:
        """The listener docstring must not deny the coordinator-driven close.

        The delegated repair path transitions matching active tickets to
        closed — claiming the flow 'NEVER mutates ticket state' is false.
        """
        doc = inspect.getdoc(AuditListener.on_guild_channel_delete) or ""
        # Whitespace-normalized so a line wrap cannot hide the denied phrase.
        flat = " ".join(doc.split())
        assert "NEVER mutates ticket state" not in flat, (
            "docstring denies real service-side close behavior — rewrite it honestly"
        )
        # Honest documentation: names the coordinator and its repair outcome.
        assert "handle_channel_delete" in flat or "TicketService" in flat

    @pytest.fixture
    def repair_bot(self, mock_logging: MagicMock) -> MagicMock:
        """A bot with logging_service + ticket_service (coordinator delegate)."""
        bot = MagicMock(spec=commands.Bot)
        bot.logging_service = mock_logging
        bot.user = MagicMock()
        bot.user.id = 999999999
        bot.ticket_service = MagicMock()
        bot.ticket_service.handle_channel_delete = AsyncMock(return_value=None)
        return bot

    @pytest.fixture
    def repair_listener(self, repair_bot: MagicMock) -> commands.Cog:

        return AuditListener(repair_bot)

    @pytest.mark.asyncio
    async def test_channel_delete_logs_and_delegates_facts(
        self,
        repair_listener: commands.Cog,
        repair_bot: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """A deleted channel is logged AND its (guild, channel) facts are routed."""
        channel = make_mock_channel(channel_id=555555, name="ticket-0001")

        await repair_listener.on_guild_channel_delete(channel)  # type: ignore[union-attr]

        mock_logging.log_channel_delete.assert_awaited_once_with("123456789", channel)
        assert repair_bot.ticket_service.handle_channel_delete.await_count == 1
        await_args, await_kwargs = repair_bot.ticket_service.handle_channel_delete.call_args
        assert await_args[0] == "123456789"
        assert await_args[1] == "555555"
        assert "preflight" in await_kwargs

    @pytest.mark.asyncio
    async def test_channel_delete_never_mutates_directly(
        self,
        repair_listener: commands.Cog,
        repair_bot: MagicMock,
    ) -> None:
        """The listener holds no DB/transition access — mutation flows only
        through the coordinator delegate."""
        channel = make_mock_channel(channel_id=555555, name="ticket-0001")

        await repair_listener.on_guild_channel_delete(channel)  # type: ignore[union-attr]

        assert not hasattr(repair_listener, "db")
        assert repair_bot.ticket_service.handle_channel_delete.await_count == 1

    @pytest.mark.asyncio
    async def test_channel_delete_without_ticket_service_logs_only(
        self,
        mock_logging: MagicMock,
    ) -> None:
        """When the ticket_service is absent, deletion still logs and never raises."""
        bot = MagicMock(spec=commands.Bot)
        bot.logging_service = mock_logging
        bot.user = MagicMock()
        bot.user.id = 999999999
        # ticket_service intentionally unset.

        listener = AuditListener(bot)
        channel = make_mock_channel(name="general")

        await listener.on_guild_channel_delete(channel)

        mock_logging.log_channel_delete.assert_awaited_once_with("123456789", channel)


# ---------------------------------------------------------------------------
# PR3 — TestAuthoritativeChannelDeletePR3: resolved channel-delete through real listener
# ---------------------------------------------------------------------------


class TestAuthoritativeChannelDeletePR3:
    """Resolved channel-delete repair is reachable through the real AuditListener."""

    @pytest.mark.asyncio
    async def test_resolved_preflight_reaches_conditional_close(self) -> None:
        """G.2 resolved + active ticket -> handle_channel_delete with resolved preflight repairs."""

        db = AsyncMock()
        row = {"id": "t-1", "guildId": "123", "channelId": "555", "status": "open"}
        db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        db.transition_ticket_to_closed = AsyncMock(return_value={**row, "status": "closed"})
        db.insert_audit_row = AsyncMock(return_value={})
        svc = TicketService(db=db, cache=TTLCache())
        bot = MagicMock()
        bot.ticket_service = svc
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            observed_at=datetime.now(UTC).isoformat(),
        )
        bot.live_preflight = lambda: preflight
        listener = AuditListener(bot)
        channel = make_mock_channel(channel_id=555, name="ticket-0001")
        channel.guild.id = 123
        await listener.on_guild_channel_delete(channel)
        db.transition_ticket_to_closed.assert_awaited_once()
        assert db.transition_ticket_to_closed.call_args.kwargs["close_reason"] == "zombie:channel_deleted"

    @pytest.mark.asyncio
    async def test_gate_unresolved_is_fail_closed_no_mutation(self) -> None:
        """G.2 unresolved -> no conditional close, but deletion logging preserved."""

        db = AsyncMock()
        row = {"id": "t-1", "guildId": "123", "channelId": "555", "status": "open"}
        db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        db.transition_ticket_to_closed = AsyncMock(return_value={**row, "status": "closed"})
        db.insert_audit_row = AsyncMock(return_value={})
        svc = TicketService(db=db, cache=TTLCache())
        bot = MagicMock()
        bot.ticket_service = svc
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        # no live_preflight -> unresolved
        listener = AuditListener(bot)
        channel = make_mock_channel(channel_id=555, name="ticket-0001")
        channel.guild.id = 123
        await listener.on_guild_channel_delete(channel)
        db.transition_ticket_to_closed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_two_resolved_events_one_repaired_one_already_closed(self) -> None:
        """Two concurrent resolved deletes -> one repaired, one already_closed."""

        db = AsyncMock()
        row = {"id": "t-1", "guildId": "123", "channelId": "555", "status": "open"}
        db.get_active_ticket_by_channel = AsyncMock(return_value=row)
        db.transition_ticket_to_closed = AsyncMock(side_effect=[{**row, "status": "closed"}, None])
        db.insert_audit_row = AsyncMock(return_value={})
        svc = TicketService(db=db, cache=TTLCache())
        bot = MagicMock()
        bot.ticket_service = svc
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        preflight = evaluate_live_preflight(
            project_status="ACTIVE_HEALTHY",
            migration_015_applied=True,
            close_reason_nullable=True,
            required_indexes_present=True,
            realtime_publication_covers=["guild", "greeting_config", "ticket", "ticket_note"],
            observed_at=datetime.now(UTC).isoformat(),
        )
        bot.live_preflight = lambda: preflight
        listener = AuditListener(bot)
        channel = make_mock_channel(channel_id=555, name="ticket-0001")
        channel.guild.id = 123
        await asyncio.gather(listener.on_guild_channel_delete(channel), listener.on_guild_channel_delete(channel))
        assert db.transition_ticket_to_closed.await_count == 2
        # Strengthened: exactly one repaired close and one already_closed no-op via service harnesses
        db2 = AsyncMock()
        db2.get_active_ticket_by_channel = AsyncMock(return_value=row)
        db2.transition_ticket_to_closed = AsyncMock(side_effect=[{**row, "status": "closed"}, None])
        db2.insert_audit_row = AsyncMock(return_value={})
        svc2 = TicketService(db=db2, cache=TTLCache())
        r1, r2 = await asyncio.gather(
            svc2.handle_channel_delete("123", "555", preflight=preflight),
            svc2.handle_channel_delete("123", "555", preflight=preflight),
        )
        assert {r.outcome for r in (r1, r2)} == {"repaired", "already_closed"}  # type: ignore[union-attr]
        assert {r.action for r in (r1, r2)} == {"close", "no_op"}  # type: ignore[union-attr]
        # Exact audit contracts: one repaired, one already_closed denied
        assert db2.insert_audit_row.await_count == 2
        outcomes = [
            c.args[4] if len(c.args) > 4 else c.kwargs.get("outcome") for c in db2.insert_audit_row.call_args_list
        ]
        assert "repaired" in outcomes
        assert "denied" in outcomes

    @pytest.mark.asyncio
    async def test_cross_guild_lookup_is_isolated(self) -> None:
        """Cross-guild channel delete does not leak tickets across guilds."""

        db = AsyncMock()
        # No ticket in this guild
        db.get_active_ticket_by_channel = AsyncMock(return_value=None)
        svc = TicketService(db=db, cache=TTLCache())
        bot = MagicMock()
        bot.ticket_service = svc
        bot.logging_service = MagicMock()
        bot.logging_service.log_channel_delete = AsyncMock()
        bot.user = MagicMock()
        listener = AuditListener(bot)
        channel = make_mock_channel(channel_id=999, name="other")
        channel.guild.id = 999
        await listener.on_guild_channel_delete(channel)
        db.transition_ticket_to_closed.assert_not_awaited()


# ---------------------------------------------------------------------------
# SentinelCog Refactor — Approval Tests
# ---------------------------------------------------------------------------


class TestSentinelCogUsesLoggingService:
    """Approval tests: verify SentinelCog calls logging_service after refactor.

    These tests document current behavior (via _log_action) and will
    transition to verifying log_moderation_action after the refactor.
    """

    @pytest.fixture
    def sentinel_bot(self) -> MagicMock:
        """Build a mock NebulosaBot with enough services for SentinelCog."""
        bot = MagicMock(spec=commands.Bot)
        bot.user = MagicMock()
        bot.user.id = 999999999

        # logging_service will be set by the refactor
        bot.logging_service = make_mock_logging_service()

        # mock guild_service for _validate_target checks
        bot.guild_service = MagicMock()
        bot.guild_service.get_config = AsyncMock()
        bot_config = MagicMock()
        bot_config.log_enabled = True
        bot_config.log_channel_id = "999999999"
        bot.guild_service.get_config.return_value = bot_config

        # infraction_service
        bot.infraction_service = MagicMock()
        bot.infraction_service.warn = AsyncMock()
        infraction_mock = MagicMock()
        infraction_mock.id = 1
        infraction_mock.action = None  # No escalation
        bot.infraction_service.warn.return_value = (infraction_mock, None)

        # db
        bot.db = MagicMock()
        bot.db.insert_infraction = AsyncMock()

        # get_channel (for _log_action fallback in current code)
        log_channel = MagicMock()
        log_channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=log_channel)

        return bot

    @pytest.fixture
    def sentinel_cog(self, sentinel_bot: MagicMock) -> SentinelCog:
        """Create a SentinelCog with mocked bot for refactor approval."""
        return SentinelCog(sentinel_bot)

    @pytest.mark.asyncio
    async def test_warn_handler_calls_log_moderation_action(
        self,
        sentinel_cog: SentinelCog,
        sentinel_bot: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After refactor, /warn must call logging_service.log_moderation_action.

        This is an APPROVAL test: it will FAIL (RED) until _log_action()
        is replaced with logging_service.log_moderation_action().
        """
        # Bypass _validate_target for this focused test — we want to verify
        # the log call path, not the full validation chain.
        monkeypatch.setattr(sentinel_cog, "_validate_target", AsyncMock(return_value=True))

        ctx = MagicMock(spec=commands.Context)
        ctx.send = AsyncMock()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.id = 111111111
        ctx.author.guild_permissions.administrator = True
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 123456789

        target = MagicMock(spec=discord.Member)
        target.id = 222222222
        target.mention = "<@222222222>"
        target.name = "BadUser"
        target.timeout = AsyncMock()
        target.kick = AsyncMock()

        reason = "Spamming"

        await sentinel_cog.warn.callback(sentinel_cog, ctx, target, reason=reason)

        # RED: this assertion will FAIL because SentinelCog currently
        # uses _log_action() instead of logging_service.log_moderation_action.
        sentinel_bot.logging_service.log_moderation_action.assert_awaited_once_with(
            "123456789",
            "Warn",
            target,
            ctx.author,
            reason,
        )


# ---------------------------------------------------------------------------
# cog setup function
# ---------------------------------------------------------------------------


class TestAuditListenerSetup:
    """Verify the extension can be loaded."""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self, mock_bot: MagicMock) -> None:
        """setup() must add AuditListener as a cog."""
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_awaited_once()
        added_cog = mock_bot.add_cog.call_args[0][0]
        assert added_cog._logging is mock_bot.logging_service

    @pytest.mark.asyncio
    async def test_teardown_removes_cog(self, mock_bot: MagicMock) -> None:
        """teardown() must remove the AuditListener cog."""
        mock_bot.remove_cog = AsyncMock()

        await teardown(mock_bot)

        mock_bot.remove_cog.assert_awaited_once_with("AuditListener")
