"""RED: S3.4B views 3 seams behind facade — 4 IDs, 2 timeouts, revalidation, t(guild_id), field_definitions.

Strict TDD: this file MUST be written before implementation. Tests query the new
seams (ticket_panel / ticket_actions / ticket_category_select) and the facade
(bot.views.tickets) for:
- 4 static custom_ids: ticket:open | claim | close | edit-category
- persistent timeout=None (TicketPanelView, TicketActionsView) + ephemeral 300s
- is_mod_check revalidation + closed-state re-fetch before mutation
- t(guild_id) dynamic label + deploy_ticket_panel(None) localized defaults
- field_definitions passed through to TicketIntakeModal
- facade re-exports + bot.add_view() registration still from facade
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


def test_facade_re_exports_all_view_symbols() -> None:
    """bot.views.tickets MUST re-export all 4 view symbols after split."""
    import bot.views.tickets as facade

    for name in (
        "deploy_ticket_panel",
        "TicketIntakeModal",
        "TicketPanelView",
        "TicketActionsView",
        "_CategorySelectView",
        "_CategorySelect",
        "_EditCategoryView",
        "_EditCategorySelect",
    ):
        assert hasattr(facade, name), f"facade missing {name}"


def test_panel_seam_contains_intake_and_panel() -> None:
    """ticket_panel seam MUST contain TicketIntakeModal + TicketPanelView."""
    import bot.views.ticket_panel as mod

    assert hasattr(mod, "TicketIntakeModal")
    assert hasattr(mod, "TicketPanelView")
    assert hasattr(mod, "deploy_ticket_panel")
    assert hasattr(mod, "_create_ticket_after_modal")


def test_persistent_seam_contains_actions_view() -> None:
    """ticket_actions seam MUST contain TicketActionsView."""
    import bot.views.ticket_actions as mod

    assert hasattr(mod, "TicketActionsView")


def test_ephemeral_seam_contains_category_selects() -> None:
    """ticket_category_select seam MUST contain all 4 ephemeral symbols."""
    import bot.views.ticket_category_select as mod

    for name in ("_CategorySelectView", "_CategorySelect", "_EditCategoryView", "_EditCategorySelect"):
        assert hasattr(mod, name), f"missing {name}"


def test_four_static_custom_ids_survive_extraction() -> None:
    """All 4 persistent custom_ids MUST survive extraction with same values."""
    from bot.views.tickets import TicketActionsView, TicketPanelView

    panel = TicketPanelView(guild_id="123")
    actions = TicketActionsView(guild_id="123")

    panel_ids = {c.custom_id for c in panel.children if hasattr(c, "custom_id")}
    actions_ids = {c.custom_id for c in actions.children if hasattr(c, "custom_id")}

    assert "ticket:open" in panel_ids, f"missing ticket:open in panel {panel_ids}"
    assert "ticket:claim" in actions_ids
    assert "ticket:close" in actions_ids
    assert "ticket:edit-category" in actions_ids
    assert panel_ids | actions_ids == {"ticket:open", "ticket:claim", "ticket:close", "ticket:edit-category"}


def test_persistent_views_timeout_none() -> None:
    """TicketPanelView and TicketActionsView MUST have timeout=None (persistent)."""
    from bot.views.tickets import TicketActionsView, TicketPanelView

    assert TicketPanelView(guild_id="123").timeout is None
    assert TicketActionsView(guild_id="123").timeout is None


def test_ephemeral_views_timeout_300() -> None:
    """Ephemeral category views MUST have timeout=300."""
    from bot.models.ticket_category import TicketCategory
    from bot.views.tickets import _CategorySelectView, _EditCategoryView

    guild = MagicMock()
    guild.id = 123456789
    cats = [TicketCategory(id="c1", guild_id="123", name="Support", description="", position=0)]
    opts = [discord.SelectOption(label="Support", value="c1")]

    v1 = _CategorySelectView(opts, guild, cats)
    assert v1.timeout == 300

    ticket_row = {
        "id": "t1",
        "ticketNumber": 1,
        "guildId": "123",
        "authorId": "1",
        "channelId": "1",
        "categoryId": "c1",
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-01T00:00:00+00:00",
    }
    v2 = _EditCategoryView(opts, guild, cats, ticket_row)
    assert v2.timeout == 300


def test_bot_setup_hook_registers_persistent_views_via_facade() -> None:
    """bot.bot.setup_hook MUST add_view() persistent views imported from facade."""
    src = inspect.getsource(import_module("bot.bot"))
    assert "from bot.views.tickets import TicketActionsView" in src or "from bot.views.tickets import" in src
    assert "add_view(TicketPanelView" in src
    assert "add_view(TicketActionsView" in src


def test_panel_button_label_uses_t_guild_id_dynamic() -> None:
    """TicketPanelView button label MUST be resolved via t(guild_id)."""
    from bot.views.tickets import TicketPanelView

    with patch("bot.views.tickets.t", return_value="Abrir Ticket") as mock_t:
        view = TicketPanelView(guild_id="999")
        btn = next(c for c in view.children if getattr(c, "custom_id", None) == "ticket:open")
        assert btn.label == "Abrir Ticket"
        mock_t.assert_any_call("999", "tickets.panel.open_button")


def test_deploy_none_defaults_resolve_via_t() -> None:
    """deploy_ticket_panel(None, None) MUST resolve via t(guild_id)."""
    import asyncio

    from bot.core.i18n import load_locales, set_guild_language
    from bot.views.tickets import deploy_ticket_panel

    load_locales()
    set_guild_language("555", "es")

    channel = MagicMock()
    channel.id = 999
    channel.send = AsyncMock()
    msg = MagicMock()
    msg.id = 42
    msg.channel = channel
    channel.send.return_value = msg
    bot = MagicMock()
    bot.guild_service = MagicMock()
    bot.guild_service.update_guild_panel = AsyncMock()

    async def _run() -> None:
        await deploy_ticket_panel(channel, "555", bot=bot)

    asyncio.run(_run())
    embed = channel.send.call_args.kwargs["embed"]
    assert embed.title == "Tickets de Soporte"


def test_category_select_passes_field_definitions_to_modal() -> None:
    """_CategorySelect MUST pass field_definitions to TicketIntakeModal."""
    from bot.models.ticket_category import TicketCategory
    from bot.views.ticket_category_select import _CategorySelect

    guild = MagicMock()
    guild.id = 123456789
    cat = TicketCategory(
        id="cat-uuid-1",
        guild_id="123",
        name="Reportes",
        description="",
        position=0,
        field_definitions=[
            {"key": "player_nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}
        ],
    )
    opts = [discord.SelectOption(label="Reportes", value="cat-uuid-1")]
    select = _CategorySelect(opts, guild, [cat])
    select._values = ["cat-uuid-1"]

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.send_modal = AsyncMock()
    interaction.guild = guild
    interaction.client = MagicMock()

    import asyncio

    asyncio.run(select.callback(interaction))
    sent_modal = interaction.response.send_modal.call_args.args[0]
    # modal must carry field_definitions
    assert hasattr(sent_modal, "_field_definitions")
    assert sent_modal._field_definitions == cat.field_definitions


@pytest.mark.asyncio
async def test_edit_category_select_revalidates_is_mod_and_closed_state() -> None:
    """_EditCategorySelect.callback MUST re-check is_mod_check and re-fetch closed state before mutation."""
    from bot.models.ticket_category import TicketCategory
    from bot.views.ticket_category_select import _EditCategorySelect

    guild = MagicMock()
    guild.id = 123456789
    cat = TicketCategory(id="cat-uuid-2", guild_id="123", name="Billing", description="", position=1)
    opts = [discord.SelectOption(label="Billing", value="cat-uuid-2")]
    ticket_row_open = {
        "id": "t1",
        "ticketNumber": 1,
        "guildId": "123",
        "authorId": "1",
        "channelId": "888",
        "categoryId": "cat-uuid-1",
        "status": "open",
        "claimedBy": None,
        "transcriptUrl": None,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-01T00:00:00+00:00",
    }
    select = _EditCategorySelect(opts, guild, [cat], ticket_row_open)
    select._values = ["cat-uuid-2"]

    # Case 1: now-non-mod must be rejected and not call service
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.id = 888
    interaction.channel.send = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = 111
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.client = MagicMock()
    interaction.client.db = MagicMock()
    interaction.client.db.get_ticket_by_channel = AsyncMock(return_value=ticket_row_open)
    interaction.client.ticket_service = MagicMock()
    interaction.client.ticket_service.edit_ticket_category = AsyncMock()

    with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=False):
        await select.callback(interaction)
    interaction.client.ticket_service.edit_ticket_category.assert_not_called()
    # Case 2: closed while dropdown open must be rejected after re-fetch
    interaction2 = MagicMock(spec=discord.Interaction)
    interaction2.guild = guild
    interaction2.channel = MagicMock(spec=discord.TextChannel)
    interaction2.channel.id = 888
    interaction2.channel.send = AsyncMock()
    interaction2.user = MagicMock()
    interaction2.user.id = 111
    interaction2.response = MagicMock()
    interaction2.response.send_message = AsyncMock()
    interaction2.client = MagicMock()
    closed_row = {**ticket_row_open, "status": "closed"}
    interaction2.client.db = MagicMock()
    interaction2.client.db.get_ticket_by_channel = AsyncMock(return_value=closed_row)
    interaction2.client.ticket_service = MagicMock()
    interaction2.client.ticket_service.edit_ticket_category = AsyncMock()
    with patch("bot.views.tickets.is_mod_check", new_callable=AsyncMock, return_value=True):
        await select.callback(interaction2)
    interaction2.client.ticket_service.edit_ticket_category.assert_not_called()


def import_module(name: str):
    import importlib

    return importlib.import_module(name)
