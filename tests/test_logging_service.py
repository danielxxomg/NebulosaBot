"""Unit tests for bot.services.logging_service.LoggingService.

Covers the logging-service spec scenarios:
    - Embed building per event type (edit, delete, join, leave, update, channel create/delete)
    - Log moderation action
    - Routing guards: logging disabled, missing channel, private channel skip
    - can_log_in_channel: visibility filter

Strict TDD: tests written BEFORE implementation (RED phase).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.services.logging_service import LoggingService

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
        """Messages with empty content should show a placeholder."""
        service, _, mock_log_channel = await _setup_service_and_config()
        channel = make_mock_channel(name="general")
        msg = make_mock_message(content="", channel=channel)

        await service.log_message_delete("123456789", msg)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        # Should contain some indicator — e.g. "No content" or "[Empty]"
        assert any(indicator in text for indicator in ("No content", "Empty", "Attachment"))


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
    async def test_no_roles_shows_none(self) -> None:
        """When member has no roles, embed should indicate that."""
        service, _, mock_log_channel = await _setup_service_and_config()
        member = make_mock_member(member_id=444, name="NoRolesUser", roles=[])

        await service.log_member_leave("123456789", member)

        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        # Should indicate no roles somehow
        assert any(word in text for word in ("None", "none", "None"))


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
        embed = mock_log_channel.send.call_args.kwargs["embed"]
        text = _embed_to_str(embed)
        assert "VIP" in text  # Added
        assert "Added" in text or "added" in text

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
        parts.append(field.name)
        parts.append(field.value)
    if embed.footer.text:
        parts.append(embed.footer.text)
    return " ".join(parts)
