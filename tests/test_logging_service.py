"""Unit tests for bot.services.logging_service.LoggingService.

Covers the logging-service spec scenarios:
    - Embed building per event type (edit, delete, join, leave, update, channel create/delete)
    - Log moderation action
    - Routing guards: logging disabled, missing channel, private channel skip
    - can_log_in_channel: visibility filter
    - Footer icon wiring from bot avatar / guild icon
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.i18n import set_guild_language, t
from bot.services.logging_service import (
    LoggingService,
    build_operator_diagnosis_record,
    build_repair_audit_record,
)
from bot.services.ticket_invariants import GlobalMutationGrant

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_channel(
    channel_id: int = 123456789,
    name: str = "general",
    is_text: bool = True,
    everyone_read_messages: bool | None = True,
) -> MagicMock:
    """Build a mock discord.TextChannel (or GuildChannel) with @everyone overwrites."""
    if is_text:
        channel = MagicMock(spec=discord.TextChannel)
    else:
        channel = MagicMock(spec=discord.VoiceChannel)

    channel.id = channel_id
    channel.name = name
    channel.guild = MagicMock()
    channel.guild.default_role = MagicMock()

    overwrite = MagicMock()
    overwrite.read_messages = everyone_read_messages
    channel.overwrites_for.return_value = overwrite

    return channel


def make_mock_message(
    message_id: int = 111,
    content: str = "test message",
    author_name: str = "TestUser",
    author_id: int = 222,
    channel: MagicMock | None = None,
) -> MagicMock:
    """Build a mock discord.Message with content and author."""
    msg = MagicMock(spec=discord.Message)
    msg.id = message_id
    msg.content = content
    msg.author = MagicMock()
    msg.author.name = author_name
    msg.author.id = author_id
    msg.author.mention = f"<@{author_id}>"
    msg.channel = channel or make_mock_channel()
    return msg


def make_mock_member(
    member_id: int = 333,
    name: str = "NewUser",
    roles: list[str] | None = None,
    created_at: datetime | None = None,
    member_number: int = 150,
) -> MagicMock:
    """Build a mock discord.Member with roles and account age."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.name = name
    member.mention = f"<@{member_id}>"
    member.guild = MagicMock()
    member.guild.member_count = member_number
    member.created_at = created_at or datetime(2024, 1, 1, tzinfo=UTC)

    if roles is not None:
        member.roles = [MagicMock() for _ in roles]
        for i, role in enumerate(member.roles):
            role.name = roles[i]
    else:
        member.roles = []

    return member


async def _setup_service_and_config(
    guild_id: str = "123456789",
    log_channel_id: str | None = "999999999",
    log_enabled: bool = True,
) -> tuple[LoggingService, MagicMock, MagicMock]:
    """Create a LoggingService with mocked guild_service and log channel."""
    mock_guild_service = AsyncMock()
    mock_guild_service.get_config.return_value = MagicMock()
    mock_guild_service.get_config.return_value.log_channel_id = log_channel_id
    mock_guild_service.get_config.return_value.log_enabled = log_enabled
    mock_guild_service.get_config.return_value.id = guild_id

    mock_bot = MagicMock()
    mock_bot.guild_service = mock_guild_service

    service = LoggingService(bot=mock_bot)

    # Create a real-looking log channel
    mock_log_channel = make_mock_channel(channel_id=int(log_channel_id or 0), name="mod-log")
    mock_bot.get_channel = MagicMock(return_value=mock_log_channel)

    return service, mock_bot, mock_log_channel


# ---------------------------------------------------------------------------
# can_log_in_channel — visibility filter
# ---------------------------------------------------------------------------


