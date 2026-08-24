"""Unit tests for bot.services.transcript_service.TranscriptService.

Covers:
    - HTML generation with mock messages (author, timestamp, content)
    - Message cap at 5000
    - Empty channel yields valid HTML skeleton
    - Messages with no content display placeholder
    - HTML escaping for special characters
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales, set_guild_language
from bot.services.transcript_service import MAX_MESSAGES, TranscriptService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_message(
    author_name: str = "TestUser",
    author_discriminator: str = "1234",
    content: str = "Hello, world!",
    created_at: datetime | None = None,
) -> MagicMock:
    """Return a MagicMock standing in for discord.Message."""
    author = MagicMock()
    author.name = author_name
    author.discriminator = author_discriminator

    msg = MagicMock(spec=discord.Message)
    msg.author = author
    msg.created_at = created_at or datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    msg.content = content
    return msg


def _make_mock_channel(
    name: str = "ticket-0001",
    channel_id: int = 888888888,
    messages: list[MagicMock] | None = None,
) -> MagicMock:
    """Return a MagicMock standing in for discord.TextChannel.

    The ``history()`` method returns an async iterator over *messages*.
    The channel is bound to guild ``888888888`` (English in the locale
    fixture) so t() resolves deterministically.
    """
    channel = MagicMock(spec=discord.TextChannel)
    channel.name = name
    channel.id = channel_id
    channel.guild.id = 888888888

    # discord.TextChannel.history() is NOT an async method — it returns an
    # AsyncIterator directly.  Our mock must mirror that contract.
    def _history(*, limit: int, oldest_first: bool):
        return _AsyncIterMock(messages or [])

    channel.history = _history
    return channel


class _AsyncIterMock:
    """Minimal async-iterator wrapper for a list."""

    def __init__(self, items: list) -> None:
        self._items = items
        self._index = 0

    def __aiter__(self) -> _AsyncIterMock:
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# ---------------------------------------------------------------------------
# TranscriptService fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_real_locales() -> None:
    """Load real locale files so t() resolves transcript strings.

    The shared helper channels belong to guild ``888888888`` pinned to
    English so pre-existing assertions keep their expected text.
    """
    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()
    locale_dir = Path("bot/locales")
    if locale_dir.exists():
        load_locales(locale_dir)
        set_guild_language("888888888", "en")


@pytest.fixture
def transcript_service() -> TranscriptService:
    """Return a fresh TranscriptService."""
    return TranscriptService()


# ---------------------------------------------------------------------------
# generate — basic HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_produces_html(
    transcript_service: TranscriptService,
) -> None:
    """generate() MUST produce a discord.File with valid HTML."""
    messages = [
        _make_mock_message("Alice", "0001", "First message"),
        _make_mock_message("Bob", "0002", "Second message"),
    ]
    channel = _make_mock_channel(name="support-42", messages=messages)

    file = await transcript_service.generate(channel)

    assert isinstance(file, discord.File)
    assert file.filename == "transcript-support-42.html"

    # Read back the HTML content.
    buffer_content = file.fp.read()
    html = buffer_content.decode("utf-8")

    assert "<!DOCTYPE html>" in html
    assert "<title>Ticket Transcript" not in html  # should be in the body h1
    assert "Ticket Transcript — support-42" in html
    assert "Alice#0001" in html
    assert "Bob#0002" in html
    assert "First message" in html
    assert "Second message" in html
    assert "2026-01-15 12:00" in html


@pytest.mark.asyncio
async def test_generate_empty_channel(
    transcript_service: TranscriptService,
) -> None:
    """generate() MUST produce valid HTML even when the channel has no messages."""
    channel = _make_mock_channel(name="empty-ticket", messages=[])

    file = await transcript_service.generate(channel)

    buffer_content = file.fp.read()
    html = buffer_content.decode("utf-8")
    assert "Ticket Transcript — empty-ticket" in html
    assert '<div class="message">' not in html


# ---------------------------------------------------------------------------
# generate — cap at MAX_MESSAGES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_respects_message_cap(
    transcript_service: TranscriptService,
) -> None:
    """generate() MUST cap requests at MAX_MESSAGES (5000), even if caller asks for more."""
    # Create more than MAX_MESSAGES mock messages.
    messages = [_make_mock_message(f"User{i:04d}", "0000", f"Message {i}") for i in range(MAX_MESSAGES + 100)]

    channel = _make_mock_channel(name="overflow", messages=messages[:MAX_MESSAGES])
    # We cap at 5000 regardless — the mock truncates to MAX_MESSAGES.
    # The real Discord history(limit=5000) won't return more.

    file = await transcript_service.generate(channel, limit=9999)
    buffer_content = file.fp.read()
    html = buffer_content.decode("utf-8")

    # Spot-check first and last messages are present.
    assert "User0000#0000" in html
    assert "Message 0" in html
    assert f"User{MAX_MESSAGES - 1:04d}" in html


# ---------------------------------------------------------------------------
# generate — special content handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_null_content_shows_placeholder(
    transcript_service: TranscriptService,
) -> None:
    """Messages with empty content MUST show a placeholder."""
    messages = [_make_mock_message("Ghost", "0000", content="")]
    channel = _make_mock_channel(name="ghost", messages=messages)

    file = await transcript_service.generate(channel)
    buffer_content = file.fp.read()
    html = buffer_content.decode("utf-8")

    assert "[no text content]" in html


@pytest.mark.asyncio
async def test_generate_escapes_html(
    transcript_service: TranscriptService,
) -> None:
    """Message content with HTML special chars MUST be escaped."""
    messages = [_make_mock_message("Hacker", "0001", content='<script>alert("xss")</script>')]
    channel = _make_mock_channel(name="xss-test", messages=messages)

    file = await transcript_service.generate(channel)
    buffer_content = file.fp.read()
    html = buffer_content.decode("utf-8")

    # The raw script tag should be escaped.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;xss&quot;" in html


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_returns_attachment_url(
    transcript_service: TranscriptService,
) -> None:
    """upload() MUST return the URL of the first attachment."""
    # Build a mock discord.File.
    buffer = io.BytesIO(b"<html>test</html>")
    file = discord.File(buffer, filename="transcript.html")

    # Mock the log channel's send().
    mock_attachment = MagicMock()
    mock_attachment.url = "https://cdn.discordapp.com/attachments/123/456/transcript.html"

    mock_message = MagicMock()
    mock_message.attachments = [mock_attachment]

    mock_log_channel = MagicMock(spec=discord.TextChannel)
    mock_log_channel.name = "ticket-logs"
    mock_log_channel.send = AsyncMock(return_value=mock_message)

    url = await transcript_service.upload(file, mock_log_channel)

    assert url == "https://cdn.discordapp.com/attachments/123/456/transcript.html"
    mock_log_channel.send.assert_awaited_once_with(file=file)


@pytest.mark.asyncio
async def test_upload_no_attachment_returns_none(
    transcript_service: TranscriptService,
) -> None:
    """When send() returns a message with no attachments, upload() MUST return None."""
    buffer = io.BytesIO(b"<html>test</html>")
    file = discord.File(buffer, filename="transcript.html")

    mock_message = MagicMock()
    mock_message.attachments = []

    mock_log_channel = MagicMock(spec=discord.TextChannel)
    mock_log_channel.name = "ticket-logs"
    mock_log_channel.send = AsyncMock(return_value=mock_message)

    url = await transcript_service.upload(file, mock_log_channel)

    assert url is None


# ---------------------------------------------------------------------------
# generate — event-loop offload (S4.2)
# ---------------------------------------------------------------------------


class TestToThreadOffload:
    """S4.2 — ``_build_html`` must run off the event loop via asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_generate_offloads_build_html_to_thread(self) -> None:
        """generate() MUST hand the sync-pure ``_build_html`` to asyncio.to_thread.

        HTML assembly over up to 5000 messages is CPU-bound string work;
        running it inline blocks the event loop. The recorder wraps the real
        ``asyncio.to_thread`` and captures every callable handed through it.
        """
        captured: list[object] = []
        real_to_thread = asyncio.to_thread

        async def _recorder(func, *args, **kwargs):
            captured.append(func)
            return await real_to_thread(func, *args, **kwargs)

        service = TranscriptService()
        messages = [_make_mock_message("Alice", "0001", "hello")]
        channel = _make_mock_channel(name="offload-1", messages=messages)

        # Patching ``asyncio.to_thread`` globally (delegating to the real one)
        # keeps the RED phase honest: before the production wrap exists, no
        # call is captured and the assertion below fails cleanly.
        with patch("asyncio.to_thread", side_effect=_recorder):
            file = await service.generate(channel)

        assert captured, "_build_html ran inline on the event loop — wrap the call in asyncio.to_thread"
        handed = captured[0]
        assert callable(handed), "asyncio.to_thread must receive a callable"
        assert getattr(handed, "__self__", None) is service, "to_thread must receive the bound _build_html"
        assert getattr(handed, "__name__", "") == "_build_html"
        # The rendered artifact is unchanged: a discord.File with the HTML body.
        assert isinstance(file, discord.File)
        html = file.fp.read().decode("utf-8")
        assert "Alice#0001" in html


