"""Unit tests for ticket i18n — verifying ticket commands return localized strings.

Tests that ticket embeds and responses use t() instead of hardcoded English.
Uses distinctive locale overrides so tests prove t() is called, not hardcoded strings.

Strict TDD: RED phase — tests written BEFORE the i18n migration.
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
from bot.core.i18n import load_locales, set_guild_language
from bot.models.ticket import Ticket

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ES_GUILD_ID = "123456789"
_EN_GUILD_ID = "987654321"

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

    Uses strings that are DIFFERENT from the current hardcoded English
    so tests can prove t() is being called.
    """
    from bot.core import i18n as i18n_mod

    # Save original state.
    orig_locales = dict(i18n_mod._locales)
    orig_guild_langs = dict(i18n_mod._guild_languages)

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    es_data = {
        "common": {
            "footer": "NB • {timestamp}",
            "error": {"title": "ERR_ES"},
            "success": {"title": "OK_ES"},
            "info": {"title": "INFO_ES"},
        },
        "tickets": {
            "config_missing": {
                "title": "TICKET_NO_CONFIG_ES",
                "description": "TICKET_NO_CONFIG_DESC_ES",
            },
            "panel": {
                "server_only_title": "PANEL_GUILD_ONLY_ES",
                "server_only_description": "PANEL_GUILD_ONLY_DESC_ES",
                "no_categories_title": "PANEL_NO_CATS_ES",
                "no_categories_description": "PANEL_NO_CATS_DESC_ES",
                "select_placeholder": "SELECT_CAT_ES",
                "success_title": "PANEL_OK_ES",
                "success_description": "PANEL_OK_DESC_ES",
                "deploy_error_title": "PANEL_ERR_ES",
                "deploy_error_description": "PANEL_ERR_DESC_ES",
                "permission_denied_title": "PANEL_PERM_ES",
                "permission_denied_description": "PANEL_PERM_DESC_ES",
                "open_button": "OPEN_BTN_ES",
            },
            "create": {
                "server_only_title": "CREATE_GUILD_ONLY_ES",
                "server_only_description": "CREATE_GUILD_ONLY_DESC_ES",
                "duplicate_title": "CREATE_DUP_ES",
                "duplicate_description": "CREATE_DUP_DESC_{name}_ES",
                "check_failed_title": "CREATE_CHECK_ERR_ES",
                "check_failed_description": "CREATE_CHECK_ERR_DESC_ES",
                "failed_title": "CREATE_ERR_ES",
                "failed_description": "CREATE_ERR_DESC_ES",
                "success_title": "CREATE_OK_ES",
                "success_description": "CREATE_OK_DESC_{name}_{id}_ES",
            },
            "list": {
                "id_label": "LIST_ID_ES",
                "position_label": "LIST_POS_ES",
                "failed_title": "LIST_ERR_ES",
                "failed_description": "LIST_ERR_DESC_ES",
                "empty_title": "LIST_EMPTY_ES",
                "empty_description": "LIST_EMPTY_DESC_ES",
                "title": "LIST_TITLE_ES",
            },
            "delete": {
                "failed_title": "DEL_ERR_ES",
                "failed_description": "DEL_ERR_DESC_ES",
                "not_found_title": "DEL_NOT_FOUND_ES",
                "not_found_description": "DEL_NOT_FOUND_DESC_{id}_ES",
                "wrong_guild_title": "DEL_WRONG_GUILD_ES",
                "wrong_guild_description": "DEL_WRONG_GUILD_DESC_ES",
                "in_use_title": "DEL_IN_USE_ES",
                "in_use_description": "DEL_IN_USE_DESC_{name}_{count}_ES",
                "success_title": "DEL_OK_ES",
                "success_description": "DEL_OK_DESC_{name}_ES",
            },
            "open": {
                "server_only_title": "OPEN_GUILD_ONLY_ES",
                "server_only_description": "OPEN_GUILD_ONLY_DESC_ES",
                "no_categories_title": "OPEN_NO_CATS_ES",
                "no_categories_description": "OPEN_NO_CATS_DESC_ES",
                "select_category": "OPEN_SELECT_CAT_ES",
                "config_error_title": "OPEN_CFG_ERR_ES",
                "config_error_description": "OPEN_CFG_ERR_DESC_ES",
                "invalid_category_title": "OPEN_INV_CAT_ES",
                "invalid_category_description": "OPEN_INV_CAT_DESC_ES",
                "permission_denied_title": "OPEN_PERM_ES",
                "permission_denied_description": "OPEN_PERM_DESC_ES",
                "channel_failed_title": "OPEN_CH_FAIL_ES",
                "channel_failed_description": "OPEN_CH_FAIL_DESC_ES",
                "creation_failed_title": "OPEN_CR_FAIL_ES",
                "creation_failed_description": "OPEN_CR_FAIL_DESC_ES",
                "success_title": "OPEN_OK_ES",
                "success_description": "OPEN_OK_DESC_{channel}_ES",
                "welcome_title": "OPEN_WELCOME_{number}_ES",
                "welcome_description": "OPEN_WELCOME_DESC_ES",
                "welcome_claimed_title": "OPEN_CLAIMED_{number}_ES",
                "welcome_claimed_description": "OPEN_CLAIMED_DESC_ES",
                "welcome_claimed_by": "OPEN_CLAIMED_BY_ES",
                "author_field": "OPEN_AUTHOR_ES",
                "footer": "OPEN_FOOTER_ES",
            },
            "actions": {
                "claim_button": "CLAIM_BTN_ES",
                "close_button": "CLOSE_BTN_ES",
                "claim_mods_only_title": "CLAIM_MOD_ES",
                "claim_mods_only_description": "CLAIM_MOD_DESC_ES",
                "claim_failed_title": "CLAIM_FAIL_ES",
                "claim_failed_description": "CLAIM_FAIL_DESC_ES",
                "claim_not_ticket_description": "CLAIM_NO_TICKET_ES",
                "claim_already_closed_description": "CLAIM_CLOSED_ES",
                "claim_already_claimed_title": "CLAIM_ALREADY_ES",
                "claim_already_claimed_description": "CLAIM_ALREADY_DESC_{user}_ES",
                "claim_generic_error_description": "CLAIM_ERR_DESC_ES",
                "close_failed_title": "CLOSE_FAIL_ES",
                "close_not_ticket_description": "CLOSE_NO_TICKET_ES",
                "close_already_closed_description": "CLOSE_CLOSED_ES",
                "close_author_or_mod_title": "CLOSE_AUTH_MOD_ES",
                "close_author_or_mod_description": "CLOSE_AUTH_MOD_DESC_ES",
                "close_db_error_title": "CLOSE_DB_ERR_ES",
                "close_db_error_description": "CLOSE_DB_ERR_DESC_ES",
                "close_success_title": "CLOSE_OK_ES",
                "close_success_description": "CLOSE_OK_DESC_ES",
                "closed_channel_title": "CLOSED_CH_TITLE_ES",
                "closed_channel_message": "CLOSED_CH_MSG_ES",
                "closed_channel_transcript": "CLOSED_CH_TRANS_ES",
            },
            "subticket": {
                "help_title": "SUB_HELP_ES",
                "help_description": "SUB_HELP_DESC_ES",
                "server_only_title": "SUB_GUILD_ONLY_ES",
                "server_only_description": "SUB_GUILD_ONLY_DESC_ES",
                "owner_not_found_title": "SUB_OWNER_NF_ES",
                "owner_not_found_description": "SUB_OWNER_NF_DESC_ES",
                "owner_not_found_resolve_title": "SUB_OWNER_RESOLVE_ES",
                "owner_not_found_resolve_description": "SUB_OWNER_RESOLVE_DESC_ES",
                "not_ticket_title": "SUB_NO_TICKET_ES",
                "not_ticket_description": "SUB_NO_TICKET_DESC_ES",
                "lookup_failed_title": "SUB_LOOKUP_ERR_ES",
                "lookup_failed_description": "SUB_LOOKUP_ERR_DESC_ES",
                "number_failed_title": "SUB_NUM_ERR_ES",
                "number_failed_description": "SUB_NUM_ERR_DESC_ES",
                "channel_failed_title": "SUB_CH_ERR_ES",
                "channel_failed_description": "SUB_CH_ERR_DESC_ES",
                "creation_failed_title": "SUB_CR_ERR_ES",
                "creation_failed_description": "SUB_CR_ERR_DESC_ES",
                "success_title": "SUB_OK_ES",
                "success_description": "SUB_OK_DESC_{channel}_ES",
                "invalid_category_title": "SUB_INV_CAT_ES",
                "invalid_category_description": "SUB_INV_CAT_DESC_ES",
            },
            "reopen": {
                "server_only_title": "REOPEN_GUILD_ONLY_ES",
                "server_only_description": "REOPEN_GUILD_ONLY_DESC_ES",
                "invalid_ref_title": "REOPEN_INV_REF_ES",
                "invalid_ref_description": "REOPEN_INV_REF_DESC_{ref}_ES",
                "lookup_failed_title": "REOPEN_LOOKUP_ERR_ES",
                "lookup_failed_description": "REOPEN_LOOKUP_ERR_DESC_ES",
                "not_found_title": "REOPEN_NF_ES",
                "not_found_description": "REOPEN_NF_DESC_{number}_ES",
                "not_found_uuid_title": "REOPEN_NF_UUID_ES",
                "not_found_uuid_description": "REOPEN_NF_UUID_DESC_{id}_ES",
                "wrong_guild_title": "REOPEN_WRONG_GUILD_ES",
                "wrong_guild_description": "REOPEN_WRONG_GUILD_DESC_ES",
                "not_ticket_title": "REOPEN_NO_TICKET_ES",
                "not_ticket_description": "REOPEN_NO_TICKET_DESC_ES",
                "failed_title": "REOPEN_FAIL_ES",
                "failed_description": "REOPEN_FAIL_DESC_ES",
                "not_closed_description": "REOPEN_NOT_CLOSED_{status}_ES",
                "success_title": "REOPEN_OK_ES",
                "success_description": "REOPEN_OK_DESC_ES",
            },
            "transfer": {
                "server_only_title": "XFER_GUILD_ONLY_ES",
                "server_only_description": "XFER_GUILD_ONLY_DESC_ES",
                "not_ticket_title": "XFER_NO_TICKET_ES",
                "not_ticket_description": "XFER_NO_TICKET_DESC_ES",
                "lookup_failed_title": "XFER_LOOKUP_ERR_ES",
                "lookup_failed_description": "XFER_LOOKUP_ERR_DESC_ES",
                "failed_title": "XFER_FAIL_ES",
                "failed_description": "XFER_FAIL_DESC_ES",
                "success_title": "XFER_OK_ES",
                "success_description": "XFER_OK_DESC_{member}_ES",
            },
            "note": {
                "help_title": "NOTE_HELP_ES",
                "help_description": "NOTE_HELP_DESC_ES",
                "add_lookup_failed_title": "NOTE_LOOKUP_ERR_ES",
                "add_lookup_failed_description": "NOTE_LOOKUP_ERR_DESC_ES",
                "add_not_ticket_title": "NOTE_NO_TICKET_ES",
                "add_not_ticket_description": "NOTE_NO_TICKET_DESC_ES",
                "add_failed_title": "NOTE_ADD_ERR_ES",
                "add_failed_description": "NOTE_ADD_ERR_DESC_ES",
                "add_success_title": "NOTE_ADD_OK_ES",
                "add_success_description": "NOTE_ADD_OK_DESC_{id}_ES",
                "list_no_notes_title": "NOTE_LIST_EMPTY_ES",
                "list_no_notes_description": "NOTE_LIST_EMPTY_DESC_ES",
                "list_title": "NOTE_LIST_TITLE_ES",
                "list_dm_failed_title": "NOTE_DM_ERR_ES",
                "list_dm_failed_description": "NOTE_DM_ERR_DESC_ES",
                "list_sent_title": "NOTE_SENT_ES",
                "list_sent_description": "NOTE_SENT_DESC_ES",
                "delete_lookup_failed_title": "NOTE_DEL_LOOKUP_ES",
                "delete_lookup_failed_description": "NOTE_DEL_LOOKUP_DESC_ES",
                "delete_not_ticket_title": "NOTE_DEL_NO_TICKET_ES",
                "delete_not_ticket_description": "NOTE_DEL_NO_TICKET_DESC_ES",
                "delete_failed_title": "NOTE_DEL_ERR_ES",
                "delete_failed_description": "NOTE_DEL_ERR_DESC_ES",
                "delete_success_title": "NOTE_DEL_OK_ES",
                "delete_success_description": "NOTE_DEL_OK_DESC_{id}_ES",
            },
        },
    }

    en_data = {
        "common": {
            "footer": "NB • {timestamp}",
            "error": {"title": "ERR_EN"},
            "success": {"title": "OK_EN"},
            "info": {"title": "INFO_EN"},
        },
        "tickets": {
            "config_missing": {
                "title": "TICKET_NO_CONFIG_EN",
                "description": "TICKET_NO_CONFIG_DESC_EN",
            },
            "panel": {
                "server_only_title": "PANEL_GUILD_ONLY_EN",
                "server_only_description": "PANEL_GUILD_ONLY_DESC_EN",
                "no_categories_title": "PANEL_NO_CATS_EN",
                "no_categories_description": "PANEL_NO_CATS_DESC_EN",
                "select_placeholder": "SELECT_CAT_EN",
                "success_title": "PANEL_OK_EN",
                "success_description": "PANEL_OK_DESC_EN",
                "deploy_error_title": "PANEL_ERR_EN",
                "deploy_error_description": "PANEL_ERR_DESC_EN",
                "permission_denied_title": "PANEL_PERM_EN",
                "permission_denied_description": "PANEL_PERM_DESC_EN",
                "open_button": "OPEN_BTN_EN",
            },
            "create": {
                "server_only_title": "CREATE_GUILD_ONLY_EN",
                "server_only_description": "CREATE_GUILD_ONLY_DESC_EN",
                "duplicate_title": "CREATE_DUP_EN",
                "duplicate_description": "CREATE_DUP_DESC_{name}_EN",
                "check_failed_title": "CREATE_CHECK_ERR_EN",
                "check_failed_description": "CREATE_CHECK_ERR_DESC_EN",
                "failed_title": "CREATE_ERR_EN",
                "failed_description": "CREATE_ERR_DESC_EN",
                "success_title": "CREATE_OK_EN",
                "success_description": "CREATE_OK_DESC_{name}_{id}_EN",
            },
            "list": {
                "id_label": "LIST_ID_EN",
                "position_label": "LIST_POS_EN",
                "failed_title": "LIST_ERR_EN",
                "failed_description": "LIST_ERR_DESC_EN",
                "empty_title": "LIST_EMPTY_EN",
                "empty_description": "LIST_EMPTY_DESC_EN",
                "title": "LIST_TITLE_EN",
            },
            "delete": {
                "failed_title": "DEL_ERR_EN",
                "failed_description": "DEL_ERR_DESC_EN",
                "not_found_title": "DEL_NOT_FOUND_EN",
                "not_found_description": "DEL_NOT_FOUND_DESC_{id}_EN",
                "wrong_guild_title": "DEL_WRONG_GUILD_EN",
                "wrong_guild_description": "DEL_WRONG_GUILD_DESC_EN",
                "in_use_title": "DEL_IN_USE_EN",
                "in_use_description": "DEL_IN_USE_DESC_{name}_{count}_EN",
                "success_title": "DEL_OK_EN",
                "success_description": "DEL_OK_DESC_{name}_EN",
            },
            "open": {
                "server_only_title": "OPEN_GUILD_ONLY_EN",
                "server_only_description": "OPEN_GUILD_ONLY_DESC_EN",
                "no_categories_title": "OPEN_NO_CATS_EN",
                "no_categories_description": "OPEN_NO_CATS_DESC_EN",
                "select_category": "OPEN_SELECT_CAT_EN",
                "config_error_title": "OPEN_CFG_ERR_EN",
                "config_error_description": "OPEN_CFG_ERR_DESC_EN",
                "invalid_category_title": "OPEN_INV_CAT_EN",
                "invalid_category_description": "OPEN_INV_CAT_DESC_EN",
                "permission_denied_title": "OPEN_PERM_EN",
                "permission_denied_description": "OPEN_PERM_DESC_EN",
                "channel_failed_title": "OPEN_CH_FAIL_EN",
                "channel_failed_description": "OPEN_CH_FAIL_DESC_EN",
                "creation_failed_title": "OPEN_CR_FAIL_EN",
                "creation_failed_description": "OPEN_CR_FAIL_DESC_EN",
                "success_title": "OPEN_OK_EN",
                "success_description": "OPEN_OK_DESC_{channel}_EN",
                "welcome_title": "OPEN_WELCOME_{number}_EN",
                "welcome_description": "OPEN_WELCOME_DESC_EN",
                "welcome_claimed_title": "OPEN_CLAIMED_{number}_EN",
                "welcome_claimed_description": "OPEN_CLAIMED_DESC_EN",
                "welcome_claimed_by": "OPEN_CLAIMED_BY_EN",
                "author_field": "OPEN_AUTHOR_EN",
                "footer": "OPEN_FOOTER_EN",
            },
            "actions": {
                "claim_button": "CLAIM_BTN_EN",
                "close_button": "CLOSE_BTN_EN",
                "claim_mods_only_title": "CLAIM_MOD_EN",
                "claim_mods_only_description": "CLAIM_MOD_DESC_EN",
                "claim_failed_title": "CLAIM_FAIL_EN",
                "claim_failed_description": "CLAIM_FAIL_DESC_EN",
                "claim_not_ticket_description": "CLAIM_NO_TICKET_EN",
                "claim_already_closed_description": "CLAIM_CLOSED_EN",
                "claim_already_claimed_title": "CLAIM_ALREADY_EN",
                "claim_already_claimed_description": "CLAIM_ALREADY_DESC_{user}_EN",
                "claim_generic_error_description": "CLAIM_ERR_DESC_EN",
                "close_failed_title": "CLOSE_FAIL_EN",
                "close_not_ticket_description": "CLOSE_NO_TICKET_EN",
                "close_already_closed_description": "CLOSE_CLOSED_EN",
                "close_author_or_mod_title": "CLOSE_AUTH_MOD_EN",
                "close_author_or_mod_description": "CLOSE_AUTH_MOD_DESC_EN",
                "close_db_error_title": "CLOSE_DB_ERR_EN",
                "close_db_error_description": "CLOSE_DB_ERR_DESC_EN",
                "close_success_title": "CLOSE_OK_EN",
                "close_success_description": "CLOSE_OK_DESC_EN",
                "closed_channel_title": "CLOSED_CH_TITLE_EN",
                "closed_channel_message": "CLOSED_CH_MSG_EN",
                "closed_channel_transcript": "CLOSED_CH_TRANS_EN",
            },
            "subticket": {
                "help_title": "SUB_HELP_EN",
                "help_description": "SUB_HELP_DESC_EN",
                "server_only_title": "SUB_GUILD_ONLY_EN",
                "server_only_description": "SUB_GUILD_ONLY_DESC_EN",
                "owner_not_found_title": "SUB_OWNER_NF_EN",
                "owner_not_found_description": "SUB_OWNER_NF_DESC_EN",
                "owner_not_found_resolve_title": "SUB_OWNER_RESOLVE_EN",
                "owner_not_found_resolve_description": "SUB_OWNER_RESOLVE_DESC_EN",
                "not_ticket_title": "SUB_NO_TICKET_EN",
                "not_ticket_description": "SUB_NO_TICKET_DESC_EN",
                "lookup_failed_title": "SUB_LOOKUP_ERR_EN",
                "lookup_failed_description": "SUB_LOOKUP_ERR_DESC_EN",
                "invalid_category_title": "SUB_INV_CAT_EN",
                "invalid_category_description": "SUB_INV_CAT_DESC_EN",
                "number_failed_title": "SUB_NUM_ERR_EN",
                "number_failed_description": "SUB_NUM_ERR_DESC_EN",
                "channel_failed_title": "SUB_CH_ERR_EN",
                "channel_failed_description": "SUB_CH_ERR_DESC_EN",
                "creation_failed_title": "SUB_CR_ERR_EN",
                "creation_failed_description": "SUB_CR_ERR_DESC_EN",
                "success_title": "SUB_OK_EN",
                "success_description": "SUB_OK_DESC_{channel}_EN",
            },
            "reopen": {
                "server_only_title": "REOPEN_GUILD_ONLY_EN",
                "server_only_description": "REOPEN_GUILD_ONLY_DESC_EN",
                "invalid_ref_title": "REOPEN_INV_REF_EN",
                "invalid_ref_description": "REOPEN_INV_REF_DESC_{ref}_EN",
                "lookup_failed_title": "REOPEN_LOOKUP_ERR_EN",
                "lookup_failed_description": "REOPEN_LOOKUP_ERR_DESC_EN",
                "not_found_title": "REOPEN_NF_EN",
                "not_found_description": "REOPEN_NF_DESC_{number}_EN",
                "not_found_uuid_title": "REOPEN_NF_UUID_EN",
                "not_found_uuid_description": "REOPEN_NF_UUID_DESC_{id}_EN",
                "wrong_guild_title": "REOPEN_WRONG_GUILD_EN",
                "wrong_guild_description": "REOPEN_WRONG_GUILD_DESC_EN",
                "not_ticket_title": "REOPEN_NO_TICKET_EN",
                "not_ticket_description": "REOPEN_NO_TICKET_DESC_EN",
                "failed_title": "REOPEN_FAIL_EN",
                "failed_description": "REOPEN_FAIL_DESC_EN",
                "not_closed_description": "REOPEN_NOT_CLOSED_{status}_EN",
                "success_title": "REOPEN_OK_EN",
                "success_description": "REOPEN_OK_DESC_EN",
            },
            "transfer": {
                "server_only_title": "XFER_GUILD_ONLY_EN",
                "server_only_description": "XFER_GUILD_ONLY_DESC_EN",
                "not_ticket_title": "XFER_NO_TICKET_EN",
                "not_ticket_description": "XFER_NO_TICKET_DESC_EN",
                "lookup_failed_title": "XFER_LOOKUP_ERR_EN",
                "lookup_failed_description": "XFER_LOOKUP_ERR_DESC_EN",
                "failed_title": "XFER_FAIL_EN",
                "failed_description": "XFER_FAIL_DESC_EN",
                "success_title": "XFER_OK_EN",
                "success_description": "XFER_OK_DESC_{member}_EN",
            },
            "note": {
                "help_title": "NOTE_HELP_EN",
                "help_description": "NOTE_HELP_DESC_EN",
                "add_lookup_failed_title": "NOTE_LOOKUP_ERR_EN",
                "add_lookup_failed_description": "NOTE_LOOKUP_ERR_DESC_EN",
                "add_not_ticket_title": "NOTE_NO_TICKET_EN",
                "add_not_ticket_description": "NOTE_NO_TICKET_DESC_EN",
                "add_failed_title": "NOTE_ADD_ERR_EN",
                "add_failed_description": "NOTE_ADD_ERR_DESC_EN",
                "add_success_title": "NOTE_ADD_OK_EN",
                "add_success_description": "NOTE_ADD_OK_DESC_{id}_EN",
                "list_no_notes_title": "NOTE_LIST_EMPTY_EN",
                "list_no_notes_description": "NOTE_LIST_EMPTY_DESC_EN",
                "list_title": "NOTE_LIST_TITLE_EN",
                "list_dm_failed_title": "NOTE_DM_ERR_EN",
                "list_dm_failed_description": "NOTE_DM_ERR_DESC_EN",
                "list_sent_title": "NOTE_SENT_EN",
                "list_sent_description": "NOTE_SENT_DESC_EN",
                "delete_lookup_failed_title": "NOTE_DEL_LOOKUP_EN",
                "delete_lookup_failed_description": "NOTE_DEL_LOOKUP_DESC_EN",
                "delete_not_ticket_title": "NOTE_DEL_NO_TICKET_EN",
                "delete_not_ticket_description": "NOTE_DEL_NO_TICKET_DESC_EN",
                "delete_failed_title": "NOTE_DEL_ERR_EN",
                "delete_failed_description": "NOTE_DEL_ERR_DESC_EN",
                "delete_success_title": "NOTE_DEL_OK_EN",
                "delete_success_description": "NOTE_DEL_OK_DESC_{id}_EN",
            },
        },
    }

    locale_dir = tmp_path / "locales"
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / "es.json").write_text(json.dumps(es_data), encoding="utf-8")
    (locale_dir / "en.json").write_text(json.dumps(en_data), encoding="utf-8")

    load_locales(locale_dir)
    set_guild_language(_ES_GUILD_ID, "es")
    set_guild_language(_EN_GUILD_ID, "en")

    yield

    # Restore original state so other test modules are not affected.
    i18n_mod._locales.clear()
    i18n_mod._locales.update(orig_locales)
    i18n_mod._guild_languages.clear()
    i18n_mod._guild_languages.update(orig_guild_langs)


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
def mock_ticket_channel() -> MagicMock:
    """Return a mock TextChannel for ticket operations."""
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = 444444444
    ch.name = "ticket-0001"
    ch.mention = "<#444444444>"
    ch.send = AsyncMock()
    ch.delete = AsyncMock()
    ch.edit = AsyncMock()
    return ch