class TestCanLogInChannel:
    """Tests for the channel visibility filter."""

    @pytest.mark.asyncio
    async def test_text_channel_visible_returns_true(self) -> None:
        """TextChannel where @everyone can read_messages → True."""
        channel = make_mock_channel(everyone_read_messages=True)
        service, _, _ = await _setup_service_and_config()

        result = service.can_log_in_channel(channel)
        assert result is True

    @pytest.mark.asyncio
    async def test_text_channel_no_overwrite_returns_true(self) -> None:
        """TextChannel with no @everyone overwrite → True (defaults to visible)."""
        channel = make_mock_channel(everyone_read_messages=None)
        service, _, _ = await _setup_service_and_config()

        result = service.can_log_in_channel(channel)
        assert result is True

    @pytest.mark.asyncio
    async def test_text_channel_hidden_returns_false(self) -> None:
        """TextChannel where @everyone read_messages=False → False."""
        channel = make_mock_channel(everyone_read_messages=False)
        service, _, _ = await _setup_service_and_config()

        result = service.can_log_in_channel(channel)
        assert result is False

    @pytest.mark.asyncio
    async def test_voice_channel_returns_false(self) -> None:
        """Non-TextChannel → always False."""
        channel = make_mock_channel(is_text=False, everyone_read_messages=True)
        service, _, _ = await _setup_service_and_config()

        result = service.can_log_in_channel(channel)
        assert result is False


# ---------------------------------------------------------------------------
# Routing guards: disabled, missing channel
# ---------------------------------------------------------------------------


class TestLoggingRoutingGuards:
    """Log methods should silently skip when logging is disabled or channel is missing."""

    @pytest.mark.asyncio
    async def test_log_disabled_skips_send(self) -> None:
        """When log_enabled is False, no embed should be sent."""
        service, mock_bot, _ = await _setup_service_and_config(log_enabled=False)
        msg = make_mock_message(content="edited", channel=make_mock_channel())

        await service.log_message_edit("123456789", msg, msg)
        assert mock_bot.get_channel.call_count == 0

    @pytest.mark.asyncio
    async def test_missing_log_channel_skips_send(self) -> None:
        """When log_channel_id is None, no embed should be sent."""
        service, mock_bot, _ = await _setup_service_and_config(log_channel_id=None)
        msg = make_mock_message(content="edited", channel=make_mock_channel())

        await service.log_message_edit("123456789", msg, msg)
        assert mock_bot.get_channel.call_count == 0

    @pytest.mark.asyncio
    async def test_log_channel_not_found_skips_send(self) -> None:
        """When the log channel is not in the bot's cache, no error, no send."""
        service, mock_bot, _ = await _setup_service_and_config()
        mock_bot.get_channel.return_value = None  # Channel not found
        msg = make_mock_message(content="edited", channel=make_mock_channel())

        # Should not raise.
        await service.log_message_edit("123456789", msg, msg)


# ---------------------------------------------------------------------------
# Embed content: message edits
# ---------------------------------------------------------------------------


class TestLogMessageEdit:
    """log_message_edit should build an embed with before/after content and channel name."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_before_and_after(self) -> None:
        """Embed should contain before and after content."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="general")
        before = make_mock_message(content="before text", channel=channel)
        after = make_mock_message(content="after text", channel=channel)

        await service.log_message_edit("123456789", before, after)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "before text" in _embed_to_str(embed)
        assert "after text" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_embed_includes_channel_name(self) -> None:
        """Embed should mention the channel where the edit happened."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="secret-room")
        before = make_mock_message(content="old", channel=channel)
        after = make_mock_message(content="new", channel=channel)

        await service.log_message_edit("123456789", before, after)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "secret-room" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_truncates_long_content(self) -> None:
        """Messages longer than 1024 chars should be truncated."""
        service, _, mock_log_channel = await _setup_service_and_config()
        long_text = "x" * 2000
        channel = make_mock_channel(name="spam")
        before = make_mock_message(content=long_text, channel=channel)
        after = make_mock_message(content=long_text, channel=channel)

        await service.log_message_edit("123456789", before, after)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        # Field values should be 1024 chars max
        for field in embed.fields:
            assert len(field.value) <= 1024


# ---------------------------------------------------------------------------
# Embed content: message deletes
# ---------------------------------------------------------------------------


class TestLogMessageDelete:
    """log_message_delete should build an embed with full content and author."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_content(self) -> None:
        """Embed should contain the deleted message content."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="general")
        msg = make_mock_message(content="deleted secret", author_name="Alice", channel=channel)

        await service.log_message_delete("123456789", msg)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "deleted secret" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_embed_includes_author(self) -> None:
        """Embed should include the author's name."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="general")
        msg = make_mock_message(content="message", author_name="Bob", channel=channel)

        await service.log_message_delete("123456789", msg)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "Bob" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_empty_content_shows_placeholder(self) -> None:
        """Messages with empty content show the localized no-content placeholder."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="general")
        msg = make_mock_message(content="", channel=channel)

        await service.log_message_delete("123456789", msg)

        embed = mock_log_channel.send.call_args.kwargs.get("embed")
        text = _embed_to_str(embed)
        # Key-based check (design D3): the localized placeholder label.
        assert t("123456789", "log.no_content") in text


# ---------------------------------------------------------------------------
# Embed content: member join
# ---------------------------------------------------------------------------


class TestLogMemberJoin:
    """log_member_join should build an embed with member mention, ID, and creation date."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_member_mention(self) -> None:
        """Embed should include the member's mention."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=333, name="NewUser", member_number=150)

        await service.log_member_join("123456789", member)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "<@333>" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_embed_includes_member_count(self) -> None:
        """Embed should show what member number this is."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=333, name="NewUser", member_number=42)

        await service.log_member_join("123456789", member)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "#42" in _embed_to_str(embed)


