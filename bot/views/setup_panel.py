"""SetupPanelView — persistent /setup panel with static custom_ids and module routing."""

from __future__ import annotations

import logging
import typing

import discord

from bot.core.i18n import t
from bot.utils.brand import INFO
from bot.utils.checks import can_member
from bot.utils.embeds import error_embed
from bot.views.setup_modules import MODULES

logger = logging.getLogger(__name__)

# Per-kind template picker custom_ids (SDD greeting-templates remediation):
# attached from MODULES at construction so the /setup panel the interaction
# actually reaches exposes the pickers, and the persistent view registered
# in bot.setup_hook routes them after restarts.
_TEMPLATE_SELECT_IDS = frozenset({
    "setup:welcome:select_template",
    "setup:goodbye:select_template",
})

# Global bot reference for module render helpers (set in setup_hook)
_setup_bot: typing.Any | None = None


def _get_setup_bot() -> typing.Any | None:
    return _setup_bot


def set_setup_bot(bot: typing.Any | None) -> None:
    global _setup_bot
    _setup_bot = bot


def _parse_module_from_footer(embed: discord.Embed | None) -> str:
    """Extract module key from footer token nbpanel|module=<key>."""
    if embed is None or embed.footer is None:
        return "tickets"
    text = getattr(embed.footer, "text", "") or ""
    if "nbpanel|module=" in text:
        try:
            # Footer is exactly nbpanel|module=<key>
            return text.split("nbpanel|module=")[1].split()[0].strip()
        except Exception:  # noqa: BLE001
            return "tickets"
    return "tickets"


async def _build_embed(
    guild_id: str,
    module_key: str,
    bot: typing.Any | None = None,
    *,
    mod: typing.Any | None = None,
) -> discord.Embed:
    """Build panel embed for module_key, recomputing from services cache-first."""
    b = bot or _get_setup_bot()
    # Try module render
    target_mod = mod if mod is not None else MODULES.get(module_key)
    embed: discord.Embed | None = None
    if target_mod is not None:
        # Prefer async render_async if available
        try:
            if hasattr(target_mod, "render_async"):
                embed = await target_mod.render_async(guild_id, bot=b)  # ty:ignore[call-non-callable]
            else:
                # sync render may still be callable
                res = target_mod.render(guild_id)
                if hasattr(res, "__await__"):
                    embed = await res  # noqa: PGH003  # ty:ignore[invalid-await]
                else:
                    embed = res
        except Exception:
            logger.exception("Module %s render failed (guild=%s)", module_key, guild_id)
            embed = None
    if embed is None:
        title = t(guild_id, "setup.panel.title")
        desc = t(guild_id, "setup.panel.description")
        embed = discord.Embed(title=title, description=desc, color=INFO)

    # Breadcrumb in author line — localized via t(guild_id, setup.panel.breadcrumb.<module>)
    breadcrumb_key = f"setup.panel.breadcrumb.{module_key}"
    breadcrumb = t(guild_id, breadcrumb_key)
    if breadcrumb == breadcrumb_key:
        # Fallback to capitalized module name
        breadcrumb = module_key.capitalize()
        # Try generic breadcrumb with param
        generic = t(guild_id, "setup.panel.breadcrumb_generic", module=module_key)
        if generic != "setup.panel.breadcrumb_generic":
            breadcrumb = generic
    embed.set_author(name=breadcrumb)
    embed.set_footer(text=f"nbpanel|module={module_key}")
    embed.color = INFO
    return embed


TAB_MODULES = ("tickets", "welcome", "goodbye", "log", "language")
TAB_EMOJIS: dict[str, str] = {
    "tickets": "🎫",
    "welcome": "👋",
    "goodbye": "🚪",
    "log": "📜",
    "language": "🌐",
}
TAB_LABELS: dict[str, str] = {
    "tickets": "setup.panel.tab.tickets",
    "welcome": "setup.panel.tab.welcome",
    "goodbye": "setup.panel.tab.goodbye",
    "log": "setup.panel.tab.log",
    "language": "setup.panel.tab.language",
}