@pytest.fixture
def ticket_guild_es(mock_ticket_channel: MagicMock) -> MagicMock:
    """Return a mock guild with ES language configured."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = int(_ES_GUILD_ID)
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.create_text_channel = AsyncMock(return_value=mock_ticket_channel)
    guild.get_channel = MagicMock(return_value=mock_ticket_channel)
    guild.get_role = MagicMock(return_value=None)
    return guild


@pytest.fixture
def ticket_guild_en(mock_ticket_channel: MagicMock) -> MagicMock:
    """Return a mock guild with EN language configured."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = int(_EN_GUILD_ID)
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.create_text_channel = AsyncMock(return_value=mock_ticket_channel)
    guild.get_channel = MagicMock(return_value=mock_ticket_channel)
    guild.get_role = MagicMock(return_value=None)
    return guild


@pytest.fixture
def cog_es(ticket_bot: MagicMock) -> TicketsCog:
    """Return a TicketsCog wired to the ES bot."""
    return TicketsCog(bot=ticket_bot)


@pytest.fixture
def cog_en(ticket_bot: MagicMock) -> TicketsCog:
    """Return a TicketsCog wired to the EN bot."""
    return TicketsCog(bot=ticket_bot)


def _make_ctx(guild: MagicMock) -> MagicMock:
    """Build a mock commands.Context for ticket command tests."""
    ctx = MagicMock()
    ctx.guild = guild
    ctx.guild.id = guild.id
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 444444444
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 111111111
    ctx.author.mention = "<@111111111>"
    ctx.author.display_name = "TestUser"
    ctx.interaction = None
    return ctx


