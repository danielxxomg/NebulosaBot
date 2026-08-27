"""Unit tests for ticket i18n — verifying ticket commands return localized strings.

Tests that ticket embeds and responses use t() instead of hardcoded English.
Uses distinctive locale overrides so tests prove t() is called, not hardcoded strings.

Every command/embed concept is parametrized over the shared ES/EN locale matrix;
the EN override set is generated from the ES markers by suffix swap, so the two
locales stay structurally identical by construction.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.cogs.tickets import (
    TicketActionsView,
    TicketPanelView,
    TicketsCog,
    _build_ticket_embed,
)
from bot.core.i18n import load_locales, set_guild_language, t
from bot.models.ticket import Ticket
from tests.conftest import make_ctx, make_interaction, make_member

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ES_GUILD_ID = "123456789"
_EN_GUILD_ID = "987654321"

# Locale matrix shared by every command concept below.
_LOCALE_MATRIX = [
    pytest.param(_ES_GUILD_ID, "ES", id="es"),
    pytest.param(_EN_GUILD_ID, "EN", id="en"),
]

# Distinctive ES markers — intentionally ugly so they're unmistakable in
# assertions. The EN set is derived by replacing the ``_ES`` suffix with
# ``_EN``, guaranteeing both locales stay structurally identical.
_ES_MARKERS: dict[str, str] = {
    "common.footer": "NB • {timestamp}",
    "common.error.title": "ERR_ES",
    "common.success.title": "OK_ES",
    "common.info.title": "INFO_ES",
    "tickets.config_missing.title": "TICKET_NO_CONFIG_ES",
    "tickets.config_missing.description": "TICKET_NO_CONFIG_DESC_ES",
    "tickets.modal.title": "MODAL_TITLE_{category}_ES",
    "tickets.modal.subject_label": "MODAL_SUBJECT_LABEL_ES",
    "tickets.modal.subject_placeholder": "MODAL_SUBJECT_PH_ES",
    "tickets.modal.description_label": "MODAL_DESC_LABEL_ES",
    "tickets.modal.description_placeholder": "MODAL_DESC_PH_ES",
    "tickets.modal.empty_title": "MODAL_EMPTY_TITLE_ES",
    "tickets.modal.empty_title_description": "MODAL_EMPTY_TITLE_DESC_ES",
    "tickets.panel.server_only_title": "PANEL_GUILD_ONLY_ES",
    "tickets.panel.server_only_description": "PANEL_GUILD_ONLY_DESC_ES",
    "tickets.panel.no_categories_title": "PANEL_NO_CATS_ES",
    "tickets.panel.no_categories_description": "PANEL_NO_CATS_DESC_ES",
    "tickets.panel.select_placeholder": "SELECT_CAT_ES",
    "tickets.panel.success_title": "PANEL_OK_ES",
    "tickets.panel.success_description": "PANEL_OK_DESC_ES",
    "tickets.panel.deploy_error_title": "PANEL_ERR_ES",
    "tickets.panel.deploy_error_description": "PANEL_ERR_DESC_ES",
    "tickets.panel.permission_denied_title": "PANEL_PERM_ES",
    "tickets.panel.permission_denied_description": "PANEL_PERM_DESC_ES",
    "tickets.panel.open_button": "OPEN_BTN_ES",
    "tickets.create.server_only_title": "CREATE_GUILD_ONLY_ES",
    "tickets.create.server_only_description": "CREATE_GUILD_ONLY_DESC_ES",
    "tickets.create.duplicate_title": "CREATE_DUP_ES",
    "tickets.create.duplicate_description": "CREATE_DUP_DESC_{name}_ES",
    "tickets.create.check_failed_title": "CREATE_CHECK_ERR_ES",
    "tickets.create.check_failed_description": "CREATE_CHECK_ERR_DESC_ES",
    "tickets.create.failed_title": "CREATE_ERR_ES",
    "tickets.create.failed_description": "CREATE_ERR_DESC_ES",
    "tickets.create.success_title": "CREATE_OK_ES",
    "tickets.create.success_description": "CREATE_OK_DESC_{name}_{id}_ES",
    "tickets.list.id_label": "LIST_ID_ES",
    "tickets.list.position_label": "LIST_POS_ES",
    "tickets.list.failed_title": "LIST_ERR_ES",
    "tickets.list.failed_description": "LIST_ERR_DESC_ES",
    "tickets.list.empty_title": "LIST_EMPTY_ES",
    "tickets.list.empty_description": "LIST_EMPTY_DESC_ES",
    "tickets.list.title": "LIST_TITLE_ES",
    "tickets.delete.failed_title": "DEL_ERR_ES",
    "tickets.delete.failed_description": "DEL_ERR_DESC_ES",
    "tickets.delete.not_found_title": "DEL_NOT_FOUND_ES",
    "tickets.delete.not_found_description": "DEL_NOT_FOUND_DESC_{id}_ES",
    "tickets.delete.wrong_guild_title": "DEL_WRONG_GUILD_ES",
    "tickets.delete.wrong_guild_description": "DEL_WRONG_GUILD_DESC_ES",
    "tickets.delete.in_use_title": "DEL_IN_USE_ES",
    "tickets.delete.in_use_description": "DEL_IN_USE_DESC_{name}_{count}_ES",
    "tickets.delete.success_title": "DEL_OK_ES",
    "tickets.delete.success_description": "DEL_OK_DESC_{name}_ES",
    "tickets.open.server_only_title": "OPEN_GUILD_ONLY_ES",
    "tickets.open.server_only_description": "OPEN_GUILD_ONLY_DESC_ES",
    "tickets.open.no_categories_title": "OPEN_NO_CATS_ES",
    "tickets.open.no_categories_description": "OPEN_NO_CATS_DESC_ES",
    "tickets.open.select_category": "OPEN_SELECT_CAT_ES",
    "tickets.open.config_error_title": "OPEN_CFG_ERR_ES",
    "tickets.open.config_error_description": "OPEN_CFG_ERR_DESC_ES",
    "tickets.open.invalid_category_title": "OPEN_INV_CAT_ES",
    "tickets.open.invalid_category_description": "OPEN_INV_CAT_DESC_ES",
    "tickets.open.permission_denied_title": "OPEN_PERM_ES",
    "tickets.open.permission_denied_description": "OPEN_PERM_DESC_ES",
    "tickets.open.channel_failed_title": "OPEN_CH_FAIL_ES",
    "tickets.open.channel_failed_description": "OPEN_CH_FAIL_DESC_ES",
    "tickets.open.creation_failed_title": "OPEN_CR_FAIL_ES",
    "tickets.open.creation_failed_description": "OPEN_CR_FAIL_DESC_ES",
    "tickets.open.success_title": "OPEN_OK_ES",
    "tickets.open.success_description": "OPEN_OK_DESC_{channel}_ES",
    "tickets.open.welcome_title": "OPEN_WELCOME_{number}_ES",
    "tickets.open.welcome_title_with_subject": "OPEN_WELCOME_SUBJ_{number}_{subject}_ES",
    "tickets.open.welcome_description": "OPEN_WELCOME_DESC_ES",
    "tickets.open.welcome_claimed_title": "OPEN_CLAIMED_{number}_ES",
    "tickets.open.welcome_claimed_description": "OPEN_CLAIMED_DESC_ES",
    "tickets.open.welcome_claimed_by": "OPEN_CLAIMED_BY_ES",
    "tickets.open.author_field": "OPEN_AUTHOR_ES",
    "tickets.open.details_field": "OPEN_DETAILS_ES",
    "tickets.open.footer": "OPEN_FOOTER_ES",
    "tickets.actions.claim_button": "CLAIM_BTN_ES",
    "tickets.actions.close_button": "CLOSE_BTN_ES",
    "tickets.actions.claim_mods_only_title": "CLAIM_MOD_ES",
    "tickets.actions.claim_mods_only_description": "CLAIM_MOD_DESC_ES",
    "tickets.actions.claim_failed_title": "CLAIM_FAIL_ES",
    "tickets.actions.claim_failed_description": "CLAIM_FAIL_DESC_ES",
    "tickets.actions.claim_not_ticket_description": "CLAIM_NO_TICKET_ES",
    "tickets.actions.claim_already_closed_description": "CLAIM_CLOSED_ES",
    "tickets.actions.claim_already_claimed_title": "CLAIM_ALREADY_ES",
    "tickets.actions.claim_already_claimed_description": "CLAIM_ALREADY_DESC_{user}_ES",
    "tickets.actions.claim_generic_error_description": "CLAIM_ERR_DESC_ES",
    "tickets.actions.close_failed_title": "CLOSE_FAIL_ES",
    "tickets.actions.close_not_ticket_description": "CLOSE_NO_TICKET_ES",
    "tickets.actions.close_already_closed_description": "CLOSE_CLOSED_ES",
    "tickets.actions.close_author_or_mod_title": "CLOSE_AUTH_MOD_ES",
    "tickets.actions.close_author_or_mod_description": "CLOSE_AUTH_MOD_DESC_ES",
    "tickets.actions.close_db_error_title": "CLOSE_DB_ERR_ES",
    "tickets.actions.close_db_error_description": "CLOSE_DB_ERR_DESC_ES",
    "tickets.actions.close_success_title": "CLOSE_OK_ES",
    "tickets.actions.close_success_description": "CLOSE_OK_DESC_ES",
    "tickets.actions.closed_channel_title": "CLOSED_CH_TITLE_ES",
    "tickets.actions.closed_channel_message": "CLOSED_CH_MSG_ES",
    "tickets.actions.closed_channel_transcript": "CLOSED_CH_TRANS_ES",
    "tickets.actions.edit_category_audit_title": "AUDIT_TITLE_ES",
    "tickets.actions.edit_category_audit_description": "AUDIT_DESC_{old_category}_{new_category}_{actor}_ES",
    "tickets.subticket.help_title": "SUB_HELP_ES",
    "tickets.subticket.help_description": "SUB_HELP_DESC_ES",
    "tickets.subticket.server_only_title": "SUB_GUILD_ONLY_ES",
    "tickets.subticket.server_only_description": "SUB_GUILD_ONLY_DESC_ES",
    "tickets.subticket.owner_not_found_title": "SUB_OWNER_NF_ES",
    "tickets.subticket.owner_not_found_description": "SUB_OWNER_NF_DESC_ES",
    "tickets.subticket.owner_not_found_resolve_title": "SUB_OWNER_RESOLVE_ES",
    "tickets.subticket.owner_not_found_resolve_description": "SUB_OWNER_RESOLVE_DESC_ES",
    "tickets.subticket.not_ticket_title": "SUB_NO_TICKET_ES",
    "tickets.subticket.not_ticket_description": "SUB_NO_TICKET_DESC_ES",
    "tickets.subticket.lookup_failed_title": "SUB_LOOKUP_ERR_ES",
    "tickets.subticket.lookup_failed_description": "SUB_LOOKUP_ERR_DESC_ES",
    "tickets.subticket.number_failed_title": "SUB_NUM_ERR_ES",
    "tickets.subticket.number_failed_description": "SUB_NUM_ERR_DESC_ES",
    "tickets.subticket.channel_failed_title": "SUB_CH_ERR_ES",
    "tickets.subticket.channel_failed_description": "SUB_CH_ERR_DESC_ES",
    "tickets.subticket.creation_failed_title": "SUB_CR_ERR_ES",
    "tickets.subticket.creation_failed_description": "SUB_CR_ERR_DESC_ES",
    "tickets.subticket.success_title": "SUB_OK_ES",
    "tickets.subticket.success_description": "SUB_OK_DESC_{channel}_ES",
    "tickets.subticket.invalid_category_title": "SUB_INV_CAT_ES",
    "tickets.subticket.invalid_category_description": "SUB_INV_CAT_DESC_ES",
    "tickets.reopen.server_only_title": "REOPEN_GUILD_ONLY_ES",
    "tickets.reopen.server_only_description": "REOPEN_GUILD_ONLY_DESC_ES",
    "tickets.reopen.invalid_ref_title": "REOPEN_INV_REF_ES",
    "tickets.reopen.invalid_ref_description": "REOPEN_INV_REF_DESC_{ref}_ES",
    "tickets.reopen.lookup_failed_title": "REOPEN_LOOKUP_ERR_ES",
    "tickets.reopen.lookup_failed_description": "REOPEN_LOOKUP_ERR_DESC_ES",
    "tickets.reopen.not_found_title": "REOPEN_NF_ES",
    "tickets.reopen.not_found_description": "REOPEN_NF_DESC_{number}_ES",
    "tickets.reopen.not_found_uuid_title": "REOPEN_NF_UUID_ES",
    "tickets.reopen.not_found_uuid_description": "REOPEN_NF_UUID_DESC_{id}_ES",
    "tickets.reopen.wrong_guild_title": "REOPEN_WRONG_GUILD_ES",
    "tickets.reopen.wrong_guild_description": "REOPEN_WRONG_GUILD_DESC_ES",
    "tickets.reopen.not_ticket_title": "REOPEN_NO_TICKET_ES",
    "tickets.reopen.not_ticket_description": "REOPEN_NO_TICKET_DESC_ES",
    "tickets.reopen.failed_title": "REOPEN_FAIL_ES",
    "tickets.reopen.failed_description": "REOPEN_FAIL_DESC_ES",
    "tickets.reopen.not_closed_description": "REOPEN_NOT_CLOSED_{status}_ES",
    "tickets.reopen.success_title": "REOPEN_OK_ES",
    "tickets.reopen.success_description": "REOPEN_OK_DESC_ES",
    "tickets.transfer.server_only_title": "XFER_GUILD_ONLY_ES",
    "tickets.transfer.server_only_description": "XFER_GUILD_ONLY_DESC_ES",
    "tickets.transfer.not_ticket_title": "XFER_NO_TICKET_ES",
    "tickets.transfer.not_ticket_description": "XFER_NO_TICKET_DESC_ES",
    "tickets.transfer.lookup_failed_title": "XFER_LOOKUP_ERR_ES",
    "tickets.transfer.lookup_failed_description": "XFER_LOOKUP_ERR_DESC_ES",
    "tickets.transfer.failed_title": "XFER_FAIL_ES",
    "tickets.transfer.failed_description": "XFER_FAIL_DESC_ES",
    "tickets.transfer.success_title": "XFER_OK_ES",
    "tickets.transfer.success_description": "XFER_OK_DESC_{member}_ES",
    "tickets.note.help_title": "NOTE_HELP_ES",
    "tickets.note.help_description": "NOTE_HELP_DESC_ES",
    "tickets.note.add_lookup_failed_title": "NOTE_LOOKUP_ERR_ES",
    "tickets.note.add_lookup_failed_description": "NOTE_LOOKUP_ERR_DESC_ES",
    "tickets.note.add_not_ticket_title": "NOTE_NO_TICKET_ES",
    "tickets.note.add_not_ticket_description": "NOTE_NO_TICKET_DESC_ES",
    "tickets.note.add_failed_title": "NOTE_ADD_ERR_ES",
    "tickets.note.add_failed_description": "NOTE_ADD_ERR_DESC_ES",
    "tickets.note.add_success_title": "NOTE_ADD_OK_ES",
    "tickets.note.add_success_description": "NOTE_ADD_OK_DESC_{id}_ES",
    "tickets.note.list_no_notes_title": "NOTE_LIST_EMPTY_ES",
    "tickets.note.list_no_notes_description": "NOTE_LIST_EMPTY_DESC_ES",
    "tickets.note.list_title": "NOTE_LIST_TITLE_ES",
    "tickets.note.list_dm_failed_title": "NOTE_DM_ERR_ES",
    "tickets.note.list_dm_failed_description": "NOTE_DM_ERR_DESC_ES",
    "tickets.note.list_sent_title": "NOTE_SENT_ES",
    "tickets.note.list_sent_description": "NOTE_SENT_DESC_ES",
    "tickets.note.delete_lookup_failed_title": "NOTE_DEL_LOOKUP_ES",
    "tickets.note.delete_lookup_failed_description": "NOTE_DEL_LOOKUP_DESC_ES",
    "tickets.note.delete_not_ticket_title": "NOTE_DEL_NO_TICKET_ES",
    "tickets.note.delete_not_ticket_description": "NOTE_DEL_NO_TICKET_DESC_ES",
    "tickets.note.delete_failed_title": "NOTE_DEL_ERR_ES",
    "tickets.note.delete_failed_description": "NOTE_DEL_ERR_DESC_ES",
    "tickets.note.delete_success_title": "NOTE_DEL_OK_ES",
    "tickets.note.delete_success_description": "NOTE_DEL_OK_DESC_{id}_ES",
}


def _build_nested_locale(markers: dict[str, str]) -> dict:
    """Convert flat dot-notation keys into a nested dict for locale JSON."""
    result: dict = {}
    for key, value in markers.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result


def _swap_suffix(markers: dict[str, str], sfx: str) -> dict[str, str]:
    """Derive a sibling-locale marker set by swapping the ``_ES`` suffix."""
    return {key: value.replace("_ES", sfx) for key, value in markers.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ticket_row(
    ticket_number: int = 1,
    status: str = "open",
    channel_id: str = "444444444",
    guild_id: str = _ES_GUILD_ID,
) -> dict:
    """Return a sample ticket DB row."""
    return {
        "id": f"ticket-uuid-{ticket_number:04d}",
        "ticketNumber": ticket_number,
        "guildId": guild_id,
        "authorId": "111111111",
        "channelId": channel_id,
        "categoryId": "cat-uuid-001",
        "status": status,
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": datetime.now(UTC),
        "closedAt": None,
        "lastActivity": datetime.now(UTC),
    }


def _category_row(guild_id: str = _ES_GUILD_ID) -> dict:
    """Return a sample ticket category DB row."""
    return {
        "id": "cat-uuid-001",
        "guildId": guild_id,
        "name": "Support",
        "emoji": "🎫",
        "description": "General support",
        "position": 1,
        "active": True,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_ticket_i18n(tmp_path: Path) -> Generator[None, None, None]:
    """Load distinctive locale overrides for ticket strings.

    Uses strings that are DIFFERENT from any hardcoded default so tests can
    prove t() is being called.
    """
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "es.json").write_text(json.dumps(_build_nested_locale(_ES_MARKERS)), encoding="utf-8")
    (locale_dir / "en.json").write_text(
        json.dumps(_build_nested_locale(_swap_suffix(_ES_MARKERS, "_EN"))),
        encoding="utf-8",
    )

    load_locales(locale_dir)
    set_guild_language(_ES_GUILD_ID, "es")
    set_guild_language(_EN_GUILD_ID, "en")

    yield


@pytest.fixture
def ticket_bot() -> MagicMock:
    """Return a mock NebulosaBot for tickets i18n tests."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.ticket_service = MagicMock()
    bot.ticket_service.create_ticket = AsyncMock()
    bot.ticket_service.close_ticket = AsyncMock()
    bot.ticket_service.claim_ticket = AsyncMock()
    bot.ticket_service.get_stale_tickets = AsyncMock()
    bot.ticket_service.reopen_ticket = AsyncMock()
    bot.ticket_service.create_subticket = AsyncMock()
    bot.ticket_service.is_ticket_channel = MagicMock(return_value=False)
    bot.ticket_service.sync_channel_cache = MagicMock()
    bot.transcript_service = MagicMock()
    bot.transcript_service.generate = AsyncMock()
    bot.transcript_service.upload = AsyncMock()
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock()
    bot.guilds = []
    return bot