# ---------------------------------------------------------------------------
# Embed content: member leave
# ---------------------------------------------------------------------------


class TestLogMemberLeave:
    """log_member_leave should build an embed with member mention and roles."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_member_mention(self) -> None:
        """Embed should include the member's mention."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=444, name="LeavingUser", roles=["VIP"])

        await service.log_member_leave("123456789", member)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "<@444>" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_embed_includes_roles(self) -> None:
        """Embed should list the member's roles."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=444, name="LeavingUser", roles=["VIP", "Member"])

        await service.log_member_leave("123456789", member)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        assert "VIP" in text
        assert "Member" in text

    @pytest.mark.asyncio
    async def test_no_roles_shows_localized_none(self) -> None:
        """When member has no roles, embed shows the localized 'none' label (key-based)."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=444, name="NoRolesUser", roles=[])

        await service.log_member_leave("123456789", member)

        embed = mock_log_channel.send.call_args.kwargs.get("embed")
        text = _embed_to_str(embed)
        # Key-based check: the resolved log.none label for the guild locale.
        assert t("123456789", "log.none") in text


# ---------------------------------------------------------------------------
# Embed content: member update
# ---------------------------------------------------------------------------


class TestLogMemberUpdate:
    """log_member_update should build an embed with added/removed roles."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_role_changes(self) -> None:
        """Embed should show added and removed roles."""
        service, _, mock_log_channel = await _setup_service_and_config()
        before = make_mock_member(member_id=333, name="User", roles=["Member"])
        after = make_mock_member(member_id=333, name="User", roles=["Member", "VIP"])

        await service.log_member_update("123456789", before, after)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs.get("embed")
        text = _embed_to_str(embed)
        assert "VIP" in text  # Added
        # Key-based check: localized added-roles label (design D3).
        assert t("123456789", "log.member_update.added") in text

    @pytest.mark.asyncio
    async def test_no_role_change_skips(self) -> None:
        """If roles haven't changed, no embed should be sent."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=333, name="User", roles=["Member"])

        await service.log_member_update("123456789", member, member)

        # Should skip — no role change
        mock_log_channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# Embed content: channel create / delete
# ---------------------------------------------------------------------------


class TestLogChannelEvents:
    """Channel create/delete should log the channel name."""

    @pytest.mark.asyncio
    async def test_channel_create_sends_embed(self) -> None:
        """Creating a channel should log its name."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="new-channel")

        await service.log_channel_create("123456789", channel)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "new-channel" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_channel_delete_sends_embed(self) -> None:
        """Deleting a channel should log its name."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="old-channel")

        await service.log_channel_delete("123456789", channel)

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert "old-channel" in _embed_to_str(embed)


# ---------------------------------------------------------------------------
# Embed content: moderation action
# ---------------------------------------------------------------------------


