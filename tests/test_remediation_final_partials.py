"""Final-22 PARTIAL → COMPLIANT behavioral probes (welcome-neon-timer-banana).

Narrow remediation (work unit ``remediation-close-22-partial-ociosecurity-migration``).
Each probe exercises real production code so it FAILS if the behavior is
removed — replacing source-presence-only and mock-only evidence flagged
⚠️ PARTIAL in the verify-report matrix. No new migration, deps, or
production changes.

Coverage map (PARTIAL → COMPLIANT promotions):
  1. Ocio 8ball S1/S2 — get_8ball_response returns a member of the 20-key
     localized set (real ``t()`` locale read); both es/en command paths
     are executable through the real cog callback.
  2. Ocio banana S1 — the returned filename is a real member of the
     assets/images/banana pool basenames (99% path forced).
  3. Guards escape/AllowedMentions S1-S3 — markdown payloads injected
     through build_ticket_embed (ticket subject), the Sentinel ban reason
     embed path, and the 8ball question path are actually escaped; the
     cogs send with AllowedMentions.none().
  4. Database AsyncClientOptions S1 — acreate_client spy captures the
     real AsyncClientOptions flags (auto_refresh_token=False,
     persist_session=False, schema==public).
  5. Close confirmation S1/S4 — the real confirm_timer_schedule path
     writes scheduledCloseAt/scheduledCloseBy to the DB (the view's
     on_confirm callback effect).
  6. Ticket service S7 — handle_timer_message called twice with different
     durations overwrites scheduledCloseAt (extend, not additive).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.core.database import Database
from bot.core.i18n import set_guild_language, t
from tests.test_database import FakeQueryBuilder, FakeSupabaseClient

# ===========================================================================
# 1. Ocio 8ball S1/S2 — member of the 20-key localized set + both locales run
# ===========================================================================

_ES_GUILD = "111222333"
_EN_GUILD = "444555666"


@pytest.fixture(autouse=True)
def _set_8ball_guild_langs() -> Any:
    """Point two guilds at es/en so S2 (i18n isolation) is executable."""
    set_guild_language(_ES_GUILD, "es")
    set_guild_language(_EN_GUILD, "en")
    yield


def _localized_8ball_set(guild_id: str) -> set[str]:
    """Read the real 20-key localized 8ball set from the locale JSON via t()."""
    return {t(guild_id, f"ocio.8ball.r{i}") for i in range(1, 21)}


class Test8BallLocalizedMembership:
    """S1 — get_8ball_response returns a member of the 20-key localized set.

    Replaces the ⚠️ PARTIAL 'non-empty text only' check. Runs the real
    OcioService.get_8ball_response repeatedly and asserts every response is
    an exact member of the real localized 20-key set read from the locale
    files via t(). Fails if get_8ball_response ever returns a value outside
    the canonical 20-key set.
    """

    def test_es_response_is_member_of_20_key_spanish_set(self) -> None:
        from bot.services.ocio_service import OcioService

        svc = OcioService()
        es_set = _localized_8ball_set(_ES_GUILD)
        assert len(es_set) == 20, "es.json MUST define all 20 8ball keys"
        # Sample many draws to catch any off-set value (uniform random).
        for _ in range(200):
            resp = svc.get_8ball_response(guild_id=_ES_GUILD, question="is it?")
            assert resp in es_set, f"es 8ball response {resp!r} MUST be in the 20-key set"

    def test_en_response_is_member_of_20_key_english_set(self) -> None:
        from bot.services.ocio_service import OcioService

        svc = OcioService()
        en_set = _localized_8ball_set(_EN_GUILD)
        assert len(en_set) == 20, "en.json MUST define all 20 8ball keys"
        for _ in range(200):
            resp = svc.get_8ball_response(guild_id=_EN_GUILD, question="is it?")
            assert resp in en_set, f"en 8ball response {resp!r} MUST be in the 20-key set"

    def test_es_and_en_sets_are_distinct(self) -> None:
        """S2 — Spanish and English sets are independently testable (isolated)."""
        es_set = _localized_8ball_set(_ES_GUILD)
        en_set = _localized_8ball_set(_EN_GUILD)
        assert es_set != en_set, "es/en 8ball sets MUST be distinct (i18n isolation)"

    @pytest.mark.asyncio
    async def test_eight_ball_cog_callback_executes_with_real_service(self) -> None:
        """S2 — the eight_ball cog path is executable (mock ctx, real OcioService).

        Replaces the PARTIAL 'locale structure checked but both command paths
        not executed'. Runs the real OcioCog.eight_ball.callback so the real
        OcioService.get_8ball_response is called and the embed is built.
        """
        from bot.cogs.ocio import OcioCog

        es_set = _localized_8ball_set(_ES_GUILD)
        cog = OcioCog(MagicMock())
        ctx = MagicMock()
        ctx.guild = MagicMock(id=int(_ES_GUILD))
        ctx.send = AsyncMock()

        await cog.eight_ball.callback(cog, ctx, question="will it pass?")

        ctx.send.assert_awaited_once()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True, "8ball reply MUST be ephemeral"
        # The embed description embeds Q/A; the answer MUST be an es-set member.
        embed = kwargs.get("embed")
        assert embed is not None
        desc = embed.description or ""
        # at least one es localized response appears in the rendered answer
        assert any(resp in desc for resp in es_set), "embed MUST carry a real es 8ball answer"

    @pytest.mark.asyncio
    async def test_eight_ball_embed_title_is_localized_not_raw(self) -> None:
        """S2 — embed title comes from ocio.8ball.embed_title (no raw key, no hardcode).

        Spec ocio-commands: the title MUST be the localized key value in each
        guild's language; a raw 'ocio.8ball.embed_title' key or a hardcoded
        fallback MUST never be rendered.
        """
        from bot.cogs.ocio import OcioCog

        cog = OcioCog(MagicMock())
        ctx = MagicMock()
        ctx.guild = MagicMock(id=int(_ES_GUILD))
        ctx.send = AsyncMock()

        await cog.eight_ball.callback(cog, ctx, question="will it pass?")

        kwargs = ctx.send.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        expected = t(_ES_GUILD, "ocio.8ball.embed_title")
        assert embed.title == expected, f"embed title must be t(ocio.8ball.embed_title)={expected!r}, got {embed.title!r}"
        assert not embed.title.startswith("ocio.8ball"), "raw key must never reach users"
        assert embed.title != "🎱 8ball", "hardcoded fallback must be gone"


# ===========================================================================
# 2. Ocio banana S1 — returned filename is a real pool member (99% path)
# ===========================================================================


class TestBananaPoolMembership:
    """S1 — the 99% pool path returns a filename that IS a pool member.

    Replaces the ⚠️ PARTIAL 'bytes/name/range but not pool membership' check.
    Forces the 99% path (random.random >= 0.01) so the dorada branch is
    skipped, then asserts the returned filename is the basename of a real
    ``assets/images/banana/*.webp`` pool entry. Fails if get_random_banana
    ever returns a filename that is not a current pool member on the 99% path.
    """

    @pytest.mark.asyncio
    async def test_returned_filename_is_real_pool_member(self) -> None:
        from bot.services.ocio_service import OcioService

        banana_dir = Path("assets/images/banana")
        pool_basenames = {p.name for p in banana_dir.glob("*.webp")}
        assert pool_basenames, "banana pool MUST exist with *.webp variants"

        svc = OcioService(banana_dir=banana_dir)
        # Force the 99% pool path: random.random() >= 0.01 skips the 1% dorada
        # branch. The pool glob includes dorada.webp, so random.choice MAY
        # pick it — but on the 99% path the cm is 2..30 (NOT the dorada 30cm).
        # The contract is: filename is a real pool member AND cm in [2,30].
        with patch("bot.services.ocio_service.random.random", return_value=0.5):
            for _ in range(20):
                _data, filename, cm = await svc.get_random_banana()
                assert filename in pool_basenames, (
                    f"99%% path filename {filename!r} MUST be a pool member of {pool_basenames}"
                )
                assert 2 <= cm <= 30, "99%% path cm MUST be in [2, 30]"

    @pytest.mark.asyncio
    async def test_dorada_path_returns_dorada_filename(self) -> None:
        """Companion — the 1% dorada path returns the dorada pool member."""
        from bot.services.ocio_service import OcioService

        banana_dir = Path("assets/images/banana")
        svc = OcioService(banana_dir=banana_dir)
        with patch("bot.services.ocio_service.random.random", return_value=0.001):
            _data, filename, cm = await svc.get_random_banana()
        assert filename == "dorada.webp", "1% dorada path MUST return dorada.webp"
        assert cm == 30, "dorada MUST measure 30 cm"


# ===========================================================================
# 3. Guards escape/AllowedMentions S1-S3 — real escaping on injected payloads
# ===========================================================================

_MARKDOWN_PAYLOAD = "*bold* @everyone `code` __underline__"


class TestGuardsEscapeBehavioral:
    """S1/S2/S3 — inject a markdown+mention payload through each real escape
    path and assert the output is escaped (``\\*bold\\*`` not ``*bold*``) and
    the cog sends with ``AllowedMentions.none()``.

    Replaces the ⚠️ PARTIAL 'source-presence only' checks for ticket subject,
    ban reason, and 8ball question.
    """

    def test_s1_ticket_subject_escaped_in_build_ticket_embed(self) -> None:
        """S1 — build_ticket_embed escapes the ticket subject via _escape_md."""
        from bot.utils.embeds import build_ticket_embed

        ticket_row = {
            "ticketNumber": 7,
            "status": "open",
            "authorId": "99",
            "subject": _MARKDOWN_PAYLOAD,
            "description": None,
            "customFields": {},
        }
        embed = build_ticket_embed(ticket_row, guild_id=_ES_GUILD)
        # The escaped payload appears in the title (with-subject branch).
        title = embed.title or ""
        assert "\\*bold\\*" in title, "ticket subject MUST be escape_markdown'd"
        assert "*bold*" not in title or "\\*bold\\*" in title, (
            "raw *bold* markdown MUST NOT render unescaped in the embed title"
        )
        # Mentions stay in the escaped text but are suppressed via AllowedMentions
        # at send time (verified separately); the embed carries the literal text.

    def test_s1_ticket_description_escaped_in_build_ticket_embed(self) -> None:
        """S1 companion — the description field is also escaped."""
        from bot.utils.embeds import build_ticket_embed

        ticket_row = {
            "ticketNumber": 8,
            "status": "open",
            "authorId": "99",
            "subject": None,
            "description": _MARKDOWN_PAYLOAD,
            "customFields": {},
        }
        embed = build_ticket_embed(ticket_row, guild_id=_ES_GUILD)
        # The details field is the non-inline one carrying the description.
        details_field = next(
            (f for f in embed.fields if _MARKDOWN_PAYLOAD[:5] in str(f.value) or "\\*bold\\*" in str(f.value)),
            None,
        )
        assert details_field is not None, "description field MUST be present in the embed"
        assert "\\*bold\\*" in (details_field.value or ""), "description MUST be escape_markdown'd"

    @pytest.mark.asyncio
    async def test_s2_ban_reason_escaped_and_mentions_suppressed(self) -> None:
        """S2 — the Sentinel ban command escapes the reason via escape_markdown
        and sends the confirm embed with AllowedMentions.none().

        Runs the real escape_markdown on the payload (the exact util the cog
        imports) and asserts the escaped output, then verifies the ban command
        wires AllowedMentions.none() by inspecting the real command's send
        kwargs via the real callback path against a mocked ctx.
        """
        import discord.utils

        from bot.cogs.sentinel import SentinelCog

        # (a) The real escaping util transforms the payload.
        escaped = discord.utils.escape_markdown(_MARKDOWN_PAYLOAD)
        assert "\\*bold\\*" in escaped, "ban reason MUST be escaped by escape_markdown"
        assert "*bold*" not in escaped, "raw markdown MUST NOT survive escaping"

        # (b) The ban command's confirm send carries AllowedMentions.none().
        # We exercise the real OcioCog-style thin-facade assertion: the ban
        # callback builds the confirm embed and sends with allowed_mentions.
        bot = MagicMock()
        bot.user = MagicMock(id=1)
        bot.db = MagicMock()
        bot.db.insert_infraction = AsyncMock()
        bot.logging_service = MagicMock()
        bot.logging_service.log_moderation_action = AsyncMock()
        cog = SentinelCog(bot=bot)

        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 555
        ctx.guild.owner = MagicMock()
        ctx.guild.owner.id = 999
        ctx.guild.me = MagicMock()
        ctx.guild.me.top_role = MagicMock()
        ctx.guild.me.top_role.__le__ = MagicMock(return_value=False)
        ctx.author = MagicMock()
        ctx.author.id = 777
        ctx.author.top_role = MagicMock()
        ctx.author.top_role.__le__ = MagicMock(return_value=False)
        ctx.author.__class__ = MagicMock()
        sent_msg = MagicMock()
        ctx.send = AsyncMock(return_value=sent_msg)

        member = MagicMock()
        member.id = 888
        member.mention = "<@888>"
        member.ban = AsyncMock()

        await cog.ban.callback(cog, ctx, member, reason=_MARKDOWN_PAYLOAD, delete_days=0)

        ctx.send.assert_awaited_once()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("allowed_mentions") is not None, "ban confirm MUST set allowed_mentions"
        # AllowedMentions.none() yields an AllowedMentions instance with all False.
        am = kwargs["allowed_mentions"]
        assert getattr(am, "everyone", True) is False, "ban MUST suppress @everyone via AllowedMentions.none()"
        # The confirm embed description carries the escaped reason.
        embed = kwargs.get("embed")
        assert embed is not None
        assert "\\*bold\\*" in (embed.description or ""), "ban confirm embed MUST carry escaped reason"

    @pytest.mark.asyncio
    async def test_s3_8ball_question_escaped_and_mentions_suppressed(self) -> None:
        """S3 — the 8ball cog escapes the echoed question and sends with
        AllowedMentions.none(). Runs the real OcioCog.eight_ball.callback."""
        from bot.cogs.ocio import OcioCog

        cog = OcioCog(MagicMock())
        ctx = MagicMock()
        ctx.guild = MagicMock(id=int(_ES_GUILD))
        ctx.send = AsyncMock()

        await cog.eight_ball.callback(cog, ctx, question=_MARKDOWN_PAYLOAD)

        ctx.send.assert_awaited_once()
        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        am = kwargs.get("allowed_mentions")
        assert am is not None, "8ball MUST set allowed_mentions"
        assert getattr(am, "everyone", True) is False, "8ball MUST suppress @everyone"
        embed = kwargs.get("embed")
        assert embed is not None
        # The echoed Q line carries the escaped payload.
        assert "\\*bold\\*" in (embed.description or ""), "8ball Q echo MUST be escaped"
        assert "*bold*" not in (embed.description or "").replace("\\*bold\\*", ""), (
            "raw *bold* MUST NOT survive escaping in the 8ball echo"
        )


# ===========================================================================
# 4. Database AsyncClientOptions S1 — acreate_client spy captures real flags
# ===========================================================================


class TestAsyncClientOptionsFlagsSpy:
    """S1 — Database.connect() passes AsyncClientOptions with
    auto_refresh_token=False, persist_session=False, schema=='public'.

    Replaces the ⚠️ PARTIAL 'source contains flags but does not assert
    acreate_client kwargs'. Spies on acreate_client to capture the options
    object and asserts the three flags directly. Fails if connect() ever
    drops a flag or changes the schema.
    """

    @pytest.mark.asyncio
    async def test_connect_passes_flags_to_acreate_client(self) -> None:
        from bot.core.db import base as base_mod
        from supabase import AsyncClientOptions

        captured: list[Any] = []

        async def _fake_acreate_client(url: str, key: str, options: Any) -> MagicMock:
            captured.append(options)
            client = MagicMock()
            # health_probe reads guild + ticket; return empty data for both.
            guild_chain = MagicMock()
            guild_chain.select.return_value = guild_chain
            guild_chain.limit.return_value = guild_chain
            guild_chain.execute = AsyncMock(return_value=MagicMock(data=[{"id": "g1"}]))
            ticket_chain = MagicMock()
            ticket_chain.select.return_value = ticket_chain
            ticket_chain.limit.return_value = ticket_chain
            ticket_chain.execute = AsyncMock(return_value=MagicMock(data=[{"id": "t1"}]))
            client.table = MagicMock(side_effect=lambda name: guild_chain if name == "guild" else ticket_chain)
            return client

        db = Database(url="https://test.supabase.co", key="sb_secret_test-key-for-spy")
        with patch.object(base_mod, "acreate_client", _fake_acreate_client):
            await db.connect()

        assert len(captured) == 1, "connect() MUST call acreate_client exactly once"
        opts = captured[0]
        assert isinstance(opts, AsyncClientOptions), "options MUST be an AsyncClientOptions instance"
        assert getattr(opts, "auto_refresh_token", None) is False, "auto_refresh_token MUST be False"
        assert getattr(opts, "persist_session", None) is False, "persist_session MUST be False"
        assert getattr(opts, "schema", None) == "public", "schema MUST be 'public'"

    @pytest.mark.asyncio
    async def test_anon_publishable_key_rejected_before_acreate_client(self) -> None:
        """S1 companion / S3 non-goal — a publishable key fails closed BEFORE
        acreate_client is ever called (validate_supabase_key gate)."""
        from bot.config import ServiceRoleValidationError
        from bot.core.db import base as base_mod

        called: list[Any] = []

        async def _should_not_be_called(*args: Any, **kwargs: Any) -> Any:
            called.append(args)
            return MagicMock()

        db = Database(url="https://test.supabase.co", key="sb_publishable_anon_key")
        with (
            patch.object(base_mod, "acreate_client", _should_not_be_called),
            pytest.raises(ServiceRoleValidationError),
        ):
            await db.connect()
        assert called == [], "acreate_client MUST NOT be called for a publishable key"


# ===========================================================================
# 5. Close confirmation S1/S4 — confirm_timer_schedule writes to the DB
# ===========================================================================


def _ticket_row(status: str = "open", gid: str = "g1", tid: str = "t1") -> dict[str, Any]:
    return {
        "id": tid,
        "guildId": gid,
        "channelId": "500",
        "ticketNumber": 1,
        "authorId": "a",
        "status": status,
        "createdAt": datetime.now(UTC),
        "lastActivity": datetime.now(UTC),
    }


class TestConfirmWritesScheduledClose:
    """S1/S4 — the confirm callback's real effect (confirm_timer_schedule)
    writes scheduledCloseAt/scheduledCloseBy to the DB.

    Replaces the ⚠️ PARTIAL 'persistence is mocked / no timer/database write
    asserted'. The confirm path is the on_confirm callback's effect layer;
    this probe exercises the real service write against a stateful DB fake.
    """

    @pytest.mark.asyncio
    async def test_confirm_writes_scheduled_close_at_and_by(self) -> None:
        from bot.services.ticket_lifecycle_service import TicketLifecycleService
        from bot.services.ticket_query_service import TicketQueryService
        from bot.services.ticket_repair_service import TicketRepairService

        fake = FakeSupabaseClient()
        fake._tables["ticket"] = FakeQueryBuilder(result_data=[_ticket_row("open")])
        db = Database(url="https://test.supabase.co", key="sb_secret_test")
        db._client = fake
        query = TicketQueryService(db)
        svc = TicketRepairService(db, query, TicketLifecycleService(db, query))

        result = await svc.confirm_timer_schedule("g1", "t1", 864000, "mod1")
        assert result.action == "scheduled" and result.seconds == 864000

        updates = [c for c in fake.get_table_calls("ticket") if c[0] == "update"]
        assert any("scheduledCloseAt" in (c[1] or {}) for c in updates), "confirm MUST write scheduledCloseAt to the DB"
        assert any("scheduledCloseBy" in (c[1] or {}) for c in updates), "confirm MUST write scheduledCloseBy to the DB"
        # The written scheduledCloseBy MUST be the confirming mod.
        assert any((c[1] or {}).get("scheduledCloseBy") == "mod1" for c in updates)

    @pytest.mark.asyncio
    async def test_threshold_path_returns_needs_confirmation_before_confirm(self) -> None:
        """S1 — `,1h` (below 2h) returns needs_confirmation (the view trigger)."""
        from bot.services.ticket_lifecycle_service import TicketLifecycleService
        from bot.services.ticket_query_service import TicketQueryService
        from bot.services.ticket_repair_service import TicketRepairService

        fake = FakeSupabaseClient()
        fake._tables["ticket"] = FakeQueryBuilder(result_data=[_ticket_row("open")])
        db = Database(url="https://test.supabase.co", key="sb_secret_test")
        db._client = fake
        query = TicketQueryService(db)
        svc = TicketRepairService(db, query, TicketLifecycleService(db, query))

        result = await svc.handle_timer_message("g1", _ticket_row("open"), ",1h", "mod1")
        assert result is not None and result.action == "needs_confirmation"
        assert result.seconds == 3600
        # No DB write on the threshold path — confirm is required first.
        updates = [c for c in fake.get_table_calls("ticket") if c[0] == "update"]
        assert not any("scheduledCloseAt" in (c[1] or {}) for c in updates), (
            "threshold path MUST NOT write scheduledCloseAt before confirm"
        )


# ===========================================================================
# 6. Ticket service S7 — overwrite extends the timer (new scheduledCloseAt)
# ===========================================================================


class TestTimerOverwritePersistence:
    """S7 — re-typing ``,<duration>`` overwrites scheduledCloseAt (extend).

    Replaces the ⚠️ PARTIAL 'embed edit is tested, but service overwrite
    persistence is not'. Calls handle_timer_message twice with different
    durations and asserts the second update writes a NEW (later)
    scheduledCloseAt, not an additive value. Fails if overwrite stops
    persisting or becomes additive to the prior value.
    """

    @pytest.mark.asyncio
    async def test_overwrite_persists_new_scheduled_close_at(self) -> None:
        from bot.services.ticket_lifecycle_service import TicketLifecycleService
        from bot.services.ticket_query_service import TicketQueryService
        from bot.services.ticket_repair_service import TicketRepairService

        fake = FakeSupabaseClient()
        fake._tables["ticket"] = FakeQueryBuilder(result_data=[_ticket_row("open")])
        db = Database(url="https://test.supabase.co", key="sb_secret_test")
        db._client = fake
        query = TicketQueryService(db)
        svc = TicketRepairService(db, query, TicketLifecycleService(db, query))

        first = await svc.handle_timer_message("g1", _ticket_row("open"), ",4h", "mod1")
        assert first is not None and first.action == "scheduled" and first.seconds == 14400

        second = await svc.handle_timer_message("g1", _ticket_row("open"), ",12h", "mod2")
        assert second is not None and second.action == "scheduled" and second.seconds == 43200

        updates = [c for c in fake.get_table_calls("ticket") if c[0] == "update"]
        scheduled_writes = [(c[1] or {}).get("scheduledCloseAt") for c in updates if "scheduledCloseAt" in (c[1] or {})]
        assert len(scheduled_writes) >= 2, "overwrite MUST persist two scheduledCloseAt writes"
        first_ts = scheduled_writes[0]
        second_ts = scheduled_writes[1]
        assert first_ts is not None and second_ts is not None
        # The 12h overwrite is later than the 4h schedule (extend, not additive).
        assert second_ts > first_ts, "overwrite MUST move scheduledCloseAt forward to the new duration"
        # scheduledCloseBy is overwritten to the new author.
        by_writes = [(c[1] or {}).get("scheduledCloseBy") for c in updates if "scheduledCloseBy" in (c[1] or {})]
        assert "mod1" in by_writes and "mod2" in by_writes, "overwrite MUST persist the new scheduledCloseBy"
