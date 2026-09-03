"""Shared template-picker machinery for the greeting setup modules.

Extracted from the welcome/goodbye twin implementations to satisfy the
jscpd ``bot/`` duplication budget (PR #97 quality-reports gate). The
welcome and goodbye modules stay thin kind-specific glue; everything
invariant across both kinds lives here:

- picker construction (persistent StringSelect over ``TEMPLATE_REGISTRY``)
- the ephemeral refresh view (never ``view=None``)
- the select-handling flow (permission gate, payload read, persist,
  panel refresh, confirmation)
- the preview flow (defer, config, channel resolution, renderer call
  with ``template_id=resolved`` / ``theme_id=resolved``)

Static ``custom_id`` values and the persistent registration contract are
unchanged; restart routing still uses the panel's static ids.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import typing

import discord

from bot.core.i18n import t
from bot.services.greeting_renderer import TEMPLATE_REGISTRY
from bot.services.greeting_service import _resolve_avatar_url  # noqa: PLC0415  # DRY: single definition
from bot.utils.brand import INFO  # noqa: F401  # re-export parity with module files
from bot.utils.checks import can_member
from bot.utils.embeds import error_embed, success_embed

logger = logging.getLogger(__name__)

PickerKind = typing.Literal["welcome", "goodbye"]


def select_custom_id(kind: str) -> str:
    """Return the static persistent custom_id for ``kind``."""
    return f"setup:{kind}:select_template"


def _resolve_guild_icon_url(guild: discord.Guild | None) -> str | None:
    if guild is None:
        return None
    try:
        icon = guild.icon
        return str(icon.url) if icon is not None else None
    except Exception:  # noqa: BLE001
        return None


def _format_template(template: str, user: typing.Any, guild: discord.Guild | None = None) -> str:
    try:
        guild_name = guild.name if guild is not None else ""
        mention = getattr(user, "mention", "")
        return template.format(mention=mention, user=mention, server=guild_name)
    except Exception:  # noqa: BLE001
        return template


def build_template_select(guild_id: str, kind: PickerKind) -> discord.ui.Select:
    """Persistent StringSelect offering the four registry templates via t()."""
    select = discord.ui.Select(
        custom_id=select_custom_id(kind),
        placeholder=t(guild_id, f"setup.module.{kind}.template_placeholder"),
        min_values=1,
        max_values=1,
    )
    for template_id in TEMPLATE_REGISTRY:
        select.add_option(
            label=t(guild_id, f"templates.greeting.{template_id}.label"),
            description=t(guild_id, f"templates.greeting.{template_id}.description"),
            value=template_id,
        )
    return select


class TemplateRefreshView(discord.ui.View):
    """Ephemeral one-item view that re-renders the picker after a selection.

    Carries the rebound template select so the panel message keeps its
    controls after ``edit_message`` (never ``view=None``). Not persistent —
    restart routing uses the panel's static custom_ids instead.
    """

    def __init__(self, select: discord.ui.Select) -> None:
        super().__init__(timeout=180)
        self.add_item(select)


async def _send_guild_only(interaction: discord.Interaction, kind: str) -> None:
    p = f"setup.module.{kind}"
    await interaction.response.send_message(
        embed=error_embed(t(None, f"{p}.error_guild_only_title"), t(None, f"{p}.error_guild_only_description")),
        ephemeral=True,
    )


async def _send_bot_unavailable(interaction: discord.Interaction, kind: str, guild_id: str) -> None:
    p = f"setup.module.{kind}"
    await interaction.response.send_message(
        embed=error_embed(
            t(guild_id, f"{p}.error_title"),
            t(guild_id, f"{p}.error_bot_unavailable"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


async def _send_denied(interaction: discord.Interaction, guild_id: str) -> None:
    await interaction.response.send_message(
        embed=error_embed(
            t(guild_id, "setup.panel.error_denied_title"),
            t(guild_id, "setup.panel.error_denied_description"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


async def _send_unknown_action(interaction: discord.Interaction, kind: str, guild_id: str, action: str) -> None:
    p = f"setup.module.{kind}"
    await interaction.response.send_message(
        embed=error_embed(
            t(guild_id, f"{p}.error_title"),
            t(guild_id, f"{p}.unknown_action", action=action),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


async def _send_preview_error(interaction: discord.Interaction, kind: str, guild_id: str | None) -> None:
    p = f"setup.module.{kind}"
    await interaction.followup.send(
        embed=error_embed(
            t(guild_id, f"{p}.preview_error_title") if guild_id else t(None, f"{p}.preview_error_title"),
            t(guild_id, f"{p}.preview_error_description") if guild_id else t(None, f"{p}.preview_error_description"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


async def _send_preview_no_channel(interaction: discord.Interaction, kind: str, guild_id: str) -> None:
    p = f"setup.module.{kind}"
    await interaction.followup.send(
        embed=error_embed(
            t(guild_id, f"{p}.preview_no_channel_title"),
            t(guild_id, f"{p}.preview_no_channel_description"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


def _read_template_value(interaction: discord.Interaction) -> str | None:
    data = getattr(interaction, "data", None)
    if isinstance(data, dict):
        vals = data.get("values") or []
        if vals:
            return str(vals[0])
    return None


def resolve_template(kind: PickerKind, cfg: typing.Any) -> str:
    """Resolved per-kind template id (templateId → themeId → default chain)."""
    try:
        from bot.services.greeting_service import select_template  # noqa: PLC0415 -- cycle-break

        return select_template(cfg, kind)
    except Exception:  # noqa: BLE001
        return getattr(cfg, f"{kind}_template_id", None) or getattr(cfg, "theme_id", None) or "default"


async def handle_template_select_flow(
    module: typing.Any,
    interaction: discord.Interaction,
    kind: PickerKind,
    *,
    persist: typing.Callable[..., typing.Awaitable[None]],
) -> None:
    """Shared select-handling flow for welcome/goodbye pickers.

    ``module`` supplies ``_resolve_bot``, ``render_async`` and
    ``_on_template_select``; ``persist`` persists the picked template id
    (module-specific ``set_*_template_id``).
    """
    guild = interaction.guild
    if guild is None:
        await _send_guild_only(interaction, kind)
        return
    guild_id = str(guild.id)
    bot = module._resolve_bot(interaction)
    if bot is None or getattr(bot, "greeting_service", None) is None:
        await _send_bot_unavailable(interaction, kind, guild_id)
        return
    # Permission gate: greeting.manage only (no new matrix key).
    user = interaction.user
    if not getattr(getattr(user, "guild_permissions", None), "administrator", False):
        try:
            allowed = await can_member("greeting.manage", user, guild_id)
        except Exception:  # noqa: BLE001
            allowed = False
        if not allowed:
            await _send_denied(interaction, guild_id)
            return
    template_id = _read_template_value(interaction)
    if template_id is None:
        await _send_unknown_action(interaction, kind, guild_id, "select_template")
        return
    await persist(guild_id, template_id, bot)
    embed = await module.render_async(guild_id, bot=bot)
    # Re-render the picker with the current label; never pass view=None —
    # discord.py serializes it as components: [] and strips every control
    # from the panel message (verify-report CRITICAL #1 probe 2).
    select = build_template_select(guild_id, kind)
    select.callback = module._on_template_select
    await interaction.response.edit_message(embed=embed, view=TemplateRefreshView(select))
    p = f"setup.module.{kind}"
    await interaction.followup.send(
        embed=success_embed(
            t(guild_id, f"{p}.template_select_title"),
            t(guild_id, f"{p}.template_select_description"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )


async def handle_preview_flow(
    module: typing.Any,
    interaction: discord.Interaction,
    kind: PickerKind,
) -> None:
    """Shared preview/test flow for welcome/goodbye modules.

    Mirrors the legacy dispatch path: defer → config → channel →
    renderer via to_thread (resolved per-kind template) → deliver
    content/card per card_enabled.
    """
    guild = interaction.guild
    if guild is None:
        await _send_preview_error(interaction, kind, None)
        return
    guild_id = str(guild.id)
    bot = module._resolve_bot(interaction)
    if bot is None:
        await _send_preview_error(interaction, kind, None)
        return
    with contextlib.suppress(Exception):  # noqa: BLE001
        await interaction.response.defer(ephemeral=True)
    try:
        cfg = await bot.greeting_service.get_config(guild_id)
    except Exception:  # noqa: BLE001
        logger.exception("%s preview get_config failed", kind)
        await _send_preview_error(interaction, kind, guild_id)
        return
    channel_id = getattr(cfg, f"{kind}_channel_id", None)
    if not channel_id:
        await _send_preview_no_channel(interaction, kind, guild_id)
        return
    try:
        channel = guild.get_channel(int(channel_id))
    except Exception:  # noqa: BLE001
        channel = None
    if channel is None:
        await _send_preview_no_channel(interaction, kind, guild_id)
        return
    try:
        render_fn = bot.greeting_service.resolve_renderer()
    except Exception:  # noqa: BLE001
        logger.exception("%s preview resolve_renderer failed", kind)
        await _send_preview_error(interaction, kind, guild_id)
        return
    user = interaction.user
    member_count = getattr(guild, "member_count", 0) or 0
    try:
        buffer: io.BytesIO = await asyncio.to_thread(
            render_fn,
            username=getattr(user, "display_name", str(user)),
            avatar_url=_resolve_avatar_url(user),
            guild_name=getattr(guild, "name", ""),
            member_count=member_count,
            guild_icon_url=_resolve_guild_icon_url(guild),
            greeting_title=t(guild_id, f"greetings.card.{kind}_title"),
            member_count_text=t(guild_id, "greetings.card.member_count", count=member_count),
            card_type=kind,
            template_id=resolve_template(kind, cfg),
            # theme_id receives the SAME resolved id (legacy alias per
            # setup-panel spec: preview forwards template_id=resolved,
            # theme_id=resolved — never the raw config value).
            theme_id=resolve_template(kind, cfg),
        )
    except Exception:  # noqa: BLE001
        logger.exception("%s preview render failed", kind)
        await _send_preview_error(interaction, kind, guild_id)
        return
    content: str | None = None
    try:
        tmpl = getattr(cfg, f"{kind}_message", None)
        if tmpl:
            content = _format_template(tmpl, user, guild)
    except Exception:  # noqa: BLE001
        content = None
    try:
        if getattr(cfg, f"{kind}_card_enabled", False):
            file = discord.File(buffer, filename=f"{kind}.png")
            await channel.send(content=content or None, file=file)  # type: ignore[union-attr]
        else:
            if content and content.strip():
                await channel.send(content=content)  # type: ignore[union-attr]
            else:
                await channel.send(content=content or None)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        logger.exception("%s preview channel send failed", kind)
        await _send_preview_error(interaction, kind, guild_id)
        return
    await interaction.followup.send(
        embed=success_embed(
            t(guild_id, f"setup.module.{kind}.preview_success_title"),
            t(guild_id, f"setup.module.{kind}.preview_success_description", channel=f"<#{channel_id}>"),
            guild_id=guild_id,
        ),
        ephemeral=True,
    )
