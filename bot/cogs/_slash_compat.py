"""Compatibility shim for S6 slash-only migration.

Provides interaction→context adaptation so existing Context-based flows and
tests (MagicMock spec=commands.Context with .send) remain green while
production uses discord.Interaction.

The helper _has_explicit avoids MagicMock's auto-creation pitfall by
inspecting __dict__/_mock_children instead of hasattr.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

logger = logging.getLogger(__name__)


def _has_explicit(obj: Any, name: str) -> bool:
    """Return True if *name* was explicitly set on *obj* (not MagicMock auto)."""
    if name in getattr(obj, "__dict__", {}):
        return True
    mc = getattr(obj, "_mock_children", None)
    if isinstance(mc, dict) and name in mc:
        return True
    # For non-mock objects, fallback to hasattr but avoid creating
    try:
        # Use object's own __getattribute__ without MagicMock's __getattr__
        object.__getattribute__(obj, name)
        # If we got here without MagicMock auto, it exists
        # For real objects, this suffices
        if not hasattr(obj, "_mock_children"):
            return True
    except AttributeError:
        return False
    # For MagicMocks without explicit child, object.__getattribute__ still
    # returns a MagicMock via __getattr__, so we must check _mock_children
    # already did. If not in _mock_children, it's auto.
    return False


def is_interaction_like(src: Any) -> bool:
    """Heuristic: src is an Interaction if it has explicit user+response."""
    has_user = _has_explicit(src, "user")
    has_response = _has_explicit(src, "response")
    # Real discord.Interaction always has both; mocks for ctx never have response
    if has_user and has_response:
        return True
    # Fallback: check spec
    spec = getattr(src, "_spec_class", None)
    if spec is not None:
        try:
            return issubclass(spec, discord.Interaction)
        except (AttributeError, TypeError):  # noqa: BLE001
            return False  # noqa: TRY300
    return False


def is_context_like(src: Any) -> bool:
    """Context-like has explicit send without response (covers author-less mocks)."""
    mc = getattr(src, "_mock_children", None)
    if isinstance(mc, dict):
        has_send = "send" in mc
        has_response = "response" in mc
        if has_send and not has_response:
            return True
        has_author = "author" in mc
        if has_author and has_send:
            return True
    # Fallback to explicit helper
    has_author = _has_explicit(src, "author")
    has_send = _has_explicit(src, "send")
    if has_author and has_send:
        return True
    spec = getattr(src, "_spec_class", None)
    if spec is not None:
        try:
            from discord.ext import commands  # noqa: PLC0415  # isort: skip -- cycle-breaking: compat shim avoids circular import via cogs  # noqa: PLC0415

            return issubclass(spec, commands.Context)
        except (AttributeError, TypeError):  # noqa: BLE001
            return False  # noqa: TRY300
    return False


class InteractionContext:
    """Minimal NebulosaContext-like shim wrapping an Interaction.

    Satisfies the subset used by flows: guild, author/user, channel,
    guild_config, interaction, bot, send, defer.
    """

    def __init__(self, interaction: discord.Interaction, bot: Any) -> None:
        self.interaction: discord.Interaction | None = interaction
        self.bot = bot
        self.guild = getattr(interaction, "guild", None)
        # interaction.user is Union[User, Member]; flows expect Member for is_mod
        self.author = getattr(interaction, "user", None)
        self.user = self.author
        self.channel = getattr(interaction, "channel", None)
        self.guild_config = None  # populated lazily by callers if needed

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        """Proxy to interaction.response / followup."""
        ephemeral = kwargs.pop("ephemeral", False)
        # Try followup if already responded
        resp = getattr(self.interaction, "response", None) if self.interaction else None
        is_done = False
        if resp is not None:
            try:
                is_done = bool(resp.is_done())
            except (AttributeError, TypeError, RuntimeError):  # noqa: BLE001
                is_done = False
        if is_done:
            followup = getattr(self.interaction, "followup", None) if self.interaction else None
            if followup is not None:
                return await followup.send(*args, ephemeral=ephemeral, **kwargs)
        if resp is not None:
            try:
                return await resp.send_message(*args, ephemeral=ephemeral, **kwargs)
            except Exception:
                # Fallback to followup on AlreadyResponded
                followup = getattr(self.interaction, "followup", None) if self.interaction else None
                if followup is not None:
                    return await followup.send(*args, ephemeral=ephemeral, **kwargs)
                raise
        # No response (should not happen)
        return None

    async def defer(self, *, ephemeral: bool = False) -> None:
        resp = getattr(self.interaction, "response", None) if self.interaction else None
        if resp is not None:
            try:
                if not bool(resp.is_done()):
                    await resp.defer(ephemeral=ephemeral)
            except (AttributeError, TypeError, RuntimeError):  # noqa: BLE001
                logger.debug("Interaction defer failed", exc_info=True)  # noqa: TRY400


def to_context(src: Any, bot: Any) -> Any:
    """Normalize src (Interaction or Context) to a Context-like object.

    If src is already context-like, return it as-is. If interaction-like,
    wrap it. Otherwise fallback to src.
    """
    if is_context_like(src):
        return src
    if is_interaction_like(src):
        return InteractionContext(src, bot)
    # Heuristic fallback: explicit author vs user/response distinguishes ctx from interaction
    if hasattr(src, "author") and hasattr(src, "send") and _has_explicit(src, "author"):  # noqa: SIM102
        return src
    if (
        hasattr(src, "user")
        and hasattr(src, "response")
        and (_has_explicit(src, "user") or _has_explicit(src, "response"))
    ):  # noqa: SIM102
        return InteractionContext(src, bot)
    return src


async def reply(src: Any, bot: Any, *args: Any, **kwargs: Any) -> Any:
    """Unified reply: works for both Context and Interaction."""
    ctx = to_context(src, bot)
    # If wrapped InteractionContext, its send already routes correctly
    send = getattr(ctx, "send", None)
    if callable(send):
        return await send(*args, **kwargs)
    # Fallback
    resp = getattr(src, "response", None)
    if resp is not None and hasattr(resp, "send_message"):
        ephemeral = kwargs.pop("ephemeral", False)
        return await resp.send_message(*args, ephemeral=ephemeral, **kwargs)
    msg = "No send path for src"
    raise RuntimeError(msg)
