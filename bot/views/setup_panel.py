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


async def _build_embed(guild_id: str, module_key: str, bot: typing.Any | None = None) -> discord.Embed:
    """Build panel embed for module_key, recomputing from services cache-first."""
    b = bot or _get_setup_bot()
    # Try module render
    mod = MODULES.get(module_key)
    embed: discord.Embed | None = None
    if mod is not None:
        # Prefer async render_async if available
        try:
            if hasattr(mod, "render_async"):
                embed = await mod.render_async(guild_id, bot=b)  # ty:ignore[call-non-callable]
            else:
                # sync render may still be callable
                res = mod.render(guild_id)
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


class SetupPanelView(discord.ui.View):
    """Persistent setup panel view (timeout=None, static custom_ids)."""

    def __init__(self, guild_id: str | None = None) -> None:
        super().__init__(timeout=None)
        # Localize static labels via t() for i18n coverage (persistent view uses guild_id or default)
        gid = guild_id or "0"
        for child in self.children:
            cid = getattr(child, "custom_id", None)
            if cid == "setup:nav" and isinstance(child, discord.ui.Select):
                child.placeholder = t(gid, "setup.panel.select_placeholder")
                # Localize options
                for opt in child.options:
                    key = f"setup.panel.option.{opt.value}"
                    localized = t(gid, key)
                    if localized != key:
                        opt.label = localized
            elif cid == "setup:refresh" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.panel.refresh_button")
            elif cid == "setup:close" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.panel.close_button")
            elif cid == "setup:tickets:create_category" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.module.tickets.create_button")
            elif cid == "setup:tickets:delete_category" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.module.tickets.delete_button")
            elif cid == "setup:tickets:list_categories" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.module.tickets.list_button")
            elif cid == "setup:tickets:configure_fields" and isinstance(child, discord.ui.Button):
                child.label = t(gid, "setup.module.tickets.fields_button")

        # Attach the per-kind template pickers from the registered greeting
        # modules (welcome/goodbye) so the runtime panel exposes and routes
        # them. Each select keeps its module-bound callback (persistent
        # custom_id; greeting.manage gate enforced by module handler + panel
        # interaction_check). One full-width select per module row.
        for module_key in ("welcome", "goodbye"):
            mod = MODULES.get(module_key)
            if mod is None:
                continue
            for item in mod.components(gid):
                cid = getattr(item, "custom_id", None)
                if cid in _TEMPLATE_SELECT_IDS and cid not in {getattr(c, "custom_id", None) for c in self.children}:
                    self.add_item(item)

    # ------------------------------------------------------------------
    # Navigation Select — custom_id setup:nav
    # ------------------------------------------------------------------
    @discord.ui.select(
        custom_id="setup:nav",
        placeholder=t(None, "setup.panel.select_placeholder"),
        options=[
            discord.SelectOption(label=t(None, "setup.panel.option.tickets"), value="tickets", emoji="🎫"),
            discord.SelectOption(label=t(None, "setup.panel.option.welcome"), value="welcome", emoji="👋"),
            discord.SelectOption(label=t(None, "setup.panel.option.goodbye"), value="goodbye", emoji="👋"),
            discord.SelectOption(label=t(None, "setup.panel.option.log"), value="log", emoji="📝"),
            discord.SelectOption(label=t(None, "setup.panel.option.language"), value="language", emoji="🌐"),
        ],
    )
    async def nav_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        guild = interaction.guild
        guild_id = str(guild.id) if guild else "0"
        bot = getattr(interaction, "client", None)
        # Prefer interaction.data values (Discord payload) over select.values for testability
        chosen = "tickets"
        try:
            data = getattr(interaction, "data", None)
            if isinstance(data, dict):
                vals = data.get("values") or []
                if vals:
                    chosen = vals[0]
                elif getattr(select, "values", None):
                    chosen = select.values[0]
            elif getattr(select, "values", None):
                # Fallback to select.values when data not dict
                if select.values:
                    chosen = select.values[0]
        except Exception:  # noqa: BLE001
            chosen = "tickets"
        # Validate chosen is known module; fallback to tickets
        if chosen not in ("tickets", "welcome", "goodbye", "log", "language"):
            chosen = "tickets"
        embed = await _build_embed(guild_id, chosen, bot=bot)
        # Recompute labels for module components? Keep view as is; just edit message
        await interaction.response.edit_message(embed=embed, view=self)

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
        bot = getattr(interaction, "client", None)
        # Determine current module from footer token (survives restart)
        current = "tickets"
        try:
            msg = getattr(interaction, "message", None)
            embeds = getattr(msg, "embeds", []) if msg else []
            embed0 = embeds[0] if embeds else None
            current = _parse_module_from_footer(embed0)
        except Exception:  # noqa: BLE001
            current = "tickets"
        # Re-read live state: trigger cache-first reads before rebuild
        if bot is not None:
            try:
                if hasattr(bot, "guild_service") and bot.guild_service is not None:
                    await bot.guild_service.get_config(guild_id)
            except Exception:
                logger.debug("Refresh get_config failed", exc_info=True)
            try:
                if hasattr(bot, "db") and bot.db is not None:
                    # Tickets live state
                    await bot.db.get_ticket_categories(guild_id)
            except Exception:
                logger.debug("Refresh get_ticket_categories failed", exc_info=True)
        embed = await _build_embed(guild_id, current, bot=bot)
        await interaction.response.edit_message(embed=embed, view=self)

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
            else:
                # Fallback: try interaction.message
                await interaction.message.delete()  # ty:ignore[unresolved-attribute]
        except discord.NotFound:
            pass
        except Exception:
            logger.exception("Failed to delete setup panel message")
        # Acknowledge if not already responded? Message delete is enough; try to defer if needed
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
            elif len(parts) == 3:
                module_key = parts[1]
                mod = MODULES.get(module_key)
                if mod is not None:
                    permission = getattr(mod, "permission_key", None)
                else:
                    # Fallback mapping
                    if module_key == "tickets":
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