# ---------------------------------------------------------------------------
# 2.5 — RED: Test ticket commands return localized strings for es/en
# ---------------------------------------------------------------------------


class TestTicketConfigMissingI18n:
    """Test tickets.config_missing uses t() for es and en guilds."""

    async def test_config_missing_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """Subticket create with no ticket_category_id → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        guild.default_role = MagicMock()
        guild.me = MagicMock()
        guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.CategoryChannel))

        ctx = _make_ctx(guild)

        config = MagicMock()
        config.ticket_category_id = None
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        await cog_es.subticket_create.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "TICKET_NO_CONFIG_ES" in embed.title

    async def test_config_missing_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """Subticket create with no ticket_category_id → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        guild.default_role = MagicMock()
        guild.me = MagicMock()
        guild.get_channel = MagicMock(return_value=MagicMock(spec=discord.CategoryChannel))

        ctx = _make_ctx(guild)

        config = MagicMock()
        config.ticket_category_id = None
        config.mod_role_id = None
        ticket_bot.guild_service.get_config = AsyncMock(return_value=config)

        await cog_en.subticket_create.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "TICKET_NO_CONFIG_EN" in embed.title


class TestTicketOpenNoCategoriesI18n:
    """Test TicketPanelView.open_ticket_button uses t() for no-categories error."""

    async def test_no_categories_es(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """No categories → localized ES error embed."""

        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.client = ticket_bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        view = TicketPanelView()
        await view.open_ticket_button.callback(interaction)

        call_kwargs = interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        # Should use localized string, not hardcoded English
        assert "PANEL_NO_CATS_ES" in embed.title

    async def test_no_categories_en(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """No categories → localized EN error embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.client = ticket_bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        view = TicketPanelView()
        await view.open_ticket_button.callback(interaction)

        call_kwargs = interaction.response.send_message.call_args
        embed = call_kwargs.kwargs.get("embed")
        assert embed is not None
        assert "PANEL_NO_CATS_EN" in embed.title


class TestTicketClaimI18n:
    """Test claim button error messages use t()."""

    async def test_claim_not_ticket_es(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """Claim on non-ticket channel → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.user.guild_permissions.administrator = True
        interaction.client = ticket_bot
        interaction.channel_id = 444444444
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.claim_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CLAIM_FAIL_ES" in embed.title
        assert "CLAIM_NO_TICKET_ES" in embed.description

    async def test_claim_not_ticket_en(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """Claim on non-ticket channel → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.guild_id = int(_EN_GUILD_ID)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.user.guild_permissions.administrator = True
        interaction.client = ticket_bot
        interaction.channel_id = 444444444
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.claim_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CLAIM_FAIL_EN" in embed.title
        assert "CLAIM_NO_TICKET_EN" in embed.description


class TestTicketCloseI18n:
    """Test close button error messages use t()."""

    async def test_close_not_ticket_es(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """Close on non-ticket channel → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.client = ticket_bot
        interaction.channel_id = 444444444
        interaction.channel = MagicMock()
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        view = TicketActionsView()
        await view.close_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CLOSE_FAIL_ES" in embed.title
        assert "CLOSE_NO_TICKET_ES" in embed.description

    async def test_close_already_closed_en(
        self,
        ticket_bot: MagicMock,
    ) -> None:
        """Close already-closed ticket → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.client = ticket_bot
        interaction.channel_id = 444444444
        interaction.channel = MagicMock()
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        row = _ticket_row(status="closed", guild_id=_EN_GUILD_ID)
        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=row)

        view = TicketActionsView()
        await view.close_button.callback(interaction)

        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CLOSE_FAIL_EN" in embed.title
        assert "CLOSE_CLOSED_EN" in embed.description


class TestSubticketHelpI18n:
    """Test /subticket help uses t()."""

    async def test_subticket_help_es(
        self,
        cog_es: TicketsCog,
    ) -> None:
        """/subticket help → localized ES embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        await cog_es.subticket.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "SUB_HELP_ES" in embed.title

    async def test_subticket_help_en(
        self,
        cog_en: TicketsCog,
    ) -> None:
        """/subticket help → localized EN embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        await cog_en.subticket.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "SUB_HELP_EN" in embed.title


class TestReopenI18n:
    """Test /reopen error messages use t()."""

    async def test_reopen_not_ticket_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/reopen in non-ticket channel → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        await cog_es.reopen.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "REOPEN_NO_TICKET_ES" in embed.title

    async def test_reopen_not_ticket_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/reopen in non-ticket channel → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        await cog_en.reopen.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "REOPEN_NO_TICKET_EN" in embed.title


class TestNoteHelpI18n:
    """Test /note help uses t()."""

    async def test_note_help_es(
        self,
        cog_es: TicketsCog,
    ) -> None:
        """/note help → localized ES embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        await cog_es.note.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "NOTE_HELP_ES" in embed.title

    async def test_note_help_en(
        self,
        cog_en: TicketsCog,
    ) -> None:
        """/note help → localized EN embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        await cog_en.note.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "NOTE_HELP_EN" in embed.title


class TestListCategoriesI18n:
    """Test /list_categories uses t()."""

    async def test_list_categories_empty_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/list_categories with no categories → localized ES embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        await cog_es.list_categories.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "LIST_EMPTY_ES" in embed.title

    async def test_list_categories_empty_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/list_categories with no categories → localized EN embed."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[])

        await cog_en.list_categories.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "LIST_EMPTY_EN" in embed.title


class TestCreateCategoryI18n:
    """Test /create_category uses t()."""

    async def test_create_category_duplicate_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/create_category with duplicate name → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[_category_row()])

        await cog_es.create_category.callback(cog_es, ctx, name="Support")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CREATE_DUP_ES" in embed.title

    async def test_create_category_duplicate_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/create_category with duplicate name → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_categories = AsyncMock(return_value=[_category_row(guild_id=_EN_GUILD_ID)])

        await cog_en.create_category.callback(cog_en, ctx, name="Support")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "CREATE_DUP_EN" in embed.title


class TestDeleteCategoryI18n:
    """Test /delete_category uses t()."""

    async def test_delete_category_not_found_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/delete_category with invalid ID → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_category = AsyncMock(return_value=None)

        await cog_es.delete_category.callback(cog_es, ctx, category_id="nonexistent")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DEL_NOT_FOUND_ES" in embed.title

    async def test_delete_category_in_use_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/delete_category with open tickets → localized EN error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        row = _category_row(guild_id=_EN_GUILD_ID)
        ticket_bot.db.get_ticket_category = AsyncMock(return_value=row)
        ticket_bot.db.count_open_tickets_by_category = AsyncMock(return_value=3)

        await cog_en.delete_category.callback(cog_en, ctx, category_id="cat-uuid-001")

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "DEL_IN_USE_EN" in embed.title


class TestTransferI18n:
    """Test /transfer uses t()."""

    async def test_transfer_not_ticket_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/transfer in non-ticket channel → localized ES error."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=None)

        target = MagicMock(spec=discord.Member)
        target.id = 222222222

        await cog_es.transfer.callback(cog_es, ctx, member=target)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        assert "XFER_NO_TICKET_ES" in embed.title


class TestTicketEmbedI18n:
    """Test _build_ticket_embed uses t() for titles and descriptions."""

    def test_open_ticket_embed_es(self) -> None:
        """Open ticket embed uses localized ES strings."""
        guild_id = _ES_GUILD_ID
        ticket = Ticket.from_db_row(_ticket_row(status="open", guild_id=guild_id))
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_WELCOME_" in embed.title
        assert embed.description is not None and "OPEN_WELCOME_DESC_ES" in embed.description

    def test_open_ticket_embed_en(self) -> None:
        """Open ticket embed uses localized EN strings."""
        guild_id = _EN_GUILD_ID
        ticket = Ticket.from_db_row(_ticket_row(status="open", guild_id=guild_id))
        embed = _build_ticket_embed(ticket, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_WELCOME_" in embed.title
        assert embed.description is not None and "OPEN_WELCOME_DESC_EN" in embed.description

    def test_claimed_ticket_embed_es(self) -> None:
        """Claimed ticket embed uses localized ES strings."""
        guild_id = _ES_GUILD_ID
        ticket = Ticket.from_db_row(_ticket_row(status="claimed", guild_id=guild_id))
        claimed_by = MagicMock()
        claimed_by.mention = "<@999999>"
        embed = _build_ticket_embed(ticket, claimed_by=claimed_by, guild_id=guild_id)
        assert embed.title is not None
        assert "OPEN_CLAIMED_" in embed.title
        assert embed.description is not None and "OPEN_CLAIMED_DESC_ES" in embed.description


# ---------------------------------------------------------------------------
# CRITICAL 1 fix: Button labels are localized when guild_id is provided
# ---------------------------------------------------------------------------


class TestButtonLabelI18n:
    """Test persistent view button labels use t() when guild_id is provided."""

    def test_panel_view_open_button_es(self) -> None:
        """TicketPanelView with ES guild_id → button label localized to ES."""
        view = TicketPanelView(guild_id=_ES_GUILD_ID)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "OPEN_BTN_ES"

    def test_panel_view_open_button_en(self) -> None:
        """TicketPanelView with EN guild_id → button label localized to EN."""
        view = TicketPanelView(guild_id=_EN_GUILD_ID)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "OPEN_BTN_EN"

    def test_panel_view_no_guild_default(self) -> None:
        """TicketPanelView without guild_id → default label preserved."""
        view = TicketPanelView()
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 1
        assert buttons[0].label == "Open Ticket"

    def test_actions_view_buttons_es(self) -> None:
        """TicketActionsView with ES guild_id → claim/close labels localized."""
        view = TicketActionsView(guild_id=_ES_GUILD_ID)
        buttons = {c.custom_id: c for c in view.children if isinstance(c, discord.ui.Button)}
        assert buttons["ticket:claim"].label == "CLAIM_BTN_ES"
        assert buttons["ticket:close"].label == "CLOSE_BTN_ES"

    def test_actions_view_buttons_en(self) -> None:
        """TicketActionsView with EN guild_id → claim/close labels localized."""
        view = TicketActionsView(guild_id=_EN_GUILD_ID)
        buttons = {c.custom_id: c for c in view.children if isinstance(c, discord.ui.Button)}
        assert buttons["ticket:claim"].label == "CLAIM_BTN_EN"
        assert buttons["ticket:close"].label == "CLOSE_BTN_EN"

    def test_actions_view_no_guild_default(self) -> None:
        """TicketActionsView without guild_id → default labels preserved."""
        view = TicketActionsView()
        buttons = {c.custom_id: c for c in view.children if isinstance(c, discord.ui.Button)}
        assert buttons["ticket:claim"].label == "Claim"
        assert buttons["ticket:close"].label == "Close"


# ---------------------------------------------------------------------------
# CRITICAL 3: Dynamic label resolution at interaction time
# ---------------------------------------------------------------------------


class TestDynamicLabelResolution:
    """Test button labels resolve via t() at INTERACTION time, not just construction."""

    async def test_panel_open_label_updates_at_interaction_es(self) -> None:
        """Panel open button label resolves to ES at callback time."""
        view = TicketPanelView()  # No guild_id → default "Open Ticket"

        # Simulate interaction from ES guild.
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.guild_id = int(_ES_GUILD_ID)
        interaction.client = MagicMock()
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        open_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:open"
        )
        await open_button.callback(interaction)

        # After callback, label should be updated to ES.
        assert open_button.label == "OPEN_BTN_ES"

    async def test_panel_open_label_updates_at_interaction_en(self) -> None:
        """Panel open button label resolves to EN at callback time."""
        view = TicketPanelView()  # No guild_id → default "Open Ticket"

        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.guild_id = int(_EN_GUILD_ID)
        interaction.client = MagicMock()
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_categories = AsyncMock(return_value=[])
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        open_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:open"
        )
        await open_button.callback(interaction)

        assert open_button.label == "OPEN_BTN_EN"

    async def test_actions_claim_label_updates_at_interaction_es(self) -> None:
        """Claim button label resolves to ES at callback time."""
        view = TicketActionsView()  # No guild_id → default English

        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.guild_id = int(_ES_GUILD_ID)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.user.guild_permissions.administrator = True
        interaction.client = MagicMock()
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_by_channel = AsyncMock(return_value=None)
        interaction.channel_id = 444444444
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.edit_message = AsyncMock()

        claim_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:claim"
        )
        await claim_button.callback(interaction)

        # After callback, label should be updated to ES.
        assert claim_button.label == "CLAIM_BTN_ES"

    async def test_actions_close_label_updates_at_interaction_en(self) -> None:
        """Close button label resolves to EN at callback time."""
        view = TicketActionsView()  # No guild_id → default English

        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.guild_id = int(_EN_GUILD_ID)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 111111111
        interaction.client = MagicMock()
        interaction.client.db = AsyncMock()
        interaction.client.db.get_ticket_by_channel = AsyncMock(return_value=None)
        interaction.channel_id = 444444444
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        close_button = next(
            c for c in view.children
            if isinstance(c, discord.ui.Button) and c.custom_id == "ticket:close"
        )
        await close_button.callback(interaction)

        assert close_button.label == "CLOSE_BTN_EN"


# ---------------------------------------------------------------------------
# CRITICAL 2 fix: reopen error uses t() instead of service's raw Spanish text
# ---------------------------------------------------------------------------


class TestReopenNotClosedI18n:
    """Test /reopen ValueError surfaces localized error, not service's raw text."""

    async def test_reopen_not_closed_es(
        self,
        cog_es: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/reopen on open ticket → localized ES error (not Spanish raw text)."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_ES_GUILD_ID)
        ctx = _make_ctx(guild)

        row = _ticket_row(status="open", guild_id=_ES_GUILD_ID)
        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=row)

        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            side_effect=ValueError("Solo se pueden reabrir tickets cerrados. Estado actual: open")
        )

        await cog_es.reopen.callback(cog_es, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        # Must use t() localized string, NOT the raw Spanish service text
        assert "REOPEN_NOT_CLOSED_open_ES" in embed.description
        assert "Solo se pueden" not in embed.description

    async def test_reopen_not_closed_en(
        self,
        cog_en: TicketsCog,
        ticket_bot: MagicMock,
    ) -> None:
        """/reopen on open ticket → localized EN error (English guild gets English)."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = int(_EN_GUILD_ID)
        ctx = _make_ctx(guild)

        row = _ticket_row(status="open", guild_id=_EN_GUILD_ID)
        ticket_bot.db.get_ticket_by_channel = AsyncMock(return_value=row)

        ticket_bot.ticket_service.reopen_ticket = AsyncMock(
            side_effect=ValueError("Solo se pueden reabrir tickets cerrados. Estado actual: open")
        )

        await cog_en.reopen.callback(cog_en, ctx)

        embed = ctx.send.call_args.kwargs.get("embed")
        assert embed is not None
        # Must use t() localized EN string
        assert "REOPEN_NOT_CLOSED_open_EN" in embed.description
        assert "Solo se pueden" not in embed.description


# ---------------------------------------------------------------------------
# CRITICAL 3 fix: es.json translations — no English text for fixed keys
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
