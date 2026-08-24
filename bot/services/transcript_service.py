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
