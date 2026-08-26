"""Triple-path transcript delivery — S1.1 RED (clean-1.0 S1).

Each branch (DM, Storage, log) must be best-effort and independent.
DM-closed must not block Storage+log; log-missing must not block DM+Storage.
transcriptUrl must store Storage PATH not CDN URL.
Bytes generated once; fresh File per branch.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.core.database import Database
from bot.models.ticket import Ticket
from bot.services.ticket_lifecycle_service import TicketLifecycleService
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService
from bot.services.transcript_service import TranscriptService

MIGRATION_PATH = Path("migrations/027_private_transcript_bucket.sql")


# ---------------------------------------------------------------------------
# S1.2 — migration idempotent private bucket
# ---------------------------------------------------------------------------


class TestPrivateBucketMigration:
    """S1.2: private bucket migration must exist and be idempotent."""

    def test_migration_file_exists(self) -> None:
        assert MIGRATION_PATH.exists(), "027_private_transcript_bucket.sql missing"

    def test_migration_inserts_transcripts_bucket_private(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        low = sql.lower()
        assert "storage.buckets" in low, "must INSERT into storage.buckets"
        assert "transcripts" in sql, "bucket name must be 'transcripts'"
        assert "public" in low, "must set public flag"
        # public = false (private)
        assert "false" in low, "bucket must be private public=false"

    def test_migration_is_idempotent_on_conflict(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        assert "on conflict" in sql.lower(), "must use ON CONFLICT for idempotency"

    def test_migration_documents_idempotency(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        assert "idempotent" in sql.lower() or "safe to re-run" in sql.lower()


# ---------------------------------------------------------------------------
# Helpers for deliver tests
# ---------------------------------------------------------------------------


def _make_channel(name: str = "ticket-0001", channel_id: int = 444444444, guild_id: int = 123456789) -> Any:
    ch = MagicMock(spec=discord.TextChannel)
    ch.name = name
    ch.id = channel_id
    ch.guild = MagicMock()
    ch.guild.id = guild_id
    # history is sync returning async iterator — but deliver will mock generate, so not needed
    return ch


def _make_creator(user_id: int = 111111111) -> Any:
    user = MagicMock(spec=discord.User)
    user.id = user_id
    user.send = AsyncMock()
    return user


def _make_log_channel(channel_id: int = 999999999) -> Any:
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = channel_id
    ch.name = "ticket-logs"
    ch.send = AsyncMock(
        return_value=MagicMock(
            attachments=[MagicMock(url="https://cdn.discordapp.com/attachments/123/456/transcript.html")]
        )
    )
    return ch


def _make_storage_client() -> Any:
    """Return a mock supabase client with storage.from_('transcripts').upload mocked."""
    mock_bucket = MagicMock()
    mock_bucket.upload = AsyncMock(return_value=MagicMock(path="transcripts/123/456/transcript.html"))
    mock_storage = MagicMock()
    mock_storage.from_ = MagicMock(return_value=mock_bucket)
    client = MagicMock()
    client.storage = mock_storage
    # expose bucket for assertions
    client._mock_bucket = mock_bucket
    return client


def _mock_generate(
    service: TranscriptService,
    content: bytes = b"<html>transcript</html>",
    filename: str = "transcript-ticket-0001.html",
) -> Any:
    """Patch service.generate to return a File with given bytes/filename."""
    file = discord.File(io.BytesIO(content), filename=filename)
    return patch.object(TranscriptService, "generate", new=AsyncMock(return_value=file))


# ---------------------------------------------------------------------------
# S1.3 — deliver orchestrator
# ---------------------------------------------------------------------------


class TestTranscriptDeliverExists:
    """S1.3: TranscriptService must expose deliver() orchestrator."""

    def test_deliver_method_exists(self) -> None:
        assert hasattr(TranscriptService, "deliver"), "TranscriptService.deliver missing"
        assert callable(TranscriptService.deliver)

    @pytest.mark.asyncio
    async def test_deliver_returns_storage_path(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        log_channel = _make_log_channel()
        storage = _make_storage_client()
        with _mock_generate(service):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123456789",
                ticket_id="ticket-uuid-001",
                log_channel=log_channel,
                supabase_client=storage,
            )
        # Must return storage_path in transcripts/{guild}/{ticket}/...
        assert result.storage_path is not None
        assert result.storage_path.startswith("transcripts/123456789/ticket-uuid-001/")
        assert result.storage_path.endswith(".html")
        # log_url still populated via upload, but transcriptUrl must be PATH not CDN
        assert result.log_url is not None


class TestTriplePathIndependence:
    """Each branch fails alone, others succeed."""

    @pytest.mark.asyncio
    async def test_dm_failure_storage_and_log_still_succeed(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        creator.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs closed"))
        log_channel = _make_log_channel()
        # ensure log send succeeds
        mock_msg = MagicMock()
        mock_msg.attachments = [MagicMock(url="https://cdn.discordapp.com/attachments/123/456/file.html")]
        log_channel.send = AsyncMock(return_value=mock_msg)
        storage = _make_storage_client()

        with _mock_generate(service):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123456789",
                ticket_id="tid-001",
                log_channel=log_channel,
                supabase_client=storage,
            )
        # DM failed but Storage+log succeeded
        assert result.dm_sent is False
        assert result.storage_path is not None
        assert result.log_url is not None
        # storage upload still called
        storage.storage.from_.assert_called_with("transcripts")
        storage._mock_bucket.upload.assert_awaited_once()
        log_channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_storage_failure_dm_and_log_still_succeed(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        log_channel = _make_log_channel()
        mock_msg = MagicMock()
        mock_msg.attachments = [MagicMock(url="https://cdn.discordapp.com/attachments/123/456/file.html")]
        log_channel.send = AsyncMock(return_value=mock_msg)
        storage = _make_storage_client()
        storage._mock_bucket.upload = AsyncMock(side_effect=Exception("storage down"))

        with _mock_generate(service):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123456789",
                ticket_id="tid-002",
                log_channel=log_channel,
                supabase_client=storage,
            )
        assert result.storage_path is None
        assert result.dm_sent is True
        assert result.log_url is not None
        creator.send.assert_awaited_once()
        log_channel.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_channel_missing_dm_and_storage_succeed(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        storage = _make_storage_client()

        with _mock_generate(service):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123456789",
                ticket_id="tid-003",
                log_channel=None,
                supabase_client=storage,
            )
        assert result.dm_sent is True
        assert result.storage_path is not None
        assert result.log_url is None
        creator.send.assert_awaited_once()
        storage._mock_bucket.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_branches_fail_returns_no_crash(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        creator.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs closed"))
        storage = _make_storage_client()
        storage._mock_bucket.upload = AsyncMock(side_effect=Exception("storage down"))
        log_channel = _make_log_channel()
        log_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "log fail"))

        with _mock_generate(service):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123456789",
                ticket_id="tid-004",
                log_channel=log_channel,
                supabase_client=storage,
            )
        # No exception propagated; all branches logged as failed
        assert result.dm_sent is False
        assert result.storage_path is None
        assert result.log_url is None

    @pytest.mark.asyncio
    async def test_bytes_once_fresh_file_per_branch(self) -> None:
        """Bytes generated once; fresh File per branch (single-send buffer)."""
        service = TranscriptService()
        channel = _make_channel(name="my-ticket")
        creator = _make_creator()
        log_channel = _make_log_channel()
        storage = _make_storage_client()

        generate_mock = AsyncMock(
            return_value=discord.File(io.BytesIO(b"<html>once</html>"), filename="transcript-my-ticket.html")
        )
        with patch.object(TranscriptService, "generate", generate_mock):
            await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="123",
                ticket_id="tid-005",
                log_channel=log_channel,
                supabase_client=storage,
            )
        # generate called exactly once
        generate_mock.assert_awaited_once_with(channel)
        # DM and log each received a File with same filename but distinct BytesIO
        # creator.send(file=file) — check we passed file=
        assert creator.send.call_args is not None
        dm_kwargs = creator.send.call_args.kwargs
        assert "file" in dm_kwargs
        dm_file_obj = dm_kwargs["file"]
        log_kwargs = log_channel.send.call_args.kwargs
        assert "file" in log_kwargs
        log_file_obj = log_kwargs["file"]
        # distinct objects
        assert dm_file_obj is not log_file_obj
        assert dm_file_obj.filename == log_file_obj.filename == "transcript-my-ticket.html"
        # storage path uses same filename
        upload_path = storage._mock_bucket.upload.call_args.args[0]
        assert upload_path.endswith("transcript-my-ticket.html")
        # content bytes preserved
        # verify bytes passed to storage equal original
        upload_bytes = storage._mock_bucket.upload.call_args.args[1]
        assert upload_bytes == b"<html>once</html>"

    @pytest.mark.asyncio
    async def test_storage_path_format_private(self) -> None:
        service = TranscriptService()
        channel = _make_channel()
        creator = _make_creator()
        log_channel = _make_log_channel()
        storage = _make_storage_client()
        with _mock_generate(service, filename="transcript-abc.html"):
            result = await service.deliver(
                channel=channel,
                creator=creator,
                guild_id="guild-999",
                ticket_id="ticket-xyz",
                log_channel=log_channel,
                supabase_client=storage,
            )
        expected_prefix = "transcripts/guild-999/ticket-xyz/"
        assert result.storage_path is not None
        assert result.storage_path.startswith(expected_prefix)
        # storage client called with private bucket
        storage.storage.from_.assert_called_with("transcripts")
        # verify storage upload path matches returned storage_path
        actual_upload_path = storage._mock_bucket.upload.call_args.args[0]
        assert actual_upload_path == result.storage_path


class TestTranscriptUrlIsPathNotCdn:
    """S1.4: ticket close must store Storage PATH, not CDN URL."""

    @pytest.mark.asyncio
    async def test_close_ticket_full_stores_path_not_cdn(self) -> None:
        # Setup mocks
        mock_db = AsyncMock(spec=Database)
        mock_db.update_ticket = AsyncMock()
        mock_db.transition_ticket_to_closed = AsyncMock(return_value=None)  # not used directly here, lifecycle does
        # Mock lifecycle close_ticket to avoid DB
        mock_query = MagicMock(spec=TicketQueryService)
        mock_lifecycle = MagicMock(spec=TicketLifecycleService)
        mock_lifecycle.close_ticket = AsyncMock(return_value=MagicMock())
        mock_lifecycle._clear_scheduled_fields = AsyncMock()

        # Create service under test with mocked lifecycle
        service = TicketRepairService(db=mock_db, query=mock_query, lifecycle=mock_lifecycle)

        # Mock dependencies for close_ticket_full: transcript_service.deliver and bot
        ticket = Ticket(
            id="ticket-uuid-123",
            ticket_number=42,
            guild_id="123456789",
            author_id="111111111",
            channel_id="444444444",
            status="open",
            created_at=datetime.now(UTC),
            last_activity=datetime.now(UTC),
        )
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 444444444
        channel.name = "ticket-0042"
        channel.guild = MagicMock()
        channel.guild.id = 123456789
        channel.guild.get_member = MagicMock(return_value=MagicMock(spec=discord.Member, id=111111111))
        channel.send = AsyncMock()
        channel.delete = AsyncMock()

        # Mock bot
        mock_bot = MagicMock()
        mock_bot.guild_service = MagicMock()
        mock_config = MagicMock()
        mock_config.log_channel_id = "999999999"
        mock_bot.guild_service.get_config = AsyncMock(return_value=mock_config)
        mock_bot.db = mock_db

        # Use real TranscriptService but mock its deliver to return PATH vs CDN
        real_transcript = TranscriptService()
        mock_bot.transcript_service = real_transcript

        log_ch = MagicMock(spec=discord.TextChannel)
        log_ch.id = 999999999
        channel.guild.get_channel = MagicMock(return_value=log_ch)

        # Patch deliver to return storage PATH
        fake_result = MagicMock()
        fake_result.storage_path = "transcripts/123456789/ticket-uuid-123/transcript-ticket-0042.html"
        fake_result.log_url = "https://cdn.discordapp.com/attachments/123/456/transcript.html"
        fake_result.dm_sent = True

        with (
            patch.object(TranscriptService, "deliver", new=AsyncMock(return_value=fake_result)) as mock_deliver,
            patch.object(
                TranscriptService,
                "generate",
                new=AsyncMock(return_value=discord.File(io.BytesIO(b"html"), filename="transcript.html")),
            ),
        ):
            # Need to also mock lifecycle.close_ticket to succeed and capture transcript_url
            async def _fake_close(ticket_id, closed_by, transcript_url, guild_id):
                # assert transcript_url is PATH not CDN
                assert transcript_url == fake_result.storage_path, (
                    f"transcript_url must be PATH {fake_result.storage_path!r} not CDN {transcript_url!r}"
                )
                assert "cdn.discordapp.com" not in (transcript_url or "")
                assert transcript_url.startswith("transcripts/")
                return ticket

            mock_lifecycle.close_ticket = AsyncMock(side_effect=_fake_close)
            await service.close_ticket_full(channel, ticket, closed_by="tester", bot=mock_bot, manual=False)
            mock_deliver.assert_awaited_once()
            mock_lifecycle.close_ticket.assert_awaited_once()