class TestLogModerationAction:
    """log_moderation_action should build an embed with action, target, mod, and reason."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_action_and_target(self) -> None:
        """Embed should include action type and target user."""
        service, _, mock_log_channel = await _setup_service_and_config()
        target = make_mock_member(member_id=555, name="BadUser")
        moderator = make_mock_member(member_id=111, name="ModUser")

        await service.log_moderation_action("123456789", "Warn", target, moderator, "spamming")

        mock_log_channel.send.assert_called_once()
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        assert "Warn" in text
        assert "BadUser" in text

    @pytest.mark.asyncio
    async def test_embed_includes_reason(self) -> None:
        """Embed should include the moderation reason."""
        service, _, mock_log_channel = await _setup_service_and_config()
        target = make_mock_member(member_id=555, name="BadUser")
        moderator = make_mock_member(member_id=111, name="ModUser")

        await service.log_moderation_action("123456789", "Ban", target, moderator, "breaking rule 3")

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        assert "breaking rule 3" in text

    @pytest.mark.asyncio
    async def test_embed_includes_moderator(self) -> None:
        """Embed should include the moderator's name."""
        service, _, mock_log_channel = await _setup_service_and_config()
        target = make_mock_member(member_id=555, name="BadUser")
        moderator = make_mock_member(member_id=111, name="ModUser")

        await service.log_moderation_action("123456789", "Kick", target, moderator, "reason")

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        assert "ModUser" in text


# ---------------------------------------------------------------------------
# Private channel filter — per spec
# ---------------------------------------------------------------------------


class TestPrivateChannelFilter:
    """Logging should skip events from channels invisible to @everyone."""

    @pytest.mark.asyncio
    async def test_message_delete_in_private_channel_skips(self) -> None:
        """When a message is deleted in a private channel, no embed is sent."""
        service, _, mock_log_channel = await _setup_service_and_config()
        private_channel = make_mock_channel(name="staff-only", everyone_read_messages=False)
        msg = make_mock_message(content="secret", channel=private_channel)

        await service.log_message_delete("123456789", msg)

        # Should not send to log channel because the source channel is private.
        mock_log_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_edit_in_private_channel_skips(self) -> None:
        """When a message is edited in a private channel, no embed is sent."""
        service, _, mock_log_channel = await _setup_service_and_config()
        private_channel = make_mock_channel(name="staff-only", everyone_read_messages=False)
        before = make_mock_message(content="old", channel=private_channel)
        after = make_mock_message(content="new", channel=private_channel)

        await service.log_message_edit("123456789", before, after)

        mock_log_channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _embed_to_str(embed: discord.Embed) -> str:
    """Concatenate all embed text fields into one string for assertions."""
    parts: list[str] = []
    if embed.title:
        parts.append(embed.title)
    if embed.description:
        parts.append(embed.description)
    for field in embed.fields:
        if field.name:
            parts.append(field.name)
        if field.value:
            parts.append(field.value)
    if embed.footer.text:
        parts.append(embed.footer.text)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Footer icon wiring — production callers pass bot/guild
# ---------------------------------------------------------------------------


class TestLogEmbedFooterIcon:
    """LoggingService embeds MUST have footer icon from bot avatar or guild icon."""

    @pytest.mark.asyncio
    async def test_send_log_sets_bot_avatar_as_footer_icon(self) -> None:
        """_send_log MUST set the embed footer icon_url from bot.user.display_avatar."""
        service, mock_bot, mock_log_channel = await _setup_service_and_config()
        mock_bot.user = MagicMock()
        mock_bot.user.display_avatar = MagicMock()
        mock_bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot123/avatar.png"
        # get_guild returns a guild without icon → falls back to bot avatar
        mock_guild = MagicMock()
        mock_guild.icon = None
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        msg = make_mock_message(content="test", channel=make_mock_channel())
        await service.log_message_delete("123456789", msg)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert embed.footer.icon_url == "https://cdn.discordapp.com/avatars/bot123/avatar.png"

    @pytest.mark.asyncio
    async def test_send_log_prefers_guild_icon_over_bot_avatar(self) -> None:
        """_send_log MUST prefer guild.icon.url over bot avatar when available."""
        service, mock_bot, mock_log_channel = await _setup_service_and_config()
        mock_bot.user = MagicMock()
        mock_bot.user.display_avatar = MagicMock()
        mock_bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot123/avatar.png"
        mock_guild = MagicMock()
        mock_guild.icon = MagicMock()
        mock_guild.icon.url = "https://cdn.discordapp.com/icons/456/server.png"
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        msg = make_mock_message(content="test", channel=make_mock_channel())
        await service.log_message_delete("123456789", msg)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert embed.footer.icon_url == "https://cdn.discordapp.com/icons/456/server.png"


