"""TranscriptService — HTML transcript generation for ticket channels.

Generates self-contained inline-CSS HTML transcripts from Discord channel
history and uploads them to the configured log channel.  Transcripts are
hosted permanently on Discord's CDN.
"""

from __future__ import annotations

import asyncio
import html as _html_module
import io
import logging
from dataclasses import dataclass

import discord

from bot.core.i18n import t
from bot.utils.brand import (
    TRANSCRIPT_AUTHOR,
    TRANSCRIPT_BG,
    TRANSCRIPT_BORDER,
    TRANSCRIPT_HEADER_TEXT,
    TRANSCRIPT_HOVER,
    TRANSCRIPT_MUTED,
    TRANSCRIPT_TEXT,
)

logger = logging.getLogger(__name__)

MAX_MESSAGES = 5000


# -- Delivery result --------------------------------------------------------


@dataclass(frozen=True)
class TranscriptDeliveryResult:
    """Result of triple-path transcript delivery (S1 D2).

    Each branch is best-effort and independent — a failure in one never
    aborts the others. ``storage_path`` is the durable Storage object path
    (``transcripts/{guildId}/{ticketId}/{filename}``) used as
    ``transcriptUrl``; it is NOT a CDN URL. ``log_url`` is the expiring
    Discord CDN attachment URL from the log-channel post (if any).
    """

    dm_sent: bool
    storage_path: str | None
    log_url: str | None
    dm_error: str | None = None
    storage_error: str | None = None
    log_error: str | None = None