@pytest.fixture
def cog(ticket_bot: MagicMock) -> TicketsCog:
    """Return a TicketsCog wired to the shared mock bot.

    Language resolution happens inside t() from ``ctx.guild.id``, so a single
    cog instance serves both locales of the matrix.
    """
    return TicketsCog(bot=ticket_bot)


def _make_ctx(guild_id: int) -> MagicMock:
    """Build a spec'd Context from the shared factory plus ticket extras."""
    author = make_member(member_id=111111111)
    ctx = make_ctx(guild_id=guild_id, author=author)
    ctx.interaction = None
    ctx.channel.id = 444444444
    return ctx


def _make_interaction(
    guild_id: int,
    *,
    client: MagicMock | None = None,
    admin: bool = False,
) -> MagicMock:
    """Build a mock Interaction wired with response mocks for view callbacks."""
    interaction = make_interaction(
        guild_id=guild_id,
        client=client,
        user=make_member(member_id=111111111, admin=admin),
    )
    interaction.response.send_message = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# Command-level i18n concepts — each parametrized over the ES/EN matrix
# ---------------------------------------------------------------------------


class TestTicketConfigMissingI18n:
    """subticket_create with unconfigured category uses t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_config_missing_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Subticket create with no ticket_category_id → localized error."""
        ctx = _make_ctx(int(guild_id))
        ctx.guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.CategoryChannel))

        config = MagicMock()
        config.ticket_category_id = None
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        await cog.subticket_create.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"TICKET_NO_CONFIG_{suffix}" in embed.title