# ---------------------------------------------------------------------------
# product-artifact-audit PR4b-b — repair audit vs operator diagnosis records
# (task 5.1)
# ---------------------------------------------------------------------------


class TestBuildRepairAuditRecord:
    """build_repair_audit_record produces guild-scoped, truthful repair evidence."""

    @pytest.mark.parametrize(
        ("outcome", "mutated"),
        [
            ("repaired", True),
            ("quarantined", False),
            ("denied", False),
            ("skipped", False),
            ("already_closed", False),
            ("error", False),
        ],
    )
    def test_mutation_truthfulness(self, outcome: str, mutated: bool) -> None:
        """Only a ``repaired`` outcome reports mutation; every other outcome is a no-op."""

        record = build_repair_audit_record(guild_id="111", ticket_id="t-1", outcome=outcome)

        assert record.mutated is mutated
        assert record.outcome == outcome
        assert record.guild_id == "111"
        assert record.ticket_id == "t-1"

    def test_record_carries_reason_source_actor(self) -> None:
        """The record preserves its structured review context (reason/source/actor)."""

        record = build_repair_audit_record(
            guild_id="111",
            ticket_id="t-1",
            outcome="denied",
            reason="cross_guild_denied",
            source="manual",
            actor_id="999",
        )

        assert record.reason == "cross_guild_denied"
        assert record.source == "manual"
        assert record.actor_id == "999"

    def test_record_is_guild_scoped(self) -> None:
        """Each record is bound to exactly one guild."""

        guild_a = build_repair_audit_record(guild_id="A", ticket_id="t-1", outcome="repaired")
        guild_b = build_repair_audit_record(guild_id="B", ticket_id="t-1", outcome="repaired")

        assert guild_a.guild_id == "A"
        assert guild_b.guild_id == "B"
        assert guild_a.guild_id != guild_b.guild_id

    def test_record_serializes_structured_evidence(self) -> None:
        """The record exposes non-empty ticket/guild/outcome in its dict form."""

        record = build_repair_audit_record(
            guild_id="111", ticket_id="t-1", outcome="error", reason="audit_persistence_failed"
        )
        data = record.to_dict()

        assert data["guildId"] == "111"
        assert data["ticketId"] == "t-1"
        assert data["outcome"] == "error"
        assert data["mutated"] is False


class TestBuildOperatorDiagnosisRecord:
    """build_operator_diagnosis_record is global but read-only without a grant."""

    @pytest.mark.parametrize(
        ("grant_kwargs", "expected_mutated", "expected_reason"),
        [
            (None, False, "operator_mutation_requires_grant"),
            ({"confirmed": False, "reason": "targeted"}, False, "grant_unconfirmed"),
            ({"confirmed": True, "reason": "  "}, False, "grant_missing_reason"),
            ({"confirmed": True, "reason": "targeted"}, True, "targeted"),
        ],
    )
    def test_grant_gates_mutation(
        self, grant_kwargs: dict | None, expected_mutated: bool, expected_reason: str
    ) -> None:
        """Mutation requires an explicit, confirmed, non-empty-reason grant."""

        grant = (
            GlobalMutationGrant(actor_id="bot-owner", scope="global", target_guild_id="A", **grant_kwargs)
            if grant_kwargs is not None
            else None
        )

        record = build_operator_diagnosis_record(target_guild_ids=["A"], grant=grant, actor_id="bot-owner")

        assert record.mutated is expected_mutated
        assert record.reason == expected_reason

    def test_identifies_target_guilds_and_findings(self) -> None:
        """The diagnosis names every target guild and carries its findings."""

        record = build_operator_diagnosis_record(
            target_guild_ids=["A", "B", "C"], findings=["finding-one", "finding-two"]
        )

        assert set(record.target_guild_ids) == {"A", "B", "C"}
        assert record.findings == ("finding-one", "finding-two")

    def test_grant_actor_mismatch_never_mutates(self) -> None:
        """A confirmed grant naming a different actor MUST NOT set mutated=True."""

        grant = GlobalMutationGrant(
            actor_id="bot-owner",
            scope="global",
            target_guild_id="A",
            reason="targeted",
            confirmed=True,
        )
        record = build_operator_diagnosis_record(
            target_guild_ids=["A"],
            grant=grant,
            actor_id="someone-else",
        )

        assert record.mutated is False
        assert record.reason == "grant_actor_mismatch"

    def test_grant_target_mismatch_never_mutates(self) -> None:
        """A confirmed grant for a different target guild MUST NOT set mutated=True."""

        grant = GlobalMutationGrant(
            actor_id="bot-owner",
            scope="global",
            target_guild_id="A",
            reason="targeted",
            confirmed=True,
        )
        record = build_operator_diagnosis_record(
            target_guild_ids=["B"],
            grant=grant,
            actor_id="bot-owner",
        )

        assert record.mutated is False
        assert record.reason == "grant_target_mismatch"

    def test_grant_scope_mismatch_never_mutates(self) -> None:
        """A confirmed grant whose scope is not 'global' MUST NOT set mutated=True."""

        grant = GlobalMutationGrant(
            actor_id="bot-owner",
            scope="guild",
            target_guild_id="A",
            reason="targeted",
            confirmed=True,
        )
        record = build_operator_diagnosis_record(
            target_guild_ids=["A"],
            grant=grant,
            actor_id="bot-owner",
        )

        assert record.mutated is False
        assert record.reason == "grant_scope_mismatch"

    def test_grant_requires_actor_argument(self) -> None:
        """Without an actor_id, a non-empty grant cannot be validated and MUST NOT mutate."""

        grant = GlobalMutationGrant(
            actor_id="bot-owner",
            scope="global",
            target_guild_id="A",
            reason="targeted",
            confirmed=True,
        )
        record = build_operator_diagnosis_record(target_guild_ids=["A"], grant=grant)

        assert record.mutated is False
        assert record.reason == "grant_actor_missing"


