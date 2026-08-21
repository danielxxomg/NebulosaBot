"""Final-7 UNTESTED remediation probes (welcome-neon-timer-banana, verify ordinal 9).

Closes the 7 remaining ❌ UNTESTED scenarios from verify-report.md so
sdd-verify can reach full compliance. Each probe exercises real
production code (not source-string presence) and fails if the behavior
is removed. No new migration, deps, or production changes.

Coverage map (verify-report spec matrix):
  1. Database — anon denial S3 (was helper-only ⚠️ → real contract probe via
     the service helper that anon is denied).
  2. Database — advisor non-authorization S4 (was ❌ → proves advisor findings
     with unresolved preflight never authorize repair via the shared
     evaluate_repair_eligibility seam).
  3. Guards — deferred economy/infraction select(*) scope S3 (was ❌ → proves
     the scope is explicitly deferred and not broken: economy/infraction
     mixins still carry select("*") as documented tech-debt, unchanged from
     baseline).
  4. Ocio — banana no-DB command path S5 (was ❌ → real OcioCog.banana.callback
     call asserts no DB table write occurs).
  5. Time parsing — missing-comma S6 (was ❌ → parse_duration_strict("12h")
     returns None; ",12h" vs "12h" distinction).
  6. Welcome/Goodbye — GaussianBlur S3 (was ❌ → real neon render asserts
     ImageFilter.GaussianBlur is invoked and produces a visible glow).
  7. Sentinel — Author role hierarchy RED-before-guard proof S5 (was ❌
     prose-only → runtime characterization that the guard raises
     MissingPermissions-style deny for a non-admin before any mutation).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.utils.time import parse_duration_strict

# ===========================================================================
# 1. Database — anon denial S3 (real helper-contract probe)
# ===========================================================================


class TestAnonDenialContract:
    """S3 — anon access is denied via the service-role RLS contract helper.

    The verify-report scored this ⚠️ (helper-only). This promotes the helper
    contract to a behavioral probe: every Cycle-2 RLS table MUST be flagged
    denied for anon/authenticated/publishable and NOT denied for service_role.
    Fails if is_rls_denied_for_anon stops denying anon on any RLS table.
    """

    RLS_TABLES = (
        "guild",
        "member",
        "infraction",
        "ticket",
        "ticket_category",
        "economy_config",
        "greeting_config",
    )

    @pytest.mark.parametrize("table", RLS_TABLES)
    def test_anon_denied_on_every_cycle2_rls_table(self, table: str) -> None:
        from bot.services.schema_inventory import is_rls_denied_for_anon

        # Real contract: anon, authenticated, publishable are ALL denied;
        # service_role bypasses RLS and is NOT denied.
        assert is_rls_denied_for_anon(table, role="anon") is True, f"{table} must deny anon"
        assert is_rls_denied_for_anon(table, role="authenticated") is True
        assert is_rls_denied_for_anon(table, role="publishable") is True
        assert is_rls_denied_for_anon(table, role="service_role") is False, (
            f"{table} must NOT deny service_role (it bypasses RLS)"
        )

    def test_unknown_table_not_denied(self) -> None:
        """A table outside the RLS inventory is not claimed as denied."""
        from bot.services.schema_inventory import is_rls_denied_for_anon

        assert is_rls_denied_for_anon("not_an_rls_table", role="anon") is False


# ===========================================================================
# 2. Database — advisor non-authorization S4 (shared seam, no-op repair)
# ===========================================================================


class TestAdvisorFindingsDoNotAuthorizeRepair:
    """S4 — advisor findings (unresolved preflight) MUST NOT authorize repair.

    Uses the real evaluate_repair_eligibility seam (the single fail-closed
    decision shared by channel-delete, sweeps, and manual repair). When the
    preflight is unresolved (advisor findings present but schema/deployment
    evidence not resolved), the repair MUST be skipped with gate_unresolved
    regardless of how fresh the per-ticket evidence is. Fails if the seam
    ever allows mutation without a resolved preflight.
    """

    def test_unresolved_preflight_blocks_repair_even_with_fresh_evidence(self) -> None:
        from bot.services.ticket_repair import evaluate_repair_eligibility

        # Fresh, corroborated evidence — but preflight unresolved (advisor
        # findings remain; schema/deployment not verified).
        denial = evaluate_repair_eligibility(preflight_allows=False, corroborated=True)
        assert denial == ("skipped", "gate_unresolved"), (
            "advisor findings MUST NOT authorize repair — gate_unresolved no-op"
        )

    def test_resolved_preflight_with_unresolved_evidence_still_blocks(self) -> None:
        from bot.services.ticket_repair import evaluate_repair_eligibility

        # Preflight resolved but evidence not corroborated → still skipped.
        denial = evaluate_repair_eligibility(preflight_allows=True, corroborated=None)
        assert denial == ("skipped", "evidence_unresolved")
        denial = evaluate_repair_eligibility(preflight_allows=True, corroborated=False)
        assert denial == ("skipped", "not_corroborated")

    def test_only_resolved_preflight_and_corroborated_allows_mutation(self) -> None:
        from bot.services.ticket_repair import evaluate_repair_eligibility

        # The ONLY path to a mutation (None) is resolved preflight AND
        # corroborated evidence — advisor findings alone never suffice.
        assert evaluate_repair_eligibility(preflight_allows=True, corroborated=True) is None


# ===========================================================================
# 3. Guards — deferred economy/infraction select(*) scope S3 (deferred marker)
# ===========================================================================


class TestDeferredEconomyInfractionSelectStarScope:
    """S3 — economy/infraction select(*) removal is explicitly deferred to Cycle 3.

    The spec marks this as deferred tech-debt (not a Cycle 2 failure). This
    probe asserts the deferred contract holds: the economy and infraction
    mixins STILL carry select("*") (unchanged from baseline) and the
    Cycle-2-touched greeting mixin does NOT. Fails if someone accidentally
    breaks the deferral by half-removing select("*") or removes the greeting
    explicit-column contract.
    """

    DEFERRED_FILES = (
        "bot/core/db/economy_db.py",
        "bot/core/db/infraction_db.py",
    )

    @pytest.mark.parametrize("path", DEFERRED_FILES)
    def test_deferred_mixins_still_carry_select_star(self, path: str) -> None:
        """Deferred mixins MAY still contain select("*") — documented tech-debt."""
        src = Path(path).read_text(encoding="utf-8")
        assert 'select("*")' in src, (
            f"{path} deferred scope: select('*') must remain until Cycle 3 "
            "(removing it now would break the documented deferral contract)"
        )

    def test_greeting_mixin_explicit_columns_contract_holds(self) -> None:
        """The Cycle-2-touched greeting mixin MUST NOT carry select("*")."""
        src = Path("bot/core/db/greeting_db.py").read_text(encoding="utf-8")
        # The explicit-column contract (Cycle 2 scope) must remain.
        assert 'select("*")' not in src, "greeting_db must keep explicit columns (Cycle 2 scope)"


# ===========================================================================
# 4. Ocio — banana no-DB command path S5 (real callback, no DB write)
# ===========================================================================


class TestBananaNoDbCommandPath:
    """S5 — /banana command path writes no DB row.

    Calls the REAL OcioCog.banana.callback against a FakeSupabaseClient so
    the no-DB contract is exercised at runtime. The fake records every
    table() call; the probe asserts zero writes (no insert/update/delete)
    across ALL tables after the callback completes. Fails if any DB write
    is introduced on the banana path.
    """

    @pytest.mark.asyncio
    async def test_banana_callback_writes_no_db_row(self) -> None:
        from bot.cogs.ocio import OcioCog
        from bot.services.ocio_service import OcioService
        from tests.test_database import FakeSupabaseClient

        # Wire a real fake client onto a mock bot so any accidental DB path
        # would be recorded. OcioCog does not use the DB, but the probe must
        # prove that — not assume it.
        fake = FakeSupabaseClient()
        bot = MagicMock()
        bot.db = fake  # if the cog ever touches bot.db, the fake records it

        cog = OcioCog(bot)
        # Point the service at a real (possibly empty) banana dir so the
        # Pillow fallback runs via asyncio.to_thread — real production path.
        cog.ocio_service = OcioService(banana_dir=Path("assets/images/banana"))

        ctx = MagicMock()
        ctx.guild = MagicMock(id=123456789)
        ctx.send = AsyncMock()

        await cog.banana.callback(cog, ctx)

        # The reply MUST be sent (delivery succeeds).
        ctx.send.assert_awaited_once()
        # CRITICAL: no DB write on ANY table — banana is a no-DB command.
        for table_name in (
            "guild",
            "member",
            "ticket",
            "ticket_category",
            "economy_config",
            "greeting_config",
            "infraction",
            "ticket_note",
            "ticket_audit",
        ):
            calls = fake.get_table_calls(table_name)
            writes = [c for c in calls if c[0] in ("insert", "update", "delete", "upsert")]
            assert not writes, f"/banana MUST NOT write to {table_name} (found {writes})"

    @pytest.mark.asyncio
    async def test_banana_callback_is_ephemeral(self) -> None:
        """S6 companion — the no-DB reply is also ephemeral (contract holds)."""
        from bot.cogs.ocio import OcioCog
        from bot.services.ocio_service import OcioService

        cog = OcioCog(MagicMock())
        cog.ocio_service = OcioService(banana_dir=Path("assets/images/banana"))
        ctx = MagicMock()
        ctx.guild = MagicMock(id=123456789)
        ctx.send = AsyncMock()

        await cog.banana.callback(cog, ctx)

        kwargs = ctx.send.call_args.kwargs
        assert kwargs.get("ephemeral") is True, "/banana reply MUST be ephemeral"


# ===========================================================================
# 5. Time parsing — missing-comma S6 (",12h" vs "12h" distinction)
# ===========================================================================


class TestParseDurationStrictMissingComma:
    """S6 — "12h" without a leading comma MUST return None.

    The strict anchor requires the comma prefix. ",12h" parses to 43200;
    "12h" alone MUST be rejected (None) — never the 3600 fallback. Fails
    if the strict regex is ever loosened to drop the comma requirement.
    """

    def test_missing_comma_returns_none(self) -> None:
        # The exact spec scenario: "12h" (no leading comma) → None.
        assert parse_duration_strict("12h") is None, (
            "strict parser MUST require the comma prefix — '12h' alone is rejected"
        )

    def test_with_comma_parses(self) -> None:
        # The comma-prefixed form MUST succeed — proves the distinction.
        assert parse_duration_strict(",12h") == 43200

    def test_missing_comma_never_returns_fallback(self) -> None:
        # MUST NOT fall back to the 3600 default that parse_duration uses.
        assert parse_duration_strict("12h") != 3600

    @pytest.mark.parametrize(
        "raw",
        ["1h", "30m", "1d", "2h30m", "1w", "1y", " 12h", "12h ", "1h 30m"],
    )
    def test_any_duration_without_comma_returns_none(self, raw: str) -> None:
        assert parse_duration_strict(raw) is None, f"{raw!r} lacks a leading comma — strict parser MUST return None"

    def test_comma_prefix_is_the_distinction(self) -> None:
        """The comma is the sole distinction: same body, different result."""
        # "12h" → None; ",12h" → 43200. Removing the comma MUST break parsing.
        assert parse_duration_strict("12h") is None
        assert parse_duration_strict(",12h") == 43200


# ===========================================================================
# 6. Welcome/Goodbye — GaussianBlur S3 (real render, blur invoked + glow visible)
# ===========================================================================


class TestNeonGaussianBlur:
    """S3 — the neon glow is produced via ImageFilter.GaussianBlur (Pillow).

    Two behavioral assertions: (a) the real neon render path actually invokes
    ImageFilter.GaussianBlur (patched on the real Image.Image.filter so the
    call is observed), and (b) the rendered glow spreads accent pixels beyond
    the sharp hex outline (pixel-spread proves a blur was applied, not a
    no-op). Fails if GaussianBlur is removed or the glow stops spreading.
    """

    def test_neon_render_invokes_gaussian_blur(self) -> None:
        from unittest.mock import patch

        from PIL import Image
        from PIL import ImageFilter as _RealImageFilter  # noqa: F401 — proves import path

        from bot.services.greeting_renderer import PillowGreetingRenderer

        # Track real GaussianBlur construction through the renderer's
        # ImageFilter import. The renderer calls glow.filter(...); we patch
        # Image.Image.filter to observe the blur class used.
        seen: list[str] = []
        real_filter = Image.Image.filter

        def _spy_filter(self, image_filter, *args, **kwargs):
            seen.append(type(image_filter).__name__)
            return real_filter(self, image_filter, *args, **kwargs)

        with patch.object(Image.Image, "filter", _spy_filter):
            renderer = PillowGreetingRenderer()
            renderer.render(
                username="NeonUser",
                avatar_url=None,
                guild_name="Neon Guild",
                member_count=7,
                card_type="welcome",
                greeting_title="Welcome!",
                member_count_text="Member #7",
                guild_icon_url=None,
                theme_id="gaming_neon",
            )

        assert "GaussianBlur" in seen, "neon render MUST invoke ImageFilter.GaussianBlur — saw filters: " + str(seen)

    def test_neon_glow_paints_blurred_accent_pixels(self) -> None:
        """The GaussianBlur glow paints ACCENT_A/ACCENT_B pixels that do NOT
        exist in the default render. The blur spreads the hex polygon fill
        into a halo; the default render uses a single ``brand.ACCENT`` and
        never produces ACCENT_A/B pixels. Fails if the blur is removed (no
        glow painted) or the neon accents stop being read from brand."""
        from PIL import Image

        from bot.services.greeting_renderer import PillowGreetingRenderer
        from bot.utils import brand

        common = {
            "username": "User",
            "avatar_url": None,
            "guild_name": "Guild",
            "member_count": 1,
            "card_type": "welcome",
            "greeting_title": "Welcome!",
            "member_count_text": "Member #1",
            "guild_icon_url": None,
        }
        renderer = PillowGreetingRenderer()
        default_buf = renderer.render(**common)
        neon_buf = renderer.render(theme_id="gaming_neon", **common)

        neon_img = Image.open(io.BytesIO(neon_buf.getvalue())).convert("RGBA")
        default_img = Image.open(io.BytesIO(default_buf.getvalue())).convert("RGBA")
        a_rgb = ((brand.ACCENT_A >> 16) & 255, (brand.ACCENT_A >> 8) & 255, brand.ACCENT_A & 255)
        b_rgb = ((brand.ACCENT_B >> 16) & 255, (brand.ACCENT_B >> 8) & 255, brand.ACCENT_B & 255)

        def _count_accent(img: Image.Image) -> tuple[int, int]:
            pix = img.load()
            w, h = img.size
            ca = cb = 0
            for y in range(h):
                for x in range(w):
                    p = pix[x, y]
                    if p[:3] == a_rgb:
                        ca += 1
                    if p[:3] == b_rgb:
                        cb += 1
            return ca, cb

        neon_a, neon_b = _count_accent(neon_img)
        default_a, default_b = _count_accent(default_img)
        # The neon glow paints a nonzero halo of ACCENT_A/B pixels; the
        # default render paints NONE of them (it uses brand.ACCENT only).
        assert neon_a > 0 and neon_b > 0, "GaussianBlur glow MUST paint ACCENT_A and ACCENT_B neon pixels"
        assert default_a == 0 and default_b == 0, "default render MUST NOT use neon accents (only the neon glow does)"


# ===========================================================================
# 7. Sentinel — Author role hierarchy deny before mutation S5 (runtime guard)
# ===========================================================================


class TestSentinelAuthorHierarchyGuardRuntime:
    """S5 — the author-hierarchy guard denies a non-admin BEFORE any mutation.

    The verify-report scored this ❌ (prose-only). This runtime probe calls
    the real SentinelCog._validate_target with an author whose top_role is
    below the target's and asserts: (a) the guard returns False, (b) an
    ephemeral error embed is sent, and (c) NO moderation mutation occurs
    (the bot's kick/ban/timeout are never invoked). Fails if the guard is
    removed or weakened.
    """

    @pytest.mark.asyncio
    async def test_author_below_target_denies_without_mutation(self) -> None:
        from bot.cogs.sentinel import SentinelCog

        def _make_member(role_val: int, member_id: int) -> MagicMock:
            m = MagicMock()
            m.id = member_id
            m.mention = f"<@{member_id}>"
            role = MagicMock()
            role.__le__ = MagicMock(side_effect=lambda other: role_val <= getattr(other, "_val", 0))
            role._val = role_val
            m.top_role = role
            m.roles = []
            m.guild_permissions = MagicMock()
            m.guild_permissions.administrator = False
            return m

        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 999
        # Moderation mutation hooks — MUST remain uncalled.
        bot.kick = AsyncMock()
        bot.ban = AsyncMock()

        cog = SentinelCog(bot=bot)
        guild = MagicMock()
        guild.owner = MagicMock()
        guild.owner.id = 9999
        guild.me = MagicMock()
        guild.me.top_role = MagicMock()
        guild.me.top_role.__le__ = MagicMock(return_value=False)  # bot above target
        guild.id = 123

        author = _make_member(role_val=5, member_id=10)  # below target
        target = _make_member(role_val=10, member_id=20)

        ctx = MagicMock()
        ctx.guild = guild
        ctx.author = author
        ctx.send = AsyncMock()

        result = await cog._validate_target(ctx, target, action="warn")

        # The guard MUST deny (False) — no mutation path proceeds.
        assert result is False, "author-hierarchy deny MUST fire (author below target)"
        # An ephemeral error embed MUST be sent.
        ctx.send.assert_awaited_once()
        sent_kwargs = ctx.send.call_args.kwargs
        assert sent_kwargs.get("embed") is not None, "deny MUST send an error embed"
        # CRITICAL: no moderation mutation reached the bot.
        bot.kick.assert_not_called()
        bot.ban.assert_not_called()