class TestTicketOpenNoCategoriesI18n:
    """TicketPanelView.open_ticket_button uses t() for no-categories error."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_no_categories_is_localized(
        self,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """No categories → localized error embed."""
        interaction = _make_interaction(int(guild_id), client=ticket_bot)

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        view = TicketPanelView()
        await view.open_ticket_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        # Should use localized string, not hardcoded English
        assert f"PANEL_NO_CATS_{suffix}" in embed.title


class TestTicketClaimI18n:
    """claim button error messages use t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_claim_not_ticket_is_localized(
        self,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Claim on non-ticket channel → localized error."""
        interaction = _make_interaction(int(guild_id), client=ticket_bot, admin=True)
        interaction.response.edit_message = AsyncMock()
        interaction.channel_id = 444444444

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.claim_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"CLAIM_FAIL_{suffix}" in embed.title
        assert f"CLAIM_NO_TICKET_{suffix}" in embed.description


class TestTicketCloseI18n:
    """close button error messages use t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_close_not_ticket_is_localized(
        self,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Close on non-ticket channel → localized error."""
        interaction = _make_interaction(int(guild_id), client=ticket_bot)
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.channel_id = 444444444
        interaction.channel = MagicMock()

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.close_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"CLOSE_FAIL_{suffix}" in embed.title
        assert f"CLOSE_NO_TICKET_{suffix}" in embed.description

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_close_already_closed_is_localized(
        self,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Close already-closed ticket → localized error."""
        interaction = _make_interaction(int(guild_id), client=ticket_bot)
        interaction.channel_id = 444444444
        interaction.channel = MagicMock()

        row = _ticket_row(status="closed", guild_id=guild_id)
        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=row)

        view = TicketActionsView()
        await view.close_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"CLOSE_FAIL_{suffix}" in embed.title
        assert f"CLOSE_CLOSED_{suffix}" in embed.description


class TestSubticketHelpI18n:
    """S6A slash-only: subticket group has no fallback help — covered by create subcommand."""

    def test_subticket_is_group_without_callback(self, cog: TicketsCog) -> None:
        from discord import app_commands as _a

        assert isinstance(cog.subticket, _a.Group)
        assert not hasattr(cog.subticket, "callback")

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def _test_subticket_help_is_localized_skipped(
        self,
        cog: TicketsCog,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/subticket help → localized embed."""
        ctx = _make_ctx(int(guild_id))

        await cog.subticket.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"SUB_HELP_{suffix}" in embed.title


class TestReopenI18n:
    """/reopen error messages use t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_reopen_not_ticket_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/reopen in non-ticket channel → localized error."""
        ctx = _make_ctx(int(guild_id))

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        await cog.reopen.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"REOPEN_NO_TICKET_{suffix}" in embed.title


class TestNoteHelpI18n:
    """S6A slash-only: note group has no fallback help — covered by subcommands."""

    def test_note_is_group_without_callback(self, cog: TicketsCog) -> None:
        from discord import app_commands as _a

        assert isinstance(cog.note, _a.Group)
        assert not hasattr(cog.note, "callback")

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def _test_note_help_is_localized_skipped(
        self,
        cog: TicketsCog,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/note help → localized embed."""
        ctx = _make_ctx(int(guild_id))

        await cog.note.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"NOTE_HELP_{suffix}" in embed.title


class TestListCategoriesI18n:
    """/list_categories uses t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_list_categories_empty_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/list_categories with no categories → localized embed."""
        ctx = _make_ctx(int(guild_id))

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        await cog.list_categories.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"LIST_EMPTY_{suffix}" in embed.title


class TestCreateCategoryI18n:
    """/create_category uses t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_create_category_duplicate_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/create_category with duplicate name → localized error."""
        ctx = _make_ctx(int(guild_id))

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[_category_row(guild_id=guild_id)])

        await cog.create_category.callback(cog, ctx, name="Support")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"CREATE_DUP_{suffix}" in embed.title


class TestDeleteCategoryI18n:
    """/delete_category uses t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_delete_category_not_found_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/delete_category with invalid ID → localized error."""
        ctx = _make_ctx(int(guild_id))

        ticket_bot.db.get_ticket_category = AsyncMock(return_value=None)

        await cog.delete_category.callback(cog, ctx, category_id="nonexistent")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"DEL_NOT_FOUND_{suffix}" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_delete_category_in_use_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/delete_category with open tickets → localized error."""
        ctx = _make_ctx(int(guild_id))

        row = _category_row(guild_id=guild_id)
        ticket_bot.db.get_ticket_category = AsyncMock(return_value=row)
        ticket_bot.db.count_open_tickets_by_category = AsyncMock(return_value=3)

        await cog.delete_category.callback(cog, ctx, category_id="cat-uuid-001")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"DEL_IN_USE_{suffix}" in embed.title


class TestTransferI18n:
    """/transfer uses t()."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_transfer_not_ticket_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/transfer in non-ticket channel → localized error."""
        ctx = _make_ctx(int(guild_id))

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        target = make_member(member_id=222222222)

        await cog.transfer.callback(cog, ctx, member=target)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert f"XFER_NO_TICKET_{suffix}" in embed.title


class TestTicketEmbedI18n:
    """_build_ticket_embed uses t() for titles and descriptions."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_open_ticket_embed_is_localized(self, guild_id: str, suffix: str) -> None:
        """Open ticket embed uses localized strings."""
        ticket = Ticket.from_db_row(_ticket_row(status="open", guild_id=guild_id))
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_WELCOME_" in embed.title
        assert embed.description is not None
        assert f"OPEN_WELCOME_DESC_{suffix}" in embed.description

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_claimed_ticket_embed_is_localized(self, guild_id: str, suffix: str) -> None:
        """Claimed ticket embed uses localized strings."""
        ticket = Ticket.from_db_row(_ticket_row(status="claimed", guild_id=guild_id))
        claimed_by = MagicMock()
        claimed_by.mention = "<@999999>"
        embed = _build_ticket_embed(ticket, claimed_by=claimed_by, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_CLAIMED_" in embed.title
        assert embed.description is not None
        assert f"OPEN_CLAIMED_DESC_{suffix}" in embed.description


class TestTicketEmbedSubjectI18n:
    """build_ticket_embed subject handling uses localized keys."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_embed_title_with_subject(self, guild_id: str, suffix: str) -> None:
        """Ticket with subject → embed title uses title_with_subject key."""
        row = _ticket_row(status="open", guild_id=guild_id)
        row["subject"] = "Login broken"
        ticket = Ticket.from_db_row(row)
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_WELCOME_SUBJ_" in embed.title
        assert "Login broken" in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_embed_title_fallback_when_no_subject(self, guild_id: str, suffix: str) -> None:
        """Ticket without subject → embed title uses welcome_title fallback."""
        row = _ticket_row(status="open", guild_id=guild_id)
        row["subject"] = None
        ticket = Ticket.from_db_row(row)
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_WELCOME_" in embed.title
        assert f"_{suffix}" in embed.title
        assert "SUBJ" not in embed.title

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_embed_description_field_when_present(self, guild_id: str, suffix: str) -> None:
        """Ticket with description → embed includes details field."""
        row = _ticket_row(status="open", guild_id=guild_id)
        row["description"] = "Cannot access since Monday"
        ticket = Ticket.from_db_row(row)
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        field_names = [f.name for f in embed.fields]
        assert f"OPEN_DETAILS_{suffix}" in field_names

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_embed_no_description_field_when_absent(self, guild_id: str, suffix: str) -> None:
        """Ticket without description → embed has no details field."""
        row = _ticket_row(status="open", guild_id=guild_id)
        row["description"] = None
        ticket = Ticket.from_db_row(row)
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        field_names = [f.name for f in embed.fields]
        assert f"OPEN_DETAILS_{suffix}" not in field_names


class TestModalI18nKeys:
    """modal i18n keys resolve for both locales."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_modal_keys_resolve(self, guild_id: str, suffix: str) -> None:
        """Modal i18n keys resolve with the expected marker text."""
        assert t(guild_id, "tickets.modal.title", category="Support") == (f"MODAL_TITLE_Support_{suffix}")
        assert t(guild_id, "tickets.modal.subject_label") == f"MODAL_SUBJECT_LABEL_{suffix}"
        assert t(guild_id, "tickets.modal.subject_placeholder") == f"MODAL_SUBJECT_PH_{suffix}"
        assert t(guild_id, "tickets.modal.description_label") == f"MODAL_DESC_LABEL_{suffix}"
        assert t(guild_id, "tickets.modal.description_placeholder") == f"MODAL_DESC_PH_{suffix}"
        assert t(guild_id, "tickets.modal.empty_title") == f"MODAL_EMPTY_TITLE_{suffix}"
        assert t(guild_id, "tickets.modal.empty_title_description") == (f"MODAL_EMPTY_TITLE_DESC_{suffix}")


# ---------------------------------------------------------------------------
# Button labels are localized when guild_id is provided
# ---------------------------------------------------------------------------


class TestButtonLabelI18n:
    """persistent view button labels use t() when guild_id is provided."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_panel_view_open_button(self, guild_id: str, suffix: str) -> None:
        """TicketPanelView with guild_id → button label localized."""
        view = TicketPanelView(guild_id=guild_id)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == f"OPEN_BTN_{suffix}"

    def test_panel_view_no_guild_default(self) -> None:
        """TicketPanelView without guild_id → Spanish default label preserved."""
        view = TicketPanelView()
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "Abrir Ticket"

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_actions_view_buttons(self, guild_id: str, suffix: str) -> None:
        """TicketActionsView with guild_id → claim/close labels localized."""
        view = TicketActionsView(guild_id=guild_id)
        buttons = {c.custom_id: c for c in view.children if isinstance(c, discord.ui.Button)}
        assert buttons["ticket:claim"].label == f"CLAIM_BTN_{suffix}"
        assert buttons["ticket:close"].label == f"CLOSE_BTN_{suffix}"

    def test_actions_view_no_guild_default(self) -> None:
        """TicketActionsView without guild_id → Spanish default labels preserved."""
        view = TicketActionsView()
        buttons = {c.custom_id: c for c in view.children if isinstance(c, discord.ui.Button)}
        assert buttons["ticket:claim"].label == "Reclamar"
        assert buttons["ticket:close"].label == "Cerrar"


# ---------------------------------------------------------------------------
# Dynamic label resolution at interaction time
# ---------------------------------------------------------------------------


class TestDynamicLabelResolution:
    """button labels resolve via t() at INTERACTION time, not just construction."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_panel_open_label_updates_at_interaction(
        self,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Panel open button label resolves at callback time."""
        view = TicketPanelView()  # No guild_id → Spanish default "Abrir Ticket"

        interaction = _make_interaction(int(guild_id))
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_categories = AsyncMock(return_value=[])

        open_button = next(
            c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:open"
        )
        await open_button.callback(interaction)

        # After callback, label should be updated to the guild language.
        assert open_button.label == f"OPEN_BTN_{suffix}"

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_actions_claim_label_updates_at_interaction(
        self,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Claim button label resolves at callback time."""
        view = TicketActionsView()  # No guild_id → default labels

        interaction = _make_interaction(int(guild_id), admin=True)
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_by_channel = AsyncMock(return_value=None)
        interaction.channel_id = 444444444
        interaction.response.edit_message = AsyncMock()

        claim_button = next(
            c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:claim"
        )
        await claim_button.callback(interaction)

        assert claim_button.label == f"CLAIM_BTN_{suffix}"

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_actions_close_label_updates_at_interaction(
        self,
        guild_id: str,
        suffix: str,
    ) -> None:
        """Close button label resolves at callback time."""
        view = TicketActionsView()  # No guild_id → default labels

        interaction = _make_interaction(int(guild_id))
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_by_channel = AsyncMock(return_value=None)
        interaction.channel_id = 444444444
        interaction.channel = MagicMock()

        close_button = next(
            c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:close"
        )
        await close_button.callback(interaction)

        assert close_button.label == f"CLOSE_BTN_{suffix}"


# ---------------------------------------------------------------------------
# reopen ValueError surfaces localized error, not service's raw Spanish text
# ---------------------------------------------------------------------------


class TestReopenNotClosedI18n:
    """/reopen ValueError surfaces localized error, not service's raw text."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    async def test_reopen_not_closed_is_localized(
        self,
        cog: TicketsCog,
        ticket_bot: MagicMock,
        guild_id: str,
        suffix: str,
    ) -> None:
        """/reopen on open ticket → localized error (raw service text replaced)."""
        ctx = _make_ctx(int(guild_id))

        row = _ticket_row(status="open", guild_id=guild_id)
        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=row)

        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            side_effect=ValueError("Solo se pueden reabrir tickets cerrados. Estado actual: open")
        )

        await cog.reopen.callback(cog, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        # Must use t() localized string, NOT the raw Spanish service text
        assert f"REOPEN_NOT_CLOSED_open_{suffix}" in embed.description
        assert "Solo se pueden" not in embed.description


# ---------------------------------------------------------------------------
# Production es.json contract — fixed keys must stay Spanish
# ---------------------------------------------------------------------------


class TestEsJsonTranslations:
    """Test that es.json has Spanish text, not English, for the fixed keys."""

    def test_claim_generic_error_is_spanish(self) -> None:
        """es.json claim_generic_error_description must be Spanish."""
        es_path = Path("bot/locales/es.json")
        data = json.loads(es_path.read_text(encoding="utf-8"))
        value = data["tickets"]["actions"]["claim_generic_error_description"]
        # Must NOT be the English text
        assert "Could not claim" not in value
        # Must contain Spanish words
        assert "reclamar" in value.lower() or "intent" in value.lower()

    def test_closed_channel_transcript_is_spanish(self) -> None:
        """es.json closed_channel_transcript must use Spanish 'Transcripción'."""
        es_path = Path("bot/locales/es.json")
        data = json.loads(es_path.read_text(encoding="utf-8"))
        value = data["tickets"]["actions"]["closed_channel_transcript"]
        # Must NOT use English "Transcript"
        assert "Transcript" not in value
        # Must use Spanish equivalent
        assert "Transcripción" in value or "transcripción" in value


# ---------------------------------------------------------------------------
# Edit category audit i18n keys
# ---------------------------------------------------------------------------


class TestEditCategoryAuditI18n:
    """edit_category_audit_title/description keys in both locales."""

    @pytest.mark.parametrize("guild_id,suffix", _LOCALE_MATRIX)
    def test_edit_category_audit_keys_resolve(self, guild_id: str, suffix: str) -> None:
        """Audit title and description resolve to non-empty localized strings."""
        title = t(guild_id, "tickets.actions.edit_category_audit_title")
        assert isinstance(title, str) and len(title) > 0
        assert f"AUDIT_TITLE_{suffix}" == title

        desc = t(guild_id, "tickets.actions.edit_category_audit_description")
        assert isinstance(desc, str) and len(desc) > 0
        assert f"AUDIT_DESC_{{old_category}}_{{new_category}}_{{actor}}_{suffix}" == desc

    def test_edit_category_audit_placeholders_resolve(self) -> None:
        """Audit description placeholders resolve with no leftover braces."""
        result = t(
            _ES_GUILD_ID,
            "tickets.actions.edit_category_audit_description",
            old_category="Support",
            new_category="Billing",
            actor="<@123>",
        )
        assert "Support" in result
        assert "Billing" in result
        assert "<@123>" in result
        # No unresolved placeholders
        assert "{" not in result


# ---------------------------------------------------------------------------
# Production locale file contract — audit keys must exist in real JSON files
# ---------------------------------------------------------------------------


class TestProductionLocaleAuditKeys:
    """bot/locales/{en,es}.json contain the audit keys with required placeholders."""

    @staticmethod
    def _load_locale(filename: str) -> dict:
        """Load a production locale JSON file."""
        path = Path("bot/locales") / filename
        return json.loads(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("filename", ["en.json", "es.json"])
    def test_audit_keys_exist(self, filename: str) -> None:
        """Locale file MUST contain both edit_category_audit keys."""
        data = self._load_locale(filename)
        actions = data["tickets"]["actions"]
        assert "edit_category_audit_title" in actions
        assert "edit_category_audit_description" in actions

    @pytest.mark.parametrize("filename", ["en.json", "es.json"])
    def test_audit_description_has_all_placeholders(self, filename: str) -> None:
        """Audit description MUST contain all three placeholders."""
        data = self._load_locale(filename)
        desc = data["tickets"]["actions"]["edit_category_audit_description"]
        assert "{old_category}" in desc
        assert "{new_category}" in desc
        assert "{actor}" in desc