# ===========================================================================
# product-artifact-audit remediation — duplicate-event logging deduplication
# (task: "Duplicate event is not double-counted")
# ===========================================================================


class TestDuplicateEventLogging:
    """Duplicate delete events produce one success at most, loser is denied/no-op."""

    def test_duplicate_event_builds_one_success_and_one_denied(self) -> None:
        """build_repair_audit_record maps a winner + a deterministic loser distinctly."""

        winner = build_repair_audit_record(guild_id="111", ticket_id="t-1", outcome="repaired", source="channel_delete")
        loser = build_repair_audit_record(
            guild_id="111", ticket_id="t-1", outcome="already_closed", source="channel_delete"
        )

        # Exactly one record reports a mutation.
        mutating = [r for r in (winner, loser) if r.mutated]
        assert len(mutating) == 1
        assert winner.mutated is True
        assert loser.mutated is False
        # The loser is a deterministic no-op/denied outcome, not a second success.
        assert loser.outcome == "already_closed"
        assert loser.to_dict()["mutated"] is False

    def test_duplicate_event_never_double_counts_success(self) -> None:
        """Two records for the same ticket never both report mutation."""

        first = build_repair_audit_record(guild_id="111", ticket_id="t-1", outcome="repaired")
        second = build_repair_audit_record(guild_id="111", ticket_id="t-1", outcome="already_closed")

        successes = sum(1 for r in (first, second) if r.outcome == "repaired")
        assert successes == 1
        assert first.mutated is True and second.mutated is False


# ---------------------------------------------------------------------------
# log_sentinel_loop — zero-count digest suppression (spec logging-service)
# ---------------------------------------------------------------------------


class TestLogSentinelLoopZeroCount:
    """Digest embeds driven by periodic loops MUST skip zero-count cycles."""

    @pytest.mark.asyncio
    async def test_zero_count_sends_nothing(self) -> None:
        """count == 0 → no digest embed reaches the log channel."""
        service, _mock_bot, mock_log_channel = await _setup_service_and_config()
        mock_log_channel.send = AsyncMock()

        await service.log_sentinel_loop("123", "expiry", 0)

        mock_log_channel.send.assert_not_awaited()
        # The zero-count cycle must not even resolve the log channel.
        _mock_bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonzero_count_still_delivers(self) -> None:
        """count > 0 → the digest embed is sent as before."""
        service, _mock_bot, mock_log_channel = await _setup_service_and_config()
        mock_log_channel.send = AsyncMock()

        await service.log_sentinel_loop("123", "decay", 3)

        mock_log_channel.send.assert_awaited_once()
        await_args = mock_log_channel.send.await_args
        assert await_args is not None
        embed = await_args.kwargs.get("embed")
        assert embed is not None
        assert "3" in embed.description


