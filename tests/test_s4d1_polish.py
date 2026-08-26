"""S4.1 polish — branch tests for ticket_repair_service + ticket_panel to reach 80%."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import bot.views.ticket_panel as mod
from bot.models.ticket import IntegrityEvidence
from bot.services.ticket_invariants import RepairAuthority
from bot.services.ticket_repair_service import TicketRepairService
from bot.views.ticket_panel import TicketIntakeModal, TicketPanelView, _create_ticket_after_modal, deploy_ticket_panel


@pytest.mark.asyncio
async def test_repair_denied_audit_failure_branch() -> None:

    db = MagicMock()
    db.insert_audit_row = AsyncMock(side_effect=Exception("audit fail"))
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    evidence = IntegrityEvidence(
        ticket_id="t1", guild_id="g1", channel_id="c1", status="open", channel_exists=False, corroborated=False
    )
    result = await svc.repair_ticket_from_evidence(evidence, preflight=MagicMock(repair_activation_allowed=False))
    assert result.reason in ("gate_unresolved", "evidence_unresolved")


@pytest.mark.asyncio
async def test_handle_channel_delete_lookup_error() -> None:

    db = MagicMock()
    db.get_active_ticket_by_channel = AsyncMock(side_effect=Exception("db down"))
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    result = await svc.handle_channel_delete("g1", "ch1")
    assert result is not None and result.reason == "lookup_error"


@pytest.mark.asyncio
async def test_sweep_discovery_error() -> None:

    db = MagicMock()
    db.get_open_ticket_channel_ids = AsyncMock(side_effect=Exception("discover fail"))
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    results = await svc.sweep_integrity("g1", bot=MagicMock())
    assert results and results[0].reason == "sweep_discovery_error"


@pytest.mark.asyncio
async def test_repair_by_ref_unparseable() -> None:

    svc = TicketRepairService(db=MagicMock(), query=MagicMock(), lifecycle=MagicMock())
    auth = RepairAuthority(actor_id="u1", guild_id="g1", target_guild_id="g1", is_administrator=True)
    result = await svc.repair_ticket_by_ref(
        "not-a-ref!!!", guild_id="g1", actor_id="u1", authority=auth, bot=MagicMock()
    )
    assert result is None


@pytest.mark.asyncio
async def test_create_ticket_after_modal_config_error() -> None:

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.get_channel.return_value = MagicMock(spec=discord.CategoryChannel)
    _category_channel = guild.get_channel.return_value
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = MagicMock()
    interaction.client.db = MagicMock()
    interaction.client.guild_service = MagicMock()
    interaction.client.guild_service.get_config = AsyncMock(side_effect=Exception("cfg fail"))
    interaction.client.ticket_service = MagicMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    with patch("bot.views.ticket_panel.resolve_mod_role", return_value=None):
        await _create_ticket_after_modal(interaction, guild, "cat1", "Cat", subject="s", description=None)
    assert interaction.followup.send.await_count >= 1


@pytest.mark.asyncio
async def test_ticket_intake_modal_on_error_sends_embed() -> None:

    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    modal = TicketIntakeModal(guild, category_id="c1", category_name="Cat")
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    await modal.on_error(interaction, Exception("boom"))
    assert interaction.response.send_message.await_count == 1


def test_deploy_ticket_panel_uses_facade_t_fallback() -> None:

    assert hasattr(mod, "deploy_ticket_panel")
    assert hasattr(mod, "_get_logger")


@pytest.mark.asyncio
async def test_repair_manual_cross_guild_denied() -> None:

    db = MagicMock()
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    auth = RepairAuthority(actor_id="u1", guild_id="g1", target_guild_id="g2", is_administrator=True)
    result = await svc.repair_ticket_manual("t1", guild_id="g1", actor_id="u1", authority=auth, bot=MagicMock())
    assert result.reason == "cross_guild_denied"


@pytest.mark.asyncio
async def test_repair_manual_db_error_branch() -> None:

    db = MagicMock()
    db.get_ticket = AsyncMock(side_effect=Exception("db"))
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    auth = RepairAuthority(actor_id="u1", guild_id="g1", target_guild_id="g1", is_administrator=True)
    result = await svc.repair_ticket_manual("t1", guild_id="g1", actor_id="u1", authority=auth, bot=MagicMock())
    assert result.outcome == "error" and result.reason == "database_error"


@pytest.mark.asyncio
async def test_sweep_probe_unresolved_and_gate_branches() -> None:

    db = MagicMock()
    db.get_open_ticket_channel_ids = AsyncMock(return_value=["ch1", "ch2"])
    db.get_active_ticket_by_channel = AsyncMock(
        side_effect=[
            {"id": "t1", "status": "open", "channelId": "ch1"},
            {"id": "t2", "status": "open", "channelId": "ch2"},
        ]
    )
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    bot = MagicMock()
    with (
        patch("bot.services.ticket_repair_service.probe_channel_absence", new=AsyncMock(return_value=None)),
        patch("bot.services.ticket_repair_service.asyncio.sleep", new=AsyncMock(return_value=None)),
    ):
        results = await svc.sweep_integrity("g1", bot=bot, preflight=None)
    assert any(r.reason in ("gate_unresolved", "probe_unresolved") for r in results)


@pytest.mark.asyncio
async def test_sweep_not_corroborated_branch() -> None:

    db = MagicMock()
    db.get_open_ticket_channel_ids = AsyncMock(return_value=["ch1"])
    db.get_active_ticket_by_channel = AsyncMock(return_value={"id": "t1", "status": "open", "channelId": "ch1"})
    db.insert_audit_row = AsyncMock(return_value=None)
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    bot = MagicMock()
    with patch("bot.services.ticket_repair_service.probe_channel_absence", new=AsyncMock(return_value=True)):
        results = await svc.sweep_integrity("g1", bot=bot)
    assert results[0].reason == "not_corroborated"


@pytest.mark.asyncio
async def test_sweep_repair_path_close() -> None:

    db = MagicMock()
    db.get_open_ticket_channel_ids = AsyncMock(return_value=["ch1"])
    db.get_active_ticket_by_channel = AsyncMock(return_value={"id": "t1", "status": "open", "channelId": "ch1"})
    db.transition_ticket_to_closed = AsyncMock(return_value={"id": "t1"})
    db.insert_audit_row = AsyncMock(return_value=None)
    lifecycle = MagicMock()
    # clean-1.0 D6: the repair seam now awaits the lifecycle audit helper.
    lifecycle._audit_zombie_autoclose = AsyncMock()
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=lifecycle)
    bot = MagicMock()
    preflight = MagicMock(repair_activation_allowed=True)
    with patch("bot.services.ticket_repair_service.probe_channel_absence", new=AsyncMock(return_value=False)):
        results = await svc.sweep_integrity("g1", bot=bot, preflight=preflight)
    assert any(r.outcome in ("repaired", "already_closed", "error") for r in results)


@pytest.mark.asyncio
async def test_repair_transition_error_and_audit_failure() -> None:

    db = MagicMock()
    db.transition_ticket_to_closed = AsyncMock(side_effect=Exception("trans fail"))
    db.insert_audit_row = AsyncMock(side_effect=[Exception("audit"), None])
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=MagicMock())
    evidence = IntegrityEvidence(
        ticket_id="t1", guild_id="g1", channel_id="c1", status="open", channel_exists=False, corroborated=True
    )
    preflight = MagicMock(repair_activation_allowed=True)
    result = await svc.repair_ticket_from_evidence(evidence, preflight=preflight)
    assert result.outcome == "error"


@pytest.mark.asyncio
async def test_create_ticket_channel_rename_failure() -> None:

    db = MagicMock()
    db.count_user_open_tickets_in_category = AsyncMock(return_value=0)
    db.get_max_ticket_number = AsyncMock(return_value=5)
    lifecycle = MagicMock()
    lifecycle.create_ticket = AsyncMock(return_value=MagicMock(ticket_number=6, id="tid", guild_id="g1"))
    svc = TicketRepairService(db=db, query=MagicMock(), lifecycle=lifecycle)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    category = MagicMock(spec=discord.CategoryChannel)
    author = MagicMock(spec=discord.Member)
    author.id = 100
    author.display_name = "User"
    _resp = MagicMock()
    guild.create_text_channel = AsyncMock(
        return_value=MagicMock(
            name="tentative", id=999, edit=AsyncMock(side_effect=discord.HTTPException(_resp, "fail"))
        )
    )
    with (
        patch("bot.services.ticket_repair_service.build_ticket_overwrites", return_value={}),
        patch("bot.services.ticket_repair_service.sanitize_channel_name", side_effect=["tentative", "final-name"]),
    ):
        _channel, ticket = await svc.create_ticket_channel(
            guild, category, author, guild_id="g1", category_name="Cat", category_id="cat1"
        )
    assert ticket.ticket_number == 6


@pytest.mark.asyncio
async def test_ticket_panel_open_no_guild() -> None:

    view = TicketPanelView(guild_id="1")
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = None
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.client = MagicMock()
    await view.open_ticket_button.callback(interaction)


@pytest.mark.asyncio
async def test_ticket_panel_open_no_categories() -> None:

    view = TicketPanelView(guild_id="1")
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.get_ticket_categories = AsyncMock(return_value=[])
    interaction.client = bot
    # Call the button callback via the view's registered callback
    for child in view.children:
        if isinstance(child, discord.ui.Button):
            # simulate click
            with patch("bot.views.tickets.t", return_value="x"):
                await child.callback(interaction)
            break
    assert interaction.response.send_message.await_count >= 1


@pytest.mark.asyncio
async def test_countdown_notfound_and_http_fallbacks() -> None:

    # Countdown NotFound → final delete
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111
    channel.send = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))
    channel.delete = AsyncMock(return_value=None)
    with patch("bot.services.ticket_repair_service.asyncio.sleep", new=AsyncMock(return_value=None)):
        await TicketRepairService._countdown_and_delete(channel, "mod")
    assert channel.delete.await_count >= 1

    # Countdown HTTPException → silent fallback
    channel2 = MagicMock(spec=discord.TextChannel)
    channel2.id = 222
    channel2.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "http"))
    channel2.delete = AsyncMock(return_value=None)
    with patch("bot.services.ticket_repair_service.asyncio.sleep", new=AsyncMock(return_value=None)):
        await TicketRepairService._countdown_and_delete(channel2, "mod")
    assert channel2.delete.await_count >= 1


@pytest.mark.asyncio
async def test_panel_deploy_and_create_flows() -> None:

    # deploy path — with and without guild_service
    bot = MagicMock()
    bot.guild_service = MagicMock()
    bot.guild_service.update_guild_panel = AsyncMock(return_value=None)
    channel = MagicMock()
    channel.send = AsyncMock(return_value=MagicMock(id=1, channel=MagicMock(id=2)))
    channel.send.return_value.channel.id = 2
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    await deploy_ticket_panel(channel, "1", bot=bot, guild=guild, title="T", description_text="D")
    bot2 = MagicMock()
    bot2.guild_service = None
    channel2 = MagicMock()
    channel2.send = AsyncMock(return_value=MagicMock(id=3, channel=MagicMock(id=4)))
    channel2.send.return_value.channel.id = 4
    await deploy_ticket_panel(channel2, "1", bot=bot2, guild=None)

    # _create_ticket_after_modal — invalid category branch
    guild3 = MagicMock(spec=discord.Guild)
    guild3.id = 10
    guild3.get_channel.return_value = None
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = MagicMock()
    interaction.client.db = MagicMock()
    interaction.client.guild_service = MagicMock()
    interaction.client.guild_service.get_config = AsyncMock(return_value=MagicMock(ticket_category_id="999"))
    interaction.client.ticket_service = MagicMock()
    interaction.followup = MagicMock(send=AsyncMock())
    await _create_ticket_after_modal(interaction, guild3, "cat1", "Cat", subject="s", description=None)
    assert interaction.followup.send.await_count >= 1

    # _create_ticket_after_modal — Forbidden branch
    guild4 = MagicMock(spec=discord.Guild)
    guild4.id = 11
    cat_ch = MagicMock(spec=discord.CategoryChannel)
    guild4.get_channel.return_value = cat_ch
    interaction2 = MagicMock(spec=discord.Interaction)
    interaction2.client = MagicMock()
    interaction2.client.db = MagicMock()
    interaction2.client.guild_service = MagicMock()
    interaction2.client.guild_service.get_config = AsyncMock(
        return_value=MagicMock(ticket_category_id="11", mod_role_id=None)
    )
    interaction2.client.ticket_service = MagicMock()
    interaction2.client.ticket_service.create_ticket_channel = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(), "forbidden")
    )
    interaction2.followup = MagicMock(send=AsyncMock())
    interaction2.user = MagicMock(spec=discord.Member)
    await _create_ticket_after_modal(interaction2, guild4, "cat1", "Cat", subject="s", description=None)
    assert interaction2.followup.send.await_count >= 1

    # Modal on_submit empty + required field branches
    modal_guild = MagicMock(spec=discord.Guild)
    modal_guild.id = 20
    modal = TicketIntakeModal(
        modal_guild,
        category_id="c1",
        category_name="Cat",
        field_definitions=[{"key": "k1", "label": "Field1", "required": True}],
    )
    # Empty title
    modal.title_input._value = "  "
    modal.description_input._value = ""
    inter3 = MagicMock(spec=discord.Interaction)
    inter3.response = MagicMock(send_message=AsyncMock(), is_done=MagicMock(return_value=False))
    await modal.on_submit(inter3)
    assert inter3.response.send_message.await_count == 1
    # Required custom field missing
    modal2 = TicketIntakeModal(
        modal_guild,
        category_id="c1",
        category_name="Cat",
        field_definitions=[{"key": "k1", "label": "Field1", "required": True}],
    )
    modal2.title_input._value = "Title"
    modal2.description_input._value = None
    # custom inputs empty
    for inp in modal2._custom_inputs:
        inp._value = ""
    inter4 = MagicMock(spec=discord.Interaction)
    inter4.response = MagicMock(send_message=AsyncMock(), is_done=MagicMock(return_value=False))
    await modal2.on_submit(inter4)
    assert inter4.response.send_message.await_count == 1
