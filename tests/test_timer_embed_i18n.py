"""Scheduled-close timer strings resolve through t() — no hardcoded copy.

The timer embed / confirm prompts previously carried hardcoded Spanish and
English fallback literals that bypassed ``t()`` (AGENTS.md i18n rule). All
strings MUST resolve through locale keys, with a forced-default-locale
retry as the only fallback tier.

Ref: clean-1.0 S0.11 (timer ``unix=`` kwarg fix) — also clears the
file-level i18n violations flagged while touching ticket services.
"""

from __future__ import annotations

import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core import i18n as i18n_mod
from bot.core.i18n import load_locales, set_guild_language, t
from bot.services.ticket_query_service import TicketQueryService
from bot.services.ticket_repair_service import TicketRepairService

load_locales()

_GID_ES = "555000111"
_GID_EN = "555000222"


@pytest.fixture(autouse=True)
def _guild_languages() -> None:
    set_guild_language(_GID_ES, "es")
    set_guild_language(_GID_EN, "en")


def _make_service() -> TicketRepairService:
    db = MagicMock()
    query = MagicMock(spec=TicketQueryService)
    lifecycle = MagicMock()
    return TicketRepairService(db, query, lifecycle)


def _make_channel() -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.pins = AsyncMock(return_value=[])
    sent = MagicMock()
    sent.pin = AsyncMock()
    channel.send = AsyncMock(return_value=sent)
    return channel


# ===========================================================================
# Timer embed — kwargs flow through t() on the FIRST resolution
# ===========================================================================


class TestTimerEmbedKwargsThroughT:
    @pytest.mark.asyncio
    async def test_title_and_description_formatted_without_i18n_warnings(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unix/remaining kwargs reach t(); no 'Missing placeholder' warnings."""
        svc = _make_service()
        channel = _make_channel()

        with caplog.at_level(logging.DEBUG, logger="bot.core.i18n"):
            await svc.upsert_timer_embed(channel, _GID_ES, "t1", 1_800_000_000, 3600)

        channel.send.assert_awaited_once()
        embed = channel.send.call_args.kwargs["embed"]
        expected_title = t(_GID_ES, "tickets.timer.scheduled_title", unix=1_800_000_000, remaining="1 hora")
        assert embed.title == expected_title, (
            f"title must be the single-pass localized format; got {embed.title!r}"
        )
        assert "1_800_000_000" in embed.title or "1800000000" in embed.title
        assert not any("Missing placeholder" in rec.message for rec in caplog.records), (
            "calling t() without kwargs triggers a spurious i18n warning — pass unix=/remaining="
        )

    @pytest.mark.asyncio
    async def test_localization_follows_guild_language(self) -> None:
        """EN guild gets the EN string, ES guild gets the ES string."""
        svc = _make_service()

        ch_en = _make_channel()
        await svc.upsert_timer_embed(ch_en, _GID_EN, "t1", 1_800_000_000, 3600)
        embed_en = ch_en.send.call_args.kwargs["embed"]
        assert embed_en.title.startswith("⏳ Closes"), f"EN title expected; got {embed_en.title!r}"

        ch_es = _make_channel()
        await svc.upsert_timer_embed(ch_es, _GID_ES, "t1", 1_800_000_000, 3600)
        embed_es = ch_es.send.call_args.kwargs["embed"]
        assert embed_es.title.startswith("⏳ Cierra"), f"ES title expected; got {embed_es.title!r}"

    @pytest.mark.asyncio
    async def test_degraded_locales_never_raise_and_warn(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Broken locale store: no exception, bare degradation, WARNING logged."""
        svc = _make_service()
        channel = _make_channel()
        monkeypatch.setattr(i18n_mod, "_locales", {})

        with caplog.at_level(logging.WARNING):
            await svc.upsert_timer_embed(channel, _GID_ES, "t1", 1_800_000_000, 3600)

        channel.send.assert_awaited_once()  # embed still delivered
        assert any(rec.levelno == logging.WARNING for rec in caplog.records), (
            "unresolved timer keys MUST be surfaced at WARNING instead of masked by literal copy"
        )


# ===========================================================================
# Confirm prompt helpers — resolve through t(), forced-default retry only
# ===========================================================================


class TestConfirmPromptThroughT:
    def test_title_resolves_localized(self) -> None:
        svc = _make_service()
        assert svc._confirm_prompt_title(_GID_ES) == "Confirmar Cierre Programado"
        assert svc._confirm_prompt_title(_GID_EN) == "Confirm Scheduled Close"

    def test_description_resolves_localized(self) -> None:
        svc = _make_service()
        assert svc._confirm_prompt_desc(_GID_ES) == (
            "El cierre se programará al confirmar. Tienes 30 segundos."
        )
        assert svc._confirm_prompt_desc(_GID_EN).startswith("The close will be scheduled")

    def test_degraded_store_returns_raw_key_without_literal_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no locales loaded the raw key surfaces — never hardcoded copy."""
        svc = _make_service()
        monkeypatch.setattr(i18n_mod, "_locales", {})
        assert svc._confirm_prompt_title(_GID_ES) == "tickets.timer.confirm_title"


# ===========================================================================
# Source hygiene — no hardcoded user-facing fallback literals remain
# ===========================================================================


def test_upsert_timer_embed_source_has_no_hardcoded_copy() -> None:
    """Guard: the timer region carries zero literal user-facing strings."""
    src = inspect.getsource(TicketRepairService.upsert_timer_embed)
    for literal in ("Cierra <t:", "Cierre programado"):
        assert literal not in src, f"hardcoded user-facing literal {literal!r} bypassing t()"