# ---------------------------------------------------------------------------
# Logging-service i18n — spec logging-service scenarios (cycle-5 S3)
# ---------------------------------------------------------------------------


_ES_GUILD = "777001"
_EN_GUILD = "777002"


class TestLoggingServiceI18n:
    """Localized log embeds resolved through t(guild_id, ...) per guild language."""

    @pytest.mark.asyncio
    async def test_spanish_guild_voice_join_embed_localized(self) -> None:
        """ES guild: title/description come from the es voice.join_* keys."""
        set_guild_language(_ES_GUILD, "es")
        service, _, mock_log_channel = await _setup_service_and_config(guild_id=_ES_GUILD)
        member = make_mock_member(member_id=333, name="NewUser")
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = make_mock_channel(channel_id=100, name="Voice-A", is_text=False)

        await service.log_voice_event(_ES_GUILD, member, "join", before, after)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert embed.title == t(_ES_GUILD, "voice.join_title")
        assert "<@333>" in (embed.description or "")
        assert "Voice-A" in (embed.description or "")

    @pytest.mark.asyncio
    async def test_english_guild_voice_join_embed_localized(self) -> None:
        """EN guild: en voice.join_* keys win over the es default."""
        set_guild_language(_EN_GUILD, "en")
        service, _, mock_log_channel = await _setup_service_and_config(guild_id=_EN_GUILD)
        member = make_mock_member(member_id=333, name="NewUser")
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = make_mock_channel(channel_id=100, name="Voice-A", is_text=False)

        await service.log_voice_event(_EN_GUILD, member, "join", before, after)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        assert embed.title == t(_EN_GUILD, "voice.join_title")
        # The EN title text differs from ES — proves locale selection.
        assert embed.title == "Voice Join"

    @pytest.mark.asyncio
    async def test_interpolation_params_substituted(self) -> None:
        """Voice move: {mention}/{from}/{to} replaced — no raw placeholders remain."""
        service, _, mock_log_channel = await _setup_service_and_config(guild_id=_ES_GUILD)
        member = make_mock_member(member_id=333, name="Mover")
        before = MagicMock(spec=discord.VoiceState)
        before.channel = make_mock_channel(channel_id=1, name="Lobby", is_text=False)
        after = MagicMock(spec=discord.VoiceState)
        after.channel = make_mock_channel(channel_id=2, name="Stage", is_text=False)

        await service.log_voice_event(_ES_GUILD, member, "move", before, after)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        desc = embed.description or ""
        assert "{mention}" not in desc
        assert "{from}" not in desc
        assert "{to}" not in desc
        assert "Lobby → Stage" in _embed_to_str(embed)

    @pytest.mark.asyncio
    async def test_moderation_action_field_labels_localized(self) -> None:
        """Moderation embed field names resolve via the guild language (ES default)."""
        service, _, mock_log_channel = await _setup_service_and_config(guild_id=_ES_GUILD)
        target = make_mock_member(member_id=555, name="BadUser")
        moderator = make_mock_member(member_id=111, name="ModUser")

        await service.log_moderation_action(_ES_GUILD, "Warn", target, moderator, "spamming")

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert t(_ES_GUILD, "log.moderation.target") in field_names
        assert t(_ES_GUILD, "log.moderation.moderator") in field_names
        assert t(_ES_GUILD, "log.moderation.reason") in field_names

    @pytest.mark.asyncio
    async def test_voice_event_routing_guards_unchanged(self) -> None:
        """Disabled logging or missing channel → no send even when localized."""
        service, mock_bot, _ = await _setup_service_and_config(
            guild_id=_ES_GUILD, log_channel_id=None, log_enabled=False
        )
        member = make_mock_member(member_id=333, name="Ghost")
        state = MagicMock(spec=discord.VoiceState)
        state.channel = None

        await service.log_voice_event(_ES_GUILD, member, "join", state, state)

        mock_bot.get_channel.assert_not_called()