class SetupPanelView(discord.ui.View):
    """Persistent setup panel view (timeout=None, static custom_ids) with Tab Bar layout."""

    def __init__(
        self,
        current_module: str = "tickets",
        guild_id: str | None = None,
        *,
        module: str | None = None,
    ) -> None:
        super().__init__(timeout=None)

        # Disambiguate arguments: e.g. SetupPanelView("123456789")
        if current_module not in TAB_MODULES and (current_module.isdigit() or guild_id is None):
            guild_id = current_module
            current_module = "tickets"
        if module is not None:
            current_module = module
        if current_module not in TAB_MODULES:
            current_module = "tickets"

        self.current_module: str = current_module
        gid = guild_id or "0"

        # 1. Configure Row 0 Tab Buttons & Row 1 Action Buttons
        for child in list(self.children):
            self._configure_child(child, gid)

        # 2. Add contextual components for non-ticket modules
        if self.current_module != "tickets":
            mod = MODULES.get(self.current_module)
            if mod is not None:
                for item in mod.components(gid):
                    self._bind_contextual_item(item)
                    self.add_item(item)

    def _configure_child(self, child: discord.ui.Item, gid: str) -> None:
        cid = getattr(child, "custom_id", None)
        if not cid:
            return
        if cid.startswith("setup:tab:"):
            tab_name = cid.split(":")[-1]
            is_active = tab_name == self.current_module
            if isinstance(child, discord.ui.Button):
                child.style = discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary
                child.disabled = is_active
                key = TAB_LABELS.get(tab_name)
                if key:
                    child.label = t(gid, key)
                child.emoji = TAB_EMOJIS.get(tab_name, child.emoji)
                child.row = 0
        elif cid == "setup:refresh" and isinstance(child, discord.ui.Button):
            child.label = t(gid, "setup.panel.refresh_button")
            child.row = 1
        elif cid == "setup:close" and isinstance(child, discord.ui.Button):
            child.label = t(gid, "setup.panel.close_button")
            child.row = 1
        elif cid.startswith("setup:tickets:"):
            self._configure_ticket_child(child, cid, gid)

    def _configure_ticket_child(self, child: discord.ui.Item, cid: str, gid: str) -> None:
        if self.current_module != "tickets":
            self.remove_item(child)
            return
        if not isinstance(child, discord.ui.Button):
            return
        child.row = 2
        label_keys = {
            "setup:tickets:create_category": "setup.module.tickets.create_button",
            "setup:tickets:delete_category": "setup.module.tickets.delete_button",
            "setup:tickets:list_categories": "setup.module.tickets.list_button",
            "setup:tickets:configure_fields": "setup.module.tickets.fields_button",
        }
        if cid in label_keys:
            child.label = t(gid, label_keys[cid])

    def _bind_contextual_item(self, item: discord.ui.Item) -> None:
        cid = getattr(item, "custom_id", None)
        if not cid or not cid.startswith("setup:"):
            return
        parts = cid.split(":")
        if len(parts) >= 3:
            mod_key = parts[1]
            act = parts[2]
            existing_cb = getattr(item, "callback", None)
            if existing_cb is None or getattr(existing_cb, "__qualname__", "").endswith("callback"):

                async def _item_cb(interaction: discord.Interaction, m=mod_key, a=act) -> None:
                    module = MODULES.get(m)
                    if module is not None:
                        await module.handle(interaction, a)

                item.callback = _item_cb  # type: ignore[method-assign]

    # ------------------------------------------------------------------
    # Tab Bar Buttons — Row 0 (5 tabs)
    # ------------------------------------------------------------------
    @discord.ui.button(
        label=t(None, "setup.panel.tab.tickets"),
        emoji="🎫",
        custom_id="setup:tab:tickets",
        row=0,
    )
    async def tab_tickets(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await self._switch_tab(interaction, "tickets")

    @discord.ui.button(
        label=t(None, "setup.panel.tab.welcome"),
        emoji="👋",
        custom_id="setup:tab:welcome",
        row=0,
    )
    async def tab_welcome(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await self._switch_tab(interaction, "welcome")

    @discord.ui.button(
        label=t(None, "setup.panel.tab.goodbye"),
        emoji="🚪",
        custom_id="setup:tab:goodbye",
        row=0,
    )
    async def tab_goodbye(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await self._switch_tab(interaction, "goodbye")

    @discord.ui.button(
        label=t(None, "setup.panel.tab.log"),
        emoji="📜",
        custom_id="setup:tab:log",
        row=0,
    )
    async def tab_log(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await self._switch_tab(interaction, "log")

    @discord.ui.button(
        label=t(None, "setup.panel.tab.language"),
        emoji="🌐",
        custom_id="setup:tab:language",
        row=0,
    )
    async def tab_language(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await self._switch_tab(interaction, "language")

    async def _switch_tab(self, interaction: discord.Interaction, chosen_tab: str) -> None:
        guild = interaction.guild
        guild_id = str(guild.id) if guild else "0"
        bot = getattr(interaction, "client", None) or _get_setup_bot()
        if chosen_tab not in TAB_MODULES:
            chosen_tab = "tickets"
        embed = await _build_embed(guild_id, chosen_tab, bot=bot)
        new_view = SetupPanelView(current_module=chosen_tab, guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    # ------------------------------------------------------------------
    # Refresh — custom_id setup:refresh
    # ------------------------------------------------------------------
    @discord.ui.button(
        label=t(None, "setup.panel.refresh_button"),
        style=discord.ButtonStyle.secondary,
        custom_id="setup:refresh",
        emoji="🔄",
        row=1,
    )
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        guild = interaction.guild
        guild_id = str(guild.id) if guild else "0"
        bot = getattr(interaction, "client", None) or _get_setup_bot()
        current = getattr(self, "current_module", "tickets") or "tickets"
        try:
            msg = getattr(interaction, "message", None)
            embeds = getattr(msg, "embeds", []) if msg else []
            embed0 = embeds[0] if embeds else None
            footer_text = getattr(getattr(embed0, "footer", None), "text", None) or ""
            if "nbpanel|module=" in footer_text:
                parsed = _parse_module_from_footer(embed0)
                if parsed in TAB_MODULES:
                    current = parsed
        except Exception:  # noqa: BLE001, S110
            pass

        if bot is not None:
            if current in ("log", "language") and hasattr(bot, "guild_service") and bot.guild_service is not None:
                try:
                    await bot.guild_service.get_config(guild_id)
                except Exception:
                    logger.debug("Refresh get_config failed", exc_info=True)
            elif (
                current in ("welcome", "goodbye")
                and hasattr(bot, "greeting_service")
                and bot.greeting_service is not None
            ):
                try:
                    await bot.greeting_service.get_config(guild_id)
                except Exception:
                    logger.debug("Refresh get_config failed", exc_info=True)
            elif current == "tickets" and hasattr(bot, "db") and bot.db is not None:
                try:
                    await bot.db.get_ticket_categories(guild_id)
                except Exception:
                    logger.debug("Refresh get_ticket_categories failed", exc_info=True)

        embed = await _build_embed(guild_id, current, bot=bot)
        new_view = SetupPanelView(current_module=current, guild_id=guild_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    # ------------------------------------------------------------------
    # Close — custom_id setup:close
    # ------------------------------------------------------------------
    @discord.ui.button(
        label=t(None, "setup.panel.close_button"),
        style=discord.ButtonStyle.danger,
        custom_id="setup:close",
        emoji="🗑️",
        row=1,
    )
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        # Delete the panel message
        try:
            msg = getattr(interaction, "message", None)
            if msg is not None and hasattr(msg, "delete"):
                await msg.delete()
            elif hasattr(interaction, "message") and interaction.message is not None:
                await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            logger.exception("Failed to delete setup panel message")
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:  # noqa: BLE001, S110
            pass

    # ------------------------------------------------------------------
    # Tickets module actions — setup:tickets:{action}
    # ------------------------------------------------------------------
    @discord.ui.button(
        label=t(None, "setup.module.tickets.create_button"),
        style=discord.ButtonStyle.primary,
        custom_id="setup:tickets:create_category",
        row=2,
    )
    async def tickets_create_category(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        mod = MODULES.get("tickets")
        if mod is None:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "common.error.title"),
                    t(guild_id, "setup.panel.error_module_not_loaded", module="tickets"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await mod.handle(interaction, "create_category")

    @discord.ui.button(
        label=t(None, "setup.module.tickets.delete_button"),
        style=discord.ButtonStyle.danger,
        custom_id="setup:tickets:delete_category",
        row=2,
    )
    async def tickets_delete_category(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        mod = MODULES.get("tickets")
        if mod is None:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "common.error.title"),
                    t(guild_id, "setup.panel.error_module_not_loaded", module="tickets"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await mod.handle(interaction, "delete_category")

    @discord.ui.button(
        label=t(None, "setup.module.tickets.list_button"),
        style=discord.ButtonStyle.secondary,
        custom_id="setup:tickets:list_categories",
        row=2,
    )
    async def tickets_list_categories(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        mod = MODULES.get("tickets")
        if mod is None:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "common.error.title"),
                    t(guild_id, "setup.panel.error_module_not_loaded", module="tickets"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await mod.handle(interaction, "list_categories")

    @discord.ui.button(
        label=t(None, "setup.module.tickets.fields_button"),
        style=discord.ButtonStyle.secondary,
        custom_id="setup:tickets:configure_fields",
        row=2,
    )
    async def tickets_configure_fields(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        mod = MODULES.get("tickets")
        if mod is None:
            guild_id = str(interaction.guild.id) if interaction.guild else None
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "common.error.title"),
                    t(guild_id, "setup.panel.error_module_not_loaded", module="tickets"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
            return
        await mod.handle(interaction, "configure_fields")

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:  # noqa: C901
        # Admin always passes
        try:
            if getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False):
                return True
        except Exception:  # noqa: BLE001, S110
            pass

        # Determine required permission from custom_id or footer module
        custom_id: str | None = None
        try:
            custom_id = getattr(interaction.data, "get", lambda k, d=None: None)("custom_id")  # noqa: ARG005, PGH003
            if custom_id is None:
                # interaction.data is dict
                data = getattr(interaction, "data", {}) or {}
                custom_id = data.get("custom_id") if isinstance(data, dict) else getattr(data, "custom_id", None)
        except Exception:  # noqa: BLE001
            custom_id = None
        if custom_id is None:
            # Try to infer from interaction's component
            try:
                custom_id = getattr(interaction, "custom_id", None)  # noqa: PGH003
            except Exception:  # noqa: BLE001
                custom_id = None

        permission: str | None = None
        if custom_id and custom_id.startswith("setup:"):
            parts = custom_id.split(":")
            # setup:nav, setup:refresh, setup:close are generic
            if len(parts) == 2:
                # generic panel action — allow any module permission or deny? For nav/refresh/close, allow broader
                # For S2a, only tickets.manage exists; check tickets.manage as generic gate
                permission = None  # will check any module permission
            elif len(parts) == 3 and parts[1] == "tab":
                module_key = parts[2]
                mod = MODULES.get(module_key)
                if mod is not None:
                    permission = getattr(mod, "permission_key", None)
                elif module_key in ("welcome", "goodbye"):
                    permission = "greeting.manage"
                else:
                    permission = "tickets.manage"
            elif len(parts) >= 3:
                module_key = parts[1]
                mod = MODULES.get(module_key)
                if mod is not None:
                    permission = getattr(mod, "permission_key", None)
                else:
                    # Fallback mapping
                    if module_key in ("tickets", "log", "language"):
                        permission = "tickets.manage"
                    elif module_key in ("welcome", "goodbye"):
                        permission = "greeting.manage"
                    else:
                        permission = None
        else:
            # Fallback: infer from footer module token
            try:
                msg = getattr(interaction, "message", None)
                embeds = getattr(msg, "embeds", []) if msg else []
                embed0 = embeds[0] if embeds else None
                module_key = _parse_module_from_footer(embed0)
                mod = MODULES.get(module_key)
                if mod is not None:
                    permission = getattr(mod, "permission_key", None)
            except Exception:  # noqa: BLE001
                permission = None

        guild = getattr(interaction, "guild", None)
        guild_id = str(getattr(guild, "id", "0")) if guild is not None else None
        member = getattr(interaction, "user", None)

        # If no specific permission, check any module permission (tickets.manage or greeting.manage)
        # For generic actions, allow if user has ANY module permission
        if permission is None:
            # Check tickets.manage then greeting.manage
            for perm in ("tickets.manage", "greeting.manage"):
                try:
                    if await can_member(perm, member, guild_id):
                        return True
                except Exception:  # noqa: BLE001, S112
                    continue
            # No grant → deny
            try:
                await interaction.response.send_message(
                    embed=error_embed(
                        t(guild_id, "setup.panel.error_denied_title"),
                        t(guild_id, "setup.panel.error_denied_description"),
                        guild_id=guild_id,
                    ),
                    ephemeral=True,
                )
            except Exception:
                logger.exception("Failed to send denied ephemeral")
            return False

        # Specific permission check
        try:
            allowed = await can_member(permission, member, guild_id)
        except Exception:  # noqa: BLE001
            allowed = False
        if allowed:
            return True

        try:
            await interaction.response.send_message(
                embed=error_embed(
                    t(guild_id, "setup.panel.error_denied_title"),
                    t(guild_id, "setup.panel.error_denied_description"),
                    guild_id=guild_id,
                ),
                ephemeral=True,
            )
        except Exception:
            logger.exception("Failed to send denied ephemeral")
        return False


# Register setup modules on import (avoid circular: import after MODULES definition)
def _register_module(import_path: str, class_name: str, key: str) -> None:
    try:
        mod = __import__(import_path, fromlist=[class_name])
        cls = getattr(mod, class_name)
        if key not in MODULES:
            MODULES[key] = cls()  # noqa: PGH003
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s module not yet available for auto-registration: %s", key, exc)


_register_module("bot.views.setup_modules.tickets", "TicketSetupModule", "tickets")
_register_module("bot.views.setup_modules.welcome", "WelcomeSetupModule", "welcome")
_register_module("bot.views.setup_modules.goodbye", "GoodbyeSetupModule", "goodbye")
_register_module("bot.views.setup_modules.log", "LogSetupModule", "log")
_register_module("bot.views.setup_modules.language", "LanguageSetupModule", "language")
