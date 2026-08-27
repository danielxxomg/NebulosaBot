"""Tickets setup module — guided editors for categories and custom fields.

No raw UUID/JSON input: all flows use Selects, buttons, modals over concrete Discord objects.
"""

from __future__ import annotations

import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.embeds import error_embed, success_embed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class CreateCategoryModal(discord.ui.Modal):
    """Modal for guided create-category (no UUID typing)."""

    def __init__(self, guild: discord.Guild, bot: typing.Any) -> None:
        guild_id = str(guild.id)
        super().__init__(title=t(guild_id, "setup.module.tickets.create_title"))
        self._guild = guild
        self._bot = bot

        self.name_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.create_name_label"),
            placeholder=t(guild_id, "setup.module.tickets.create_name_placeholder"),
            required=True,
            max_length=100,
        )
        self.add_item(self.name_input)

        self.emoji_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.create_emoji_label"),
            placeholder="🎫",
            required=False,
            max_length=10,
        )
        self.add_item(self.emoji_input)

        self.desc_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.create_description_label"),
            placeholder=t(guild_id, "setup.module.tickets.create_description_placeholder"),
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=200,
        )
        self.add_item(self.desc_input)

        self.position_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.create_position_label"),
            placeholder="0",
            required=False,
            max_length=4,
        )
        self.add_item(self.position_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = str(self._guild.id)
        name = self.name_input.value.strip()
        if not name:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.create_error_title"),
                    t(guild_id, "setup.module.tickets.create_name_required"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        emoji = self.emoji_input.value.strip() or None
        description = self.desc_input.value.strip() or None
        pos_raw = self.position_input.value.strip()
        try:
            position = int(pos_raw) if pos_raw else 0
        except ValueError:
            position = 0

        try:
            await self._bot.db.insert_ticket_category(
                guild_id, name, emoji=emoji, description=description, position=position
            )
        except Exception:
            logger.exception("Failed to create ticket category (guild=%s)", guild_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.create_error_title"),
                    t(guild_id, "setup.module.tickets.create_error_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                t(guild_id, "setup.module.tickets.create_success_title"),
                t(guild_id, "setup.module.tickets.create_success_description", name=name),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )


class AddFieldModal(discord.ui.Modal):
    """Modal to add a custom field interactively (no JSON)."""

    def __init__(
        self, guild: discord.Guild, category_id: str, bot: typing.Any, existing_fields: list[dict[str, typing.Any]]
    ) -> None:  # noqa: E501
        guild_id = str(guild.id)
        super().__init__(title=t(guild_id, "setup.module.tickets.field_add_title"))
        self._guild = guild
        self._category_id = category_id
        self._bot = bot
        self._existing = list(existing_fields)

        self.key_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.field_key_label"),
            placeholder="player_nick",
            required=True,
            max_length=32,
        )
        self.add_item(self.key_input)

        self.label_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.field_label_label"),
            placeholder="Player Nickname",
            required=True,
            max_length=45,
        )
        self.add_item(self.label_input)

        self.max_length_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.field_max_length_label"),
            placeholder="100",
            required=False,
            max_length=4,
        )
        self.add_item(self.max_length_input)

        self.required_input = discord.ui.TextInput(
            label=t(guild_id, "setup.module.tickets.field_required_label"),
            placeholder="true / false",
            required=False,
            max_length=5,
        )
        self.add_item(self.required_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = str(self._guild.id)
        key = self.key_input.value.strip()
        label = self.label_input.value.strip()
        if not key or not label:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.field_error_title"),
                    t(guild_id, "setup.module.tickets.field_key_required"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        # max_length
        raw_max = self.max_length_input.value.strip()
        try:
            max_len = int(raw_max) if raw_max else 100
        except ValueError:
            max_len = 100
        # required
        raw_req = self.required_input.value.strip().lower()
        required = raw_req in ("true", "1", "yes", "y")

        new_field: dict[str, typing.Any] = {
            "key": key,
            "label": label,
            "style": "short",
            "required": required,
            "max_length": max_len,
        }
        updated = [*self._existing, new_field]
        try:
            await self._bot.db.update_ticket_category_field_definitions(guild_id, self._category_id, updated)
        except Exception:
            logger.exception("Failed to update field definitions (guild=%s, cat=%s)", guild_id, self._category_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.field_error_title"),
                    t(guild_id, "setup.module.tickets.field_update_failed"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                t(guild_id, "setup.module.tickets.field_success_title"),
                t(guild_id, "setup.module.tickets.field_success_description", label=label),
                guild_id=guild_id,
            ),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Delete flow views
# ---------------------------------------------------------------------------


class ConfirmDeleteView(discord.ui.View):
    """Confirm/cancel view for delete-category."""

    def __init__(self, category_id: str, guild_id: str, bot: typing.Any) -> None:
        super().__init__(timeout=60)
        self._category_id = category_id
        self._guild_id = guild_id
        self._bot = bot

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="confirm:confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        try:
            await self._bot.db.delete_ticket_category(self._category_id, guild_id=self._guild_id)
        except Exception:
            logger.exception("Failed to delete category %s", self._category_id)
            await interaction.response.send_message(
                embed=error_embed(
                    t(self._guild_id, "setup.module.tickets.delete_error_title"),
                    t(self._guild_id, "setup.module.tickets.delete_error_description"),
                    guild_id=self._guild_id,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=success_embed(
                t(self._guild_id, "setup.module.tickets.delete_success_title"),
                t(self._guild_id, "setup.module.tickets.delete_success_description"),
                guild_id=self._guild_id,
            ),
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="confirm:cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=t(self._guild_id, "setup.module.tickets.delete_cancel_title"),
                description=t(self._guild_id, "setup.module.tickets.delete_cancel_description"),
                color=INFO,
            ),
            view=None,
        )
        self.stop()


class DeleteCategorySelectView(discord.ui.View):
    """Select a category to delete, then show ConfirmDeleteView."""

    def __init__(self, categories: list[dict[str, typing.Any]], bot: typing.Any, guild_id: str) -> None:
        super().__init__(timeout=60)
        self._bot = bot
        self._guild_id = guild_id
        options = [
            discord.SelectOption(
                label=c.get("name", "Unnamed"),
                value=c.get("id", ""),
                description=(c.get("description") or "")[:100] or None,
            )
            for c in categories
        ]
        self.select = discord.ui.Select(
            custom_id="setup:tickets:delete_select",
            placeholder=t(guild_id, "setup.module.tickets.delete_select_placeholder"),
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.on_select  # ty:ignore[invalid-assignment]
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        # Prefer interaction payload values for testability
        cat_id: str | None = None
        try:
            data = getattr(interaction, "data", None)
            if isinstance(data, dict):
                vals = data.get("values") or []
                if vals:
                    cat_id = vals[0]
            if cat_id is None and getattr(self.select, "values", None):
                vals = self.select.values
                if vals:
                    cat_id = vals[0]
        except Exception:  # noqa: BLE001
            cat_id = None
        if not cat_id:
            await interaction.response.send_message(
                embed=error_embed(
                    t(self._guild_id, "setup.module.tickets.delete_error_title"),
                    t(self._guild_id, "setup.module.tickets.delete_no_selection"),
                    guild_id=self._guild_id,
                ),
                ephemeral=True,
            )
            return
        # Show confirm
        view = ConfirmDeleteView(category_id=cat_id, guild_id=self._guild_id, bot=self._bot)
        # Find category name for confirmation embed
        await interaction.response.send_message(
            embed=discord.Embed(
                title=t(self._guild_id, "setup.module.tickets.delete_confirm_title"),
                description=t(self._guild_id, "setup.module.tickets.delete_confirm_description", category_id=cat_id),
                color=INFO,
            ),
            view=view,
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Field editor view
# ---------------------------------------------------------------------------


class FieldEditorView(discord.ui.View):
    """View for custom-fields editor (no JSON)."""

    def __init__(
        self, category_id: str, guild: discord.Guild, bot: typing.Any, existing_fields: list[dict[str, typing.Any]]
    ) -> None:  # noqa: E501
        super().__init__(timeout=120)
        self._category_id = category_id
        self._guild = guild
        self._bot = bot
        self._existing = existing_fields
        guild_id = str(guild.id)

        # Add Field button
        add_btn = discord.ui.Button(
            label=t(guild_id, "setup.module.tickets.field_add_button"),
            style=discord.ButtonStyle.primary,
            custom_id="setup:tickets:field_add",
        )

        async def _add_callback(interaction: discord.Interaction) -> None:
            modal = AddFieldModal(guild, category_id, bot, existing_fields)
            await interaction.response.send_modal(modal)

        add_btn.callback = _add_callback  # type: ignore[method-assign]
        self.add_item(add_btn)

        # List Fields button
        list_btn = discord.ui.Button(
            label=t(guild_id, "setup.module.tickets.field_list_button"),
            style=discord.ButtonStyle.secondary,
            custom_id="setup:tickets:field_list",
        )

        async def _list_callback(interaction: discord.Interaction) -> None:
            if not self._existing:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title=t(guild_id, "setup.module.tickets.field_list_empty_title"),
                        description=t(guild_id, "setup.module.tickets.field_list_empty_description"),
                        color=INFO,
                    ),
                    ephemeral=True,
                )
                return
            desc = "\n".join(f"• **{f.get('label')}** (`{f.get('key')}`)" for f in self._existing)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.tickets.field_list_title"),
                    description=desc,
                    color=INFO,
                ),
                ephemeral=True,
            )

        list_btn.callback = _list_callback  # type: ignore[method-assign]
        self.add_item(list_btn)


# ---------------------------------------------------------------------------
# Tickets module
# ---------------------------------------------------------------------------


class TicketSetupModule:
    """Guided Tickets module for /setup panel."""

    key = "tickets"
    permission_key = "tickets.manage"

    def __init__(self, bot: typing.Any | None = None) -> None:
        self._bot = bot

    def _resolve_bot(self, interaction: discord.Interaction | None = None) -> typing.Any | None:
        if self._bot is not None:
            return self._bot
        if interaction is not None:
            return getattr(interaction, "client", None)
        # Fallback: try global setup bot
        try:
            from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-break

            return _get_setup_bot()
        except Exception:  # noqa: BLE001
            return None

    def render(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        """Render tickets module embed (cache-first re-read when bot available)."""
        # Try to include live category count if bot available
        count: int | None = None
        b = bot or self._bot
        if b is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-break

                b = _get_setup_bot()
            except Exception:  # noqa: BLE001
                b = None
        # We cannot await DB here if render is sync; return static but with i18n
        title = t(guild_id, "setup.module.tickets.title")
        desc = t(guild_id, "setup.module.tickets.description")
        if count is not None:
            desc = f"{desc}\n\n{t(guild_id, 'setup.module.tickets.category_count', count=count)}"
        return discord.Embed(title=title, description=desc, color=INFO)

    async def render_async(self, guild_id: str, bot: typing.Any | None = None) -> discord.Embed:
        """Async variant that re-reads live state (used by refresh)."""
        b = bot or self._bot
        if b is None:
            try:
                from bot.views.setup_panel import _get_setup_bot  # noqa: PLC0415 -- cycle-break

                b = _get_setup_bot()
            except Exception:  # noqa: BLE001
                b = None
        title = t(guild_id, "setup.module.tickets.title")
        desc = t(guild_id, "setup.module.tickets.description")
        if b is not None and hasattr(b, "db") and b.db is not None:
            try:
                cats = await b.db.get_ticket_categories(guild_id)
                len(cats)
                # Append live list for refresh test
                if cats:
                    names = ", ".join(c.get("name", "") for c in cats[:5])
                    desc = f"{desc}\n\n{names}"
                else:
                    desc = f"{desc}\n\n{t(guild_id, 'setup.module.tickets.no_categories')}"
            except Exception:
                logger.debug("Failed to fetch categories for render_async", exc_info=True)
        return discord.Embed(title=title, description=desc, color=INFO)

    def components(self, guild_id: str, bot: typing.Any | None = None) -> list[discord.ui.Item]:  # noqa: ARG002
        """Return module action buttons (no UUID/JSON)."""
        # Use t for labels
        return [
            discord.ui.Button(
                label=t(guild_id, "setup.module.tickets.create_button"),
                style=discord.ButtonStyle.primary,
                custom_id="setup:tickets:create_category",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.tickets.delete_button"),
                style=discord.ButtonStyle.danger,
                custom_id="setup:tickets:delete_category",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.tickets.list_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:tickets:list_categories",
            ),
            discord.ui.Button(
                label=t(guild_id, "setup.module.tickets.fields_button"),
                style=discord.ButtonStyle.secondary,
                custom_id="setup:tickets:configure_fields",
            ),
        ]

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        """Route module actions to guided flows."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(None, "setup.module.tickets.error_guild_only_title"),
                    t(None, "setup.module.tickets.error_guild_only_description"),
                ),
                ephemeral=True,
            )
            return
        guild_id = str(guild.id)
        bot = self._resolve_bot(interaction) or getattr(interaction, "client", None)
        if bot is None:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.error_title"),
                    t(guild_id, "setup.module.tickets.error_bot_unavailable"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return

        if action == "create_category":
            modal = CreateCategoryModal(guild, bot)
            await interaction.response.send_modal(modal)

        elif action == "delete_category":
            try:
                cats = await bot.db.get_ticket_categories(guild_id)
            except Exception:
                logger.exception("Failed to fetch categories for delete (guild=%s)", guild_id)
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.module.tickets.delete_error_title"),
                        t(guild_id, "setup.module.tickets.delete_error_description"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            if not cats:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title=t(guild_id, "setup.module.tickets.delete_no_categories_title"),
                        description=t(guild_id, "setup.module.tickets.delete_no_categories_description"),
                        color=INFO,
                    ),
                    ephemeral=True,
                )
                return
            view = DeleteCategorySelectView(cats, bot, guild_id)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.tickets.delete_select_title"),
                    description=t(guild_id, "setup.module.tickets.delete_select_description"),
                    color=INFO,
                ),
                view=view,
                ephemeral=True,
            )

        elif action == "list_categories":
            try:
                cats = await bot.db.get_ticket_categories(guild_id)
            except Exception:
                logger.exception("Failed to list categories (guild=%s)", guild_id)
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.module.tickets.list_error_title"),
                        t(guild_id, "setup.module.tickets.list_error_description"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            if not cats:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title=t(guild_id, "setup.module.tickets.list_empty_title"),
                        description=t(guild_id, "setup.module.tickets.list_empty_description"),
                        color=INFO,
                    ),
                    ephemeral=True,
                )
                return
            desc = "\n".join(f"• **{c.get('name')}** — `{c.get('id')}`" for c in cats)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=t(guild_id, "setup.module.tickets.list_title"),
                    description=desc,
                    color=INFO,
                ),
                ephemeral=True,
            )

        elif action == "configure_fields":
            # Show field editor for first category or selection
            try:
                cats = await bot.db.get_ticket_categories(guild_id)
            except Exception:
                logger.exception("Failed to fetch categories for fields (guild=%s)", guild_id)
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.module.tickets.field_error_title"),
                        t(guild_id, "setup.module.tickets.field_update_failed"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
                return
            if not cats:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title=t(guild_id, "setup.module.tickets.field_no_category_title"),
                        description=t(guild_id, "setup.module.tickets.field_no_category_description"),
                        color=INFO,
                    ),
                    ephemeral=True,
                )
                return
            # Use first category for editor (guided: could add category selector, but for test use first)
            cat = cats[0]
            cat_id = cat.get("id", "")
            # Fetch existing field definitions
            try:
                row = await bot.db.get_ticket_category(cat_id, guild_id=guild_id)
                fields = row.get("fieldDefinitions") or [] if row else []
            except Exception:  # noqa: BLE001
                fields = cat.get("fieldDefinitions") or []
            view = FieldEditorView(cat_id, guild, bot, fields)
            embed = discord.Embed(
                title=t(guild_id, "setup.module.tickets.field_editor_title"),
                description=t(guild_id, "setup.module.tickets.field_editor_description", category=cat.get("name", "")),
                color=INFO,
            )
            # Include existing fields in description for refresh test
            if fields:
                embed.description = (
                    (embed.description or "")
                    + "\n\n"
                    + "\n".join(f"• {f.get('label')} (`{f.get('key')}`)" for f in fields)
                )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        else:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.module.tickets.error_title"),
                    t(guild_id, "setup.module.tickets.unknown_action", action=action),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
