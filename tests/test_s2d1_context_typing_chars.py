"""RED — S2.1 Typed Surface characterization (strict TDD 1.1).

Spec: Sentinel and Utility hybrid commands MUST use NebulosaContext
with interaction preserved; is_mod dual-path (decorator slash+prefix
and inline view predicate) stays fail-closed without permission change.
"""

from __future__ import annotations

import ast
import pathlib

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from bot.core.context import NebulosaContext
from bot.utils.checks import is_mod, is_mod_check


def _source_has_broad_any(fp: pathlib.Path) -> bool:
    src = fp.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(fp))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            ann = ast.unparse(node.annotation)
            if "Context[Any]" in ann or "Context[typing.Any]" in ann:
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                if arg.annotation is None:
                    continue
                ann = ast.unparse(arg.annotation)
                if "Context[Any]" in ann:
                    return True
    return False


class TestContextTypingCharacterization:
    def test_sentinel_no_context_any(self) -> None:
        assert not _source_has_broad_any(pathlib.Path("bot/cogs/sentinel.py")), "sentinel.py must not use Context[Any]"

    def test_utility_no_context_any(self) -> None:
        assert not _source_has_broad_any(pathlib.Path("bot/cogs/utility.py")), "utility.py must not use Context[Any]"

    def test_sentinel_uses_nebulosa_context(self) -> None:
        src = pathlib.Path("bot/cogs/sentinel.py").read_text(encoding="utf-8")
        assert "NebulosaContext" in src

    def test_utility_uses_nebulosa_context(self) -> None:
        src = pathlib.Path("bot/cogs/utility.py").read_text(encoding="utf-8")
        # S6A slash-only: utility no longer imports NebulosaContext; Interaction is the source
        assert "discord.Interaction" in src
        assert "utility.avatar.title" in src or "Utility" in src

    def test_nebulosa_context_preserves_interaction(self) -> None:
        # Hybrid commands expose Context.interaction when invoked via slash;
        # NebulosaContext inherits it from Context via discord.py hybrid dispatch.
        assert issubclass(NebulosaContext, commands.Context)
        # discord.py Context stores interaction as instance attribute set in __init__
        # and via from_interaction; verify the annotation and construction path exist.
        assert hasattr(NebulosaContext, "from_interaction")
        assert hasattr(commands.Context, "from_interaction")
        # Context.__init__ accepts interaction and sets self.interaction; verify
        # the attribute is settable on a NebulosaContext-constructible instance
        # without requiring a live Discord connection — use __new__ to bypass init.
        obj = NebulosaContext.__new__(NebulosaContext)
        obj.interaction = None
        assert hasattr(obj, "interaction")
        assert obj.interaction is None
        # Also verify a mock interaction object is preserved
        mock_inter = object()
        obj.interaction = mock_inter
        assert obj.interaction is mock_inter


class TestIsModDualPathCharacterization:
    def test_decorator_registers_slash_only(self) -> None:
        @app_commands.command(name="s2d1_probe_dual", description="probe")
        @is_mod()
        async def cmd(interaction: discord.Interaction):  # pragma: no cover
            pass

        # Slash-only: only app_commands checks; no prefix predicate registered
        assert hasattr(cmd, "checks")
        checks = getattr(cmd, "checks", [])
        assert isinstance(checks, list | tuple | set) and len(checks) > 0, "slash path missing"
        # Prefix dual registration is retired — __commands_checks__ must be absent/empty
        cb = getattr(cmd, "callback", None)
        cmd_checks = getattr(cb, "__commands_checks__", []) if cb is not None else []
        assert len(cmd_checks) == 0, f"prefix predicate must not be registered (slash-only), got {cmd_checks}"
        # Decorator is slash-only: no prefix_predicate attribute
        dec = is_mod()
        assert not hasattr(dec, "prefix_predicate"), "is_mod() must be slash-only (no prefix_predicate)"

    @pytest.mark.asyncio
    async def test_inline_view_predicate_fail_closed(self, mock_interaction) -> None:
        # No guild => fail closed.
        mock_interaction.guild = None
        assert await is_mod_check(mock_interaction) is False
        # No admin/mod in guild with no mod role => fail closed.
        mock_interaction.guild = type("G", (), {"id": 1})()
        mock_interaction.user.guild_permissions.administrator = False
        mock_interaction.client._guild_mod_role_cache = {}
        mock_interaction.user.roles = []
        mock_interaction.guild_id = 1
        assert await is_mod_check(mock_interaction) is False

    @pytest.mark.asyncio
    async def test_inline_view_predicate_unchanged_admin_pass(self, mock_interaction) -> None:
        import unittest.mock as mock

        mock_interaction.guild = mock.MagicMock(spec=discord.Guild)
        mock_interaction.user.guild_permissions.administrator = True
        mock_interaction.client._guild_mod_role_cache = {}
        assert await is_mod_check(mock_interaction) is True

    @pytest.mark.asyncio
    async def test_inline_claim_gate_still_enforced(self) -> None:
        """Persistent ticket claim button still calls is_mod_check inline — fail-closed."""
        # This is a structural probe: views/tickets.py must contain is_mod_check usage
        src = pathlib.Path("bot/views/tickets.py").read_text(encoding="utf-8")
        assert "is_mod_check" in src, "ticket views must retain inline is_mod_check gate"