# -- HTML templates -----------------------------------------------------------
# All colors resolve through bot.utils.brand tokens (AGENTS.md brand rule);
# interpolated values are byte-identical to the original inline CSS.

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; background: {bg}; color: {text}; padding: 20px; }}
.message {{ margin: 10px 0; padding: 8px; border-radius: 4px; }}
.message:hover {{ background: {hover}; }}
.author {{ font-weight: bold; color: {author}; }}
.timestamp {{ color: {muted}; font-size: 0.8em; margin-left: 8px; }}
.content {{ margin-top: 4px; word-wrap: break-word; }}
.header {{ border-bottom: 1px solid {border}; padding-bottom: 10px; margin-bottom: 20px; }}
.header h1 {{ color: {header_text}; font-size: 1.2em; }}
</style></head>
<body>
<div class="header"><h1>{header_title}</h1></div>
{messages}
</body></html>"""

MESSAGE_TEMPLATE = (
    '<div class="message">\n'
    '  <span class="author">{author}</span>'
    '<span class="timestamp">{timestamp}</span>\n'
    '  <div class="content">{content}</div>\n'
    "</div>"
)


class TranscriptService:
    """Generates HTML transcripts from Discord channel history.

    Messages are fetched oldest-first and rendered into self-contained
    inline-CSS HTML suitable for permanent upload to Discord.
    """

    __slots__ = ()

    async def generate(
        self,
        channel: discord.TextChannel,
        *,
        limit: int = MAX_MESSAGES,
    ) -> discord.File:
        """Generate an HTML transcript file from channel message history.

        Args:
            channel: The Discord text channel to transcribe.
            limit: Maximum number of messages to fetch (capped at 5000).

        Returns:
            A :class:`discord.File` containing the HTML transcript.
        """
        effective_limit = min(limit, MAX_MESSAGES)
        logger.info(
            "Generating transcript for #%s (%s) — limit=%d",
            channel.name,
            channel.id,
            effective_limit,
        )

        # Fetch oldest-first for chronological display.
        messages: list[discord.Message] = [
            msg
            async for msg in channel.history(
                limit=effective_limit,
                oldest_first=True,
            )
        ]
        logger.debug("Fetched %d messages from #%s", len(messages), channel.name)

        # HTML assembly over up to MAX_MESSAGES entries is CPU-bound string
        # work — offload to a worker thread so the event loop never blocks.
        # ``_build_html`` stays sync-pure for direct testability.
        guild_id = channel.guild.id
        channel_label = channel.name or str(channel.id)
        html_content = await asyncio.to_thread(
            self._build_html,
            messages,
            t(guild_id, "transcript.header_title", channel_name=channel_label),
            t(guild_id, "transcript.no_text_content"),
        )
        buffer = io.BytesIO(html_content.encode("utf-8"))
        filename = f"transcript-{channel.name or channel.id}.html"

        return discord.File(buffer, filename=filename)

    async def upload(
        self,
        file: discord.File,
        log_channel: discord.TextChannel,
    ) -> str | None:
        """Upload a transcript file to a log channel and return its URL.

        Args:
            file: The :class:`discord.File` to upload.
            log_channel: The Discord channel to post the transcript in.

        Returns:
            The attachment URL, or ``None`` if the upload fails.
        """
        try:
            message = await log_channel.send(file=file)
            if message.attachments:
                url = message.attachments[0].url
                logger.info("Transcript uploaded to #%s: %s", log_channel.name, url)
                return url
            logger.warning(
                "Transcript upload to #%s succeeded but no attachment found",
                log_channel.name,
            )
        except discord.HTTPException:
            logger.exception("Failed to upload transcript to #%s", log_channel.name)
            return None
        else:
            return None

    async def deliver(  # noqa: C901 -- triple-path fan-out best-effort branches
        self,
        *,
        channel: discord.TextChannel,
        creator: discord.abc.User | discord.Member | None,
        guild_id: str,
        ticket_id: str,
        log_channel: discord.TextChannel | None,
        supabase_client: object | None = None,
    ) -> TranscriptDeliveryResult:
        """Deliver a transcript through three independent best-effort paths (S1 D2).

        Bytes are generated once via :meth:`generate` (single
        ``channel.history`` scan + one ``asyncio.to_thread`` HTML build) and
        then fanned out as fresh :class:`discord.File` instances — a
        ``File``'s buffer is single-send, so each path receives its own
        ``BytesIO`` wrapper over the same bytes.

        Paths:
            1. DM the ticket creator (``creator.send(file)``) — DM-closed is
               logged at WARNING and never aborts remaining paths.
            2. Upload to the PRIVATE Storage bucket
               ``transcripts/{guildId}/{ticketId}/{filename}`` via
               ``supabase_client.storage.from_("transcripts").upload`` —
               Storage failure is logged at WARNING and never aborts close.
            3. Post to the configured log channel via existing :meth:`upload`
               — missing log channel skips only this path (preserved).

        Args:
            channel: The ticket channel to transcribe (source of history).
            creator: The ticket creator's Discord user/member to DM (``None``
                skips DM path).
            guild_id: Guild snowflake as string (scopes Storage path).
            ticket_id: Ticket UUID (scopes Storage path).
            log_channel: Configured log channel (``None`` skips log path).
            supabase_client: Async Supabase client (``None`` skips Storage
                path). When provided, ``client.storage.from_("transcripts")``
                is used.

        Returns:
            A :class:`TranscriptDeliveryResult` with ``storage_path`` (the
            durable path persisted as ``transcriptUrl``), ``log_url`` (the
            expiring CDN URL), and ``dm_sent``.
        """
        # --- 1. Generate once ---
        try:
            generated = await self.generate(channel)
        except Exception:  # noqa: BLE001 -- best-effort: generate failure never propagates
            logger.exception("Transcript generation failed for ticket %s", ticket_id)
            return TranscriptDeliveryResult(
                dm_sent=False,
                storage_path=None,
                log_url=None,
                dm_error="generate failed",
                storage_error="generate failed",
                log_error="generate failed",
            )

        # Extract bytes + filename from the generated File (fresh buffer per path)
        try:
            fp = generated.fp
            # BytesIO path — getvalue is most reliable; fall back to read
            if hasattr(fp, "getvalue"):
                try:
                    data: bytes = fp.getvalue()  # type: ignore[union-attr]
                except Exception:  # noqa: BLE001 -- fallback from getvalue to read
                    fp.seek(0)
                    data = fp.read()
            else:
                fp.seek(0)
                data = fp.read()
            # Ensure bytes
            if isinstance(data, str):
                data = data.encode("utf-8")
            filename: str = getattr(generated, "filename", None) or f"transcript-{ticket_id}.html"
        except Exception:  # noqa: BLE001 -- best-effort: extract failure never propagates
            logger.exception("Failed to extract transcript bytes for ticket %s", ticket_id)
            return TranscriptDeliveryResult(
                dm_sent=False,
                storage_path=None,
                log_url=None,
                dm_error="extract failed",
                storage_error="extract failed",
                log_error="extract failed",
            )

        # --- 2. Fan out independently ---
        dm_sent = False
        dm_error: str | None = None
        storage_path: str | None = None
        storage_error: str | None = None
        log_url: str | None = None
        log_error: str | None = None

        # Path 1: DM creator
        if creator is not None:
            try:
                dm_file = discord.File(io.BytesIO(data), filename=filename)
                # creator may be User or Member — both expose send
                await creator.send(file=dm_file)  # type: ignore[union-attr]
                dm_sent = True
                logger.info("Transcript DM sent to user %s for ticket %s", getattr(creator, "id", "unknown"), ticket_id)
            except Exception as exc:  # noqa: BLE001 — best-effort: any DM failure is logged, never propagates
                dm_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Failed to DM transcript to creator %s for ticket %s: %s",
                    getattr(creator, "id", "unknown"),
                    ticket_id,
                    exc,
                    exc_info=True,
                )
        else:
            logger.debug("No creator resolved for ticket %s — skipping DM path", ticket_id)

        # Path 2: Storage upload (PRIVATE bucket)
        if supabase_client is not None:
            object_path = f"transcripts/{guild_id}/{ticket_id}/{filename}"
            try:
                # supabase_client.storage is a property returning AsyncStorageClient
                storage = getattr(supabase_client, "storage", None)
                if storage is None:
                    msg = "supabase_client has no storage attribute"
                    raise AttributeError(msg)  # noqa: TRY301 -- probe failure caught as storage_error
                # storage.from_("transcripts") is sync, upload is async
                bucket = storage.from_("transcripts")
                # storage bucket upload signature: upload(path, bytes, file_options={...})
                # file_options with content-type ensures HTML is served correctly
                try:
                    await bucket.upload(object_path, data, file_options={"content-type": "text/html", "upsert": "true"})
                except TypeError:
                    # Fallback for clients expecting file_options as dict positional
                    await bucket.upload(object_path, data, {"content-type": "text/html"})
                storage_path = object_path
                logger.info("Transcript uploaded to Storage %s for ticket %s", object_path, ticket_id)
            except Exception as exc:  # noqa: BLE001 — best-effort: Storage failure never aborts close
                storage_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Failed to upload transcript to Storage %s for ticket %s: %s",
                    object_path,
                    ticket_id,
                    exc,
                    exc_info=True,
                )
        else:
            logger.debug("No supabase client for ticket %s — skipping Storage path", ticket_id)

        # Path 3: log channel (existing upload semantics, best-effort)
        if log_channel is not None:
            try:
                log_file = discord.File(io.BytesIO(data), filename=filename)
                url = await self.upload(log_file, log_channel)
                log_url = url
                if url is None and log_error is None:  # noqa: SIM102 -- preserve upload's own warning, just set marker
                    log_error = "upload returned None"
            except Exception as exc:  # noqa: BLE001 — best-effort
                log_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Failed to upload transcript to log channel for ticket %s: %s",
                    ticket_id,
                    exc,
                    exc_info=True,
                )
        else:
            logger.debug("No log channel for guild %s — skipping log path", guild_id)

        return TranscriptDeliveryResult(
            dm_sent=dm_sent,
            storage_path=storage_path,
            log_url=log_url,
            dm_error=dm_error,
            storage_error=storage_error,
            log_error=log_error,
        )

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _build_html(
        self,
        messages: list[discord.Message],
        header_title: str,
        no_content_text: str,
    ) -> str:
        """Render messages as inline-CSS HTML blocks.

        Args:
            messages: List of messages in chronological order.
            header_title: Pre-localized page heading (``t()`` resolved; the
                channel name is already interpolated into it).
            no_content_text: Pre-localized placeholder for textless messages.

        Returns:
            The full HTML string.
        """
        message_blocks: list[str] = []
        for msg in messages:
            author = _html_module.escape(f"{msg.author.name}#{msg.author.discriminator}")
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
            content = msg.content or ""
            content = _html_module.escape(content) if content else f"<em>{no_content_text}</em>"

            message_blocks.append(
                MESSAGE_TEMPLATE.format(
                    author=author,
                    timestamp=timestamp,
                    content=content,
                )
            )

        return HTML_TEMPLATE.format(
            bg=TRANSCRIPT_BG,
            text=TRANSCRIPT_TEXT,
            hover=TRANSCRIPT_HOVER,
            author=TRANSCRIPT_AUTHOR,
            muted=TRANSCRIPT_MUTED,
            border=TRANSCRIPT_BORDER,
            header_text=TRANSCRIPT_HEADER_TEXT,
            header_title=_html_module.escape(header_title),
            messages="\n".join(message_blocks),
        )