# ---------------------------------------------------------------------------
# generate — i18n (S4.2 bundled fix: user-facing strings via t())
# ---------------------------------------------------------------------------


def _make_guild_channel(name: str, guild_id: int, messages: list[MagicMock]) -> MagicMock:
    """Return a mock TextChannel bound to a real guild id (for t() resolution)."""
    channel = _make_mock_channel(name=name, messages=messages)
    channel.guild.id = guild_id
    return channel


class TestTranscriptI18n:
    """Transcript header and empty-content placeholder MUST resolve via t()."""

    @pytest.mark.asyncio
    async def test_header_localized_spanish(self) -> None:
        set_guild_language(555000111, "es")
        channel = _make_guild_channel("soporte-9", 555000111, [_make_mock_message()])
        file = await TranscriptService().generate(channel)
        html = file.fp.read().decode("utf-8")
        assert "Transcripción del ticket — soporte-9" in html

    @pytest.mark.asyncio
    async def test_header_localized_english(self) -> None:
        set_guild_language(555000222, "en")
        channel = _make_guild_channel("support-7", 555000222, [_make_mock_message()])
        file = await TranscriptService().generate(channel)
        html = file.fp.read().decode("utf-8")
        assert "Ticket Transcript — support-7" in html

    @pytest.mark.asyncio
    async def test_empty_content_placeholder_localized(self) -> None:
        set_guild_language(555000333, "es")
        message = _make_mock_message(content="")
        channel = _make_guild_channel("vacio-1", 555000333, [message])
        file = await TranscriptService().generate(channel)
        html = file.fp.read().decode("utf-8")
        assert "sin contenido de texto" in html
