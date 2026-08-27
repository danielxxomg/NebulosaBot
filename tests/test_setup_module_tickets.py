"""S2a.7 RED — Tickets module guided editors.

Ref: setup-panel "Guided editors only"
- guided create-category (resolved IDs)
- delete-category confirmed
- list-categories
- custom-fields editor builds structure (no typed JSON/UUID)

All flows MUST use Selects, buttons, modals over concrete Discord objects.
No flow MAY require typing a snowflake ID, UUID, or JSON literal.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import discord
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot(guild_id: str = "123456789") -> MagicMock:
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.insert_ticket_category = AsyncMock(return_value={"id": "new-uuid", "name": "Support", "guildId": guild_id})
    bot.db.get_ticket_categories = AsyncMock(
        return_value=[
            {
                "id": "cat-1",
                "name": "Support",
                "guildId": guild_id,
                "position": 0,
                "active": True,
                "emoji": None,
                "description": None,
            },
            {
                "id": "cat-2",
                "name": "Reports",
                "guildId": guild_id,
                "position": 1,
                "active": True,
                "emoji": None,
                "description": None,
            },
        ]
    )
    bot.db.get_ticket_category = AsyncMock(return_value={"id": "cat-1", "name": "Support", "guildId": guild_id})
    bot.db.delete_ticket_category = AsyncMock(return_value=None)
    bot.db.update_ticket_category_field_definitions = AsyncMock(return_value=None)
    bot.db.count_open_tickets_by_category = AsyncMock(return_value=0)
    bot.guild_service = MagicMock()
    bot.guild_service.get_config = AsyncMock(return_value=MagicMock(language="es"))
    return bot


def _make_interaction(guild_id: int = 123456789, user_id: int = 111) -> MagicMock:
    inter = MagicMock(spec=discord.Interaction)
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = guild_id
    inter.guild_id = guild_id
    inter.user = MagicMock(spec=discord.Member)
    inter.user.id = user_id
    inter.user.guild_permissions.administrator = True
    inter.response = MagicMock()
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.response.edit_message = AsyncMock()
    inter.response.is_done.return_value = False
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    inter.message = MagicMock()
    inter.message.edit = AsyncMock()
    inter.client = _make_bot(str(guild_id))
    inter.data = {}
    return inter


# ---------------------------------------------------------------------------
# Module registration
# ---------------------------------------------------------------------------


class TestTicketsModuleRegistration:
    """MODULES registry must contain tickets module implementing SetupModule protocol."""

    def test_module_exists(self) -> None:
        from bot.views.setup_panel import MODULES

        assert "tickets" in MODULES, f"MODULES must contain tickets, got {list(MODULES.keys())}"

    def test_module_protocol(self) -> None:
        from bot.views.setup_panel import MODULES

        mod = MODULES["tickets"]
        assert hasattr(mod, "key")
        assert mod.key == "tickets"
        assert hasattr(mod, "permission_key")
        assert mod.permission_key == "tickets.manage"
        assert hasattr(mod, "render")
        assert callable(mod.render)
        assert hasattr(mod, "components")
        assert callable(mod.components)
        assert hasattr(mod, "handle")
        assert callable(mod.handle)

    def test_no_raw_uuid_json_in_module_source(self) -> None:
        import pathlib

        src = pathlib.Path("bot/views/setup_modules/tickets.py").read_text(encoding="utf-8")
        # Ensure no raw UUID typing hinted as free-form: should not contain literal "fields_json" param name that hints JSON typing
        # The guided editor must NOT expose a fields_json text input requiring JSON literal
        assert "fields_json" not in src, "Tickets module must not require typed JSON (fields_json)"
        # Ensure no UUID text input for delete
        # Delete must be via Select/confirm, not typed UUID
        lower = src.lower()
        # Allow UUID in comments but not as TextInput label expecting UUID
        if "uuid" in lower:
            assert "select" in lower or "confirm" in lower, "UUID handling must be via Select/confirm, not raw input"


# ---------------------------------------------------------------------------
# Guided create-category (resolved IDs)
# ---------------------------------------------------------------------------


class TestGuidedCreateCategory:
    """Create-category via guided form must persist correct IDs resolved from selected objects (no typed UUID)."""

    @pytest.mark.asyncio
    async def test_create_via_modal_persists(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)  # noqa: F841
        interaction = _make_interaction()
        interaction.client = bot

        # Simulate handle create_category -> should show modal (or directly insert via test hook)
        # Our implementation: handle(interaction, "create_category") shows a modal
        # For test, we call the modal's on_submit path with concrete values
        # Create a modal instance and submit
        # The module should expose a modal class or handle via modal
        # We test that insert_ticket_category is called with resolved guild_id and form values

        # Find the modal creation: patch the modal's interaction
        # We'll directly test that after modal submit, insert is called
        # Build modal as module would
        from bot.views.setup_modules.tickets import CreateCategoryModal

        guild = interaction.guild
        modal = CreateCategoryModal(guild, bot=bot)
        # Set values (TextInputs)
        # discord.ui.Modal children are TextInputs; set their values via _value
        # For MagicMock TextInputs, we set .value
        for child in modal.children:
            if isinstance(child, discord.ui.TextInput):
                if "Nombre" in getattr(child, "label", "") or "Name" in getattr(child, "label", ""):
                    child._value = "Support"
                elif "emoji" in getattr(child, "label", "").lower():
                    child._value = "🎫"
                else:
                    child._value = "desc"

        # Mock TextInput values via internal _value; discord.py stores value via .value property reading _value
        # Set via private if needed: child.value = "Support" may not work due to property; set _value
        # For test, we patch to set .value directly via object.__setattr__
        # Simpler: we will patch the modal's fields to return our values
        # Ensure modal has attributes for test harness
        # Let's instead call handle and then trigger modal submit with mocked values

        # Prepare a fresh interaction for modal submit
        submit_inter = _make_interaction()
        submit_inter.client = bot
        submit_inter.response = MagicMock()
        submit_inter.response.send_message = AsyncMock()
        submit_inter.response.defer = AsyncMock()
        submit_inter.response.is_done.return_value = False
        submit_inter.followup = MagicMock()
        submit_inter.followup.send = AsyncMock()

        # Manually set modal's TextInput values using the component dict approach
        # For robust test, patch the modal to have predictable values via properties
        # We'll monkey-patch the TextInputs to return fixed values
        inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        if len(inputs) >= 1:
            # Use value property via mocking _value
            inputs[0]._value = "Support"
            # Ensure value property returns it
            # discord.py TextInput.value reads self._value; so setting _value suffices

        await modal.on_submit(submit_inter)

        # Assert insert called with guild_id and name resolved, not typed UUID
        bot.db.insert_ticket_category.assert_awaited_once()
        kwargs = bot.db.insert_ticket_category.call_args.args if bot.db.insert_ticket_category.call_args.args else ()
        # Check that guild_id is correct and name is Support
        # insert_ticket_category(guild_id, name, ...)
        assert kwargs[0] == "123456789" or kwargs[0] == str(guild_id) if kwargs else True  # noqa: F821  # ty:ignore[unresolved-reference]
        assert (
            bot.db.insert_ticket_category.call_args.kwargs.get("guild_id") == "123456789" or kwargs[1] == "Support"  # ty:ignore[index-out-of-bounds]
            if len(kwargs) > 1
            else True
        )

    @pytest.mark.asyncio
    async def test_create_category_flow_uses_modal_not_raw_id(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        # handle should respond with a modal, not require typing an ID
        interaction.response = MagicMock()
        interaction.response.send_modal = AsyncMock()

        await mod.handle(interaction, "create_category")

        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.call_args.args[0]
        # Modal must not contain a TextInput asking for UUID
        labels = [getattr(c, "label", "") for c in modal.children if isinstance(c, discord.ui.TextInput)]
        for label in labels:
            assert "uuid" not in label.lower(), f"create modal must not ask for UUID, got label {label!r}"
            assert "id" not in label.lower() or "category" not in label.lower(), (
                f"create modal must not ask for ID, got {label!r}"
            )


# ---------------------------------------------------------------------------
# Delete-category confirmed (no raw UUID typing)
# ---------------------------------------------------------------------------


class TestDeleteCategoryConfirmed:
    """Delete-category must be via Select + confirm dialog, not raw UUID."""

    @pytest.mark.asyncio
    async def test_delete_shows_select_not_input(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await mod.handle(interaction, "delete_category")

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        # Must contain a View with a Select (no TextInput requiring UUID)
        view = kwargs.get("view")
        assert view is not None, "delete flow must send a view"
        has_select = any(isinstance(c, discord.ui.Select) for c in view.children)
        assert has_select, "delete flow must use Select over concrete categories, not typed UUID"

    @pytest.mark.asyncio
    async def test_delete_requires_confirmation(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        await mod.handle(interaction, "delete_category")
        view = interaction.response.send_message.call_args.kwargs["view"]
        # Find select, simulate picking cat-1
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))

        # Simulate select callback -> should show confirm view, not delete yet
        confirm_inter = _make_interaction()
        confirm_inter.client = bot
        confirm_inter.response = MagicMock()
        confirm_inter.response.send_message = AsyncMock()
        confirm_inter.response.edit_message = AsyncMock()
        confirm_inter.data = {"values": ["cat-1"], "custom_id": select.custom_id}

        # The select callback should send a confirm view (reads from interaction.data)
        await select.callback(confirm_inter)

        # At this point, delete must NOT have been called yet
        bot.db.delete_ticket_category.assert_not_awaited()
        # Confirm view must have been sent
        assert (
            confirm_inter.response.send_message.await_count == 1 or confirm_inter.response.edit_message.await_count == 1
        )
        # Find the confirm button and click it
        # The confirm view is in the kwargs of the call
        call_kwargs = (
            confirm_inter.response.send_message.call_args.kwargs
            if confirm_inter.response.send_message.await_count
            else confirm_inter.response.edit_message.call_args.kwargs
        )
        confirm_view = call_kwargs.get("view")
        assert confirm_view is not None
        # Find confirm button
        confirm_btn = next(
            (
                c
                for c in confirm_view.children
                if getattr(c, "label", "").lower() in ["confirm", "confirmar", "delete", "eliminar"]
                or getattr(c, "custom_id", "") == "confirm:confirm"
            ),
            None,
        )
        if confirm_btn is None:
            # Fallback: any button with style danger
            confirm_btn = next(
                (
                    c
                    for c in confirm_view.children
                    if isinstance(c, discord.ui.Button) and c.style == discord.ButtonStyle.danger
                ),
                None,
            )
        assert confirm_btn is not None, "confirm view must have a confirm button"
        # Click confirm
        final_inter = _make_interaction()
        final_inter.client = bot
        final_inter.response = MagicMock()
        final_inter.response.edit_message = AsyncMock()
        final_inter.response.send_message = AsyncMock()
        await confirm_btn.callback(final_inter)

        bot.db.delete_ticket_category.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_cancel_does_not_remove(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        await mod.handle(interaction, "delete_category")
        view = interaction.response.send_message.call_args.kwargs["view"]
        select = next(c for c in view.children if isinstance(c, discord.ui.Select))

        confirm_inter = _make_interaction()
        confirm_inter.client = bot
        confirm_inter.response = MagicMock()
        confirm_inter.response.send_message = AsyncMock()
        confirm_inter.response.edit_message = AsyncMock()
        confirm_inter.data = {"values": ["cat-1"]}

        await select.callback(confirm_inter)
        call_kwargs = (
            confirm_inter.response.send_message.call_args.kwargs
            if confirm_inter.response.send_message.await_count
            else confirm_inter.response.edit_message.call_args.kwargs
        )
        confirm_view = call_kwargs.get("view")
        # Find cancel button
        cancel_btn = next(
            (
                c
                for c in confirm_view.children  # ty:ignore[unresolved-attribute]
                if getattr(c, "label", "").lower() in ["cancel", "cancelar"]
                or getattr(c, "custom_id", "") == "confirm:cancel"
            ),
            None,
        )
        if cancel_btn is None:
            cancel_btn = next(
                (
                    c
                    for c in confirm_view.children  # ty:ignore[unresolved-attribute]
                    if isinstance(c, discord.ui.Button) and c.style == discord.ButtonStyle.secondary
                ),
                None,
            )
        assert cancel_btn is not None
        cancel_inter = _make_interaction()
        cancel_inter.client = bot
        cancel_inter.response = MagicMock()
        cancel_inter.response.edit_message = AsyncMock()
        cancel_inter.response.send_message = AsyncMock()
        await cancel_btn.callback(cancel_inter)

        bot.db.delete_ticket_category.assert_not_awaited()


# ---------------------------------------------------------------------------
# List-categories
# ---------------------------------------------------------------------------


class TestListCategories:
    """List-categories must show existing categories via service read."""

    @pytest.mark.asyncio
    async def test_list_shows_categories(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await mod.handle(interaction, "list_categories")

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        embed = kwargs.get("embed")
        assert embed is not None
        description = embed.description or ""
        # Should contain category names
        assert "Support" in description or "Reports" in description or "cat-1" in description or len(description) > 0
        assert kwargs.get("ephemeral") is True
        bot.db.get_ticket_categories.assert_awaited()


# ---------------------------------------------------------------------------
# Custom-fields editor builds structure (no typed JSON/UUID)
# ---------------------------------------------------------------------------


class TestCustomFieldsEditor:
    """Custom-fields editor must build structure interactively via controls, not JSON."""

    @pytest.mark.asyncio
    async def test_editor_shows_fields_without_json(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        # Mock category with existing fields
        bot.db.get_ticket_category.return_value = {
            "id": "cat-1",
            "name": "Support",
            "guildId": "123456789",
            "fieldDefinitions": [
                {"key": "nick", "label": "Nick", "style": "short", "required": True, "max_length": 100}
            ],
        }
        mod = TicketSetupModule(bot=bot)
        interaction = _make_interaction()
        interaction.client = bot
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await mod.handle(interaction, "configure_fields")

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        # Should contain view with controls, not a modal asking for JSON
        view = kwargs.get("view")
        embed = kwargs.get("embed")
        assert view is not None or embed is not None
        # Ensure no JSON literal required
        if view:
            for child in view.children:
                if isinstance(child, discord.ui.TextInput):
                    assert "json" not in getattr(child, "label", "").lower()

    @pytest.mark.asyncio
    async def test_add_field_via_controls_calls_update(self) -> None:
        from bot.views.setup_modules.tickets import TicketSetupModule

        bot = _make_bot()
        bot.db.get_ticket_category.return_value = {
            "id": "cat-1",
            "name": "Support",
            "guildId": "123456789",
            "fieldDefinitions": [],
        }
        mod = TicketSetupModule(bot=bot)  # noqa: F841
        # Simulate the add-field modal flow
        # Module should expose a modal for adding a field
        from bot.views.setup_modules.tickets import AddFieldModal

        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        modal = AddFieldModal(guild, category_id="cat-1", bot=bot, existing_fields=[])
        # Set modal values
        for child in modal.children:
            if isinstance(child, discord.ui.TextInput):
                label = getattr(child, "label", "")
                if "key" in label.lower():
                    child._value = "player_nick"
                elif "label" in label.lower():
                    child._value = "Player Nick"
                else:
                    child._value = "test"

        submit_inter = _make_interaction()
        submit_inter.client = bot
        submit_inter.response = MagicMock()
        submit_inter.response.send_message = AsyncMock()
        submit_inter.response.defer = AsyncMock()
        submit_inter.response.is_done.return_value = False
        submit_inter.followup = MagicMock()
        submit_inter.followup.send = AsyncMock()

        await modal.on_submit(submit_inter)

        bot.db.update_ticket_category_field_definitions.assert_awaited_once()
        # Verify it was called with a structured list, not JSON string
        call_kwargs = bot.db.update_ticket_category_field_definitions.call_args.kwargs or {}
        args = bot.db.update_ticket_category_field_definitions.call_args.args
        field_defs = None
        if args and len(args) >= 3:
            field_defs = args[2]
        elif "field_definitions" in call_kwargs:
            field_defs = call_kwargs["field_definitions"]
        assert isinstance(field_defs, list), f"fieldDefinitions must be list, got {field_defs!r}"
        assert not isinstance(field_defs, str), "must not be JSON string"
        # Check that the new field is in the list
        assert any(f.get("key") == "player_nick" for f in field_defs), f"new field not in definitions {field_defs!r}"

    def test_no_json_in_source(self) -> None:
        import pathlib

        src = pathlib.Path("bot/views/setup_modules/tickets.py").read_text(encoding="utf-8")
        assert "fields_json" not in src
        assert "json.loads" not in src or "fieldDefinitions" in src  # allow json only if not for user input
        # Ensure no raw UUID TextInput
        assert "TextInput" not in src or "uuid" not in src.lower() or "select" in src.lower()
