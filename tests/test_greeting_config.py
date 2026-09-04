"""Unit tests for bot.models.greeting_config.GreetingConfig.

Covers the GreetingConfig model: field defaults, from_db_row mapping,
to_db_dict conversion, and roundtrip consistency. Also covers the S2
per-kind template persistence: fallback chain via select_template and
greeting_db write/read paths for welcomeTemplateId/goodbyeTemplateId.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.core.database import Database
from bot.models.greeting_config import GreetingConfig
from bot.services.greeting_service import select_template


def _captured_select(client: Any) -> str | None:
    """Extract the select column list the fake table observed (test seam)."""
    return getattr(client._table, "last_select", None)  # noqa: SLF001 — test seam


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestGreetingConfigDefaults:
    """New GreetingConfig instances should have sensible defaults."""

    def test_default_guild_id_only(self) -> None:
        """Creating a config with only guild_id sets all defaults.

        Per greeting-config spec (Scenario: Default values for new guild),
        card toggles default to ``False`` for new guilds.
        """
        config = GreetingConfig(guild_id="123456789")
        assert config.guild_id == "123456789"
        assert config.welcome_enabled is False
        assert config.goodbye_enabled is False
        assert config.welcome_channel_id is None
        assert config.goodbye_channel_id is None
        assert config.onboarding_channel_id is None
        assert config.welcome_message is None
        assert config.goodbye_message is None
        assert config.welcome_card_enabled is False
        assert config.goodbye_card_enabled is False

    def test_default_welcome_card_enabled_is_false(self) -> None:
        """Welcome card defaults to False (greeting-config spec: new-guild card toggles are false)."""
        config = GreetingConfig(guild_id="abc")
        assert config.welcome_card_enabled is False

    def test_default_goodbye_card_enabled_is_false(self) -> None:
        """Goodbye card defaults to False (greeting-config spec: new-guild card toggles are false)."""
        config = GreetingConfig(guild_id="abc")
        assert config.goodbye_card_enabled is False


# ---------------------------------------------------------------------------
# from_db_row — Supabase camelCase row → GreetingConfig
# ---------------------------------------------------------------------------


class TestFromDbRow:
    """from_db_row() must correctly map camelCase DB columns to snake_case fields."""

    def test_full_row_maps_all_fields(self) -> None:
        """All 10 columns should be mapped from a complete DB row."""
        row = {
            "guildId": "123456789",
            "welcomeEnabled": True,
            "goodbyeEnabled": True,
            "welcomeChannelId": "111111111",
            "goodbyeChannelId": "222222222",
            "onboardingChannelId": "333333333",
            "welcomeMessage": "Welcome {mention}!",
            "goodbyeMessage": "Goodbye {mention}!",
            "welcomeCardEnabled": True,
            "goodbyeCardEnabled": False,
        }
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "123456789"
        assert config.welcome_enabled is True
        assert config.goodbye_enabled is True
        assert config.welcome_channel_id == "111111111"
        assert config.goodbye_channel_id == "222222222"
        assert config.onboarding_channel_id == "333333333"
        assert config.welcome_message == "Welcome {mention}!"
        assert config.goodbye_message == "Goodbye {mention}!"
        assert config.welcome_card_enabled is True
        assert config.goodbye_card_enabled is False

    def test_minimal_row_uses_defaults(self) -> None:
        """A row with only the primary key should fill missing fields with defaults."""
        row = {"guildId": "999888777"}
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "999888777"
        assert config.welcome_enabled is False
        assert config.goodbye_enabled is False
        assert config.welcome_channel_id is None
        assert config.goodbye_channel_id is None
        assert config.welcome_message is None
        assert config.goodbye_message is None

    def test_partial_row_picks_present_values(self) -> None:
        """Provided values should be used; missing ones should get defaults."""
        row = {
            "guildId": "aaa",
            "welcomeEnabled": True,
            "welcomeChannelId": "bbb",
            "welcomeMessage": "Hey {mention}!",
        }
        config = GreetingConfig.from_db_row(row)
        assert config.guild_id == "aaa"
        assert config.welcome_enabled is True
        assert config.welcome_channel_id == "bbb"
        assert config.welcome_message == "Hey {mention}!"
        # Missing fields should use defaults.
        assert config.goodbye_enabled is False
        assert config.goodbye_channel_id is None
        assert config.onboarding_channel_id is None
        assert config.goodbye_message is None


# ---------------------------------------------------------------------------
# to_db_dict — GreetingConfig → camelCase dict for Supabase
# ---------------------------------------------------------------------------


class TestToDbDict:
    """to_db_dict() must produce a dict with camelCase keys matching the DB schema."""

    def test_full_config_converts_all_fields(self) -> None:
        """All fields should be present in the output dict with correct camelCase keys."""
        config = GreetingConfig(
            guild_id="123456789",
            welcome_enabled=True,
            goodbye_enabled=False,
            welcome_channel_id="111111111",
            goodbye_channel_id=None,
            onboarding_channel_id="333333333",
            welcome_message="Welcome {mention}!",
            goodbye_message=None,
            welcome_card_enabled=True,
            goodbye_card_enabled=False,
        )
        result = config.to_db_dict()
        expected_keys = {
            "guildId",
            "welcomeEnabled",
            "goodbyeEnabled",
            "welcomeChannelId",
            "goodbyeChannelId",
            "onboardingChannelId",
            "welcomeMessage",
            "goodbyeMessage",
            "welcomeCardEnabled",
            "goodbyeCardEnabled",
            "updatedAt",
            "themeId",
            "welcomeTemplateId",
            "goodbyeTemplateId",
        }
        assert set(result.keys()) == expected_keys
        assert result["welcomeTemplateId"] is None
        assert result["goodbyeTemplateId"] is None
        assert result["guildId"] == "123456789"
        assert result["welcomeEnabled"] is True
        assert result["goodbyeEnabled"] is False
        assert result["welcomeChannelId"] == "111111111"
        assert result["goodbyeChannelId"] is None
        assert result["onboardingChannelId"] == "333333333"
        assert result["welcomeMessage"] == "Welcome {mention}!"
        assert result["goodbyeMessage"] is None
        assert result["welcomeCardEnabled"] is True
        assert result["goodbyeCardEnabled"] is False

    def test_bool_values_are_booleans(self) -> None:
        """Boolean fields must remain Python bool, not ints or strings."""
        config = GreetingConfig(
            guild_id="x",
            welcome_enabled=True,
            goodbye_enabled=False,
            welcome_card_enabled=True,
            goodbye_card_enabled=False,
        )
        result = config.to_db_dict()
        assert isinstance(result["welcomeEnabled"], bool)
        assert isinstance(result["goodbyeEnabled"], bool)
        assert isinstance(result["welcomeCardEnabled"], bool)
        assert isinstance(result["goodbyeCardEnabled"], bool)


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    """from_db_row(to_db_dict(config)) should be equivalent to the original config."""

    def test_roundtrip_preserves_all_fields(self) -> None:
        """Serializing then deserializing should recover the same values."""
        original = GreetingConfig(
            guild_id="123456789",
            welcome_enabled=True,
            goodbye_enabled=True,
            welcome_channel_id="111",
            goodbye_channel_id="222",
            onboarding_channel_id="333",
            welcome_message="Hello {mention}!",
            goodbye_message="Bye {mention}!",
            welcome_card_enabled=False,
            goodbye_card_enabled=True,
        )
        db_dict = original.to_db_dict()
        restored = GreetingConfig.from_db_row(db_dict)
        assert restored == original


# ---------------------------------------------------------------------------
# theme_id round-trip (PR1 2.1)
# ---------------------------------------------------------------------------


class TestThemeIdRoundTrip:
    """theme_id nullable round-trip via from_db_row / to_db_dict."""

    @pytest.mark.parametrize(
        ("row", "expected"),
        [
            pytest.param({"guildId": "g1", "themeId": "gaming_neon"}, "gaming_neon", id="reads-theme-id"),
            pytest.param({"guildId": "g1"}, None, id="null-when-absent"),
        ],
    )
    def test_from_db_row_theme_id(self, row: dict[str, str], expected: str | None) -> None:
        cfg = GreetingConfig.from_db_row(row)
        assert cfg.theme_id == expected

    @pytest.mark.parametrize(
        ("theme_id", "expected"),
        [
            pytest.param("gaming_neon", "gaming_neon", id="includes-theme-id"),
            pytest.param(None, None, id="null-theme-id-persists"),
        ],
    )
    def test_to_db_dict_theme_id(self, theme_id: str | None, expected: str | None) -> None:
        cfg = GreetingConfig(guild_id="g1", theme_id=theme_id)
        d = cfg.to_db_dict()
        assert d["themeId"] == expected

    @pytest.mark.parametrize(
        "theme_id",
        [
            pytest.param("gaming_neon", id="preserves-neon-theme-id"),
            pytest.param(None, id="preserves-null-theme-id"),
        ],
    )
    def test_roundtrip_preserves_theme_id(self, theme_id: str | None) -> None:
        original = GreetingConfig(guild_id="g1", theme_id=theme_id, welcome_enabled=True)
        restored = GreetingConfig.from_db_row(original.to_db_dict())
        assert restored.theme_id == theme_id
        assert restored == original


# ---------------------------------------------------------------------------
# Per-kind template columns (greeting-templates S2)
# ---------------------------------------------------------------------------


class TestPerKindTemplateFields:
    """GreetingConfig carries welcome_template_id / goodbye_template_id (S2)."""

    def test_default_new_guild_fields_are_null(self) -> None:
        """Spec: new guild defaults → per-kind template ids null → default render."""
        config = GreetingConfig(guild_id="g1")
        assert config.welcome_template_id is None
        assert config.goodbye_template_id is None

    def test_from_db_row_reads_per_kind_ids(self) -> None:
        row = {
            "guildId": "g1",
            "welcomeTemplateId": "sunset_wave",
            "goodbyeTemplateId": "minimal_light",
        }
        cfg = GreetingConfig.from_db_row(row)
        assert cfg.welcome_template_id == "sunset_wave"
        assert cfg.goodbye_template_id == "minimal_light"

    def test_from_db_row_missing_per_kind_ids_are_none(self) -> None:
        """Legacy rows (pre-030) without the columns map to None."""
        cfg = GreetingConfig.from_db_row({"guildId": "g1", "themeId": "gaming_neon"})
        assert cfg.welcome_template_id is None
        assert cfg.goodbye_template_id is None
        assert cfg.theme_id == "gaming_neon"


class TestWelcomeWinsDualWrite:
    """to_db_dict dual-writes themeId; explicit templateId wins over themeId mapping."""

    @pytest.mark.parametrize(
        ("theme_id", "welcome_id", "goodbye_id", "expected_theme", "expected_welcome", "expected_goodbye"),
        [
            # (theme, welcome, goodbye) -> (mirrored themeId, welcomeTemplateId, goodbyeTemplateId)
            pytest.param(
                "gaming_neon",
                "minimal_light",
                None,
                "minimal_light",
                "minimal_light",
                None,
                id="welcome-wins-over-theme-id",
            ),
            pytest.param(
                None, None, "sunset_wave", "sunset_wave", None, "sunset_wave", id="goodbye-mirrors-when-welcome-absent"
            ),
            pytest.param(
                "gaming_neon",
                "sunset_wave",
                "minimal_light",
                "sunset_wave",
                "sunset_wave",
                "minimal_light",
                id="welcome-wins-tie-between-kinds",
            ),
            pytest.param(
                "gaming_neon",
                None,
                None,
                "gaming_neon",
                None,
                None,
                id="legacy-theme-id-preserved-when-no-per-kind-set",
            ),
            pytest.param(None, None, None, None, None, None, id="all-null-stay-null"),
        ],
    )
    def test_to_db_dict_dual_write(
        self,
        theme_id: str | None,
        welcome_id: str | None,
        goodbye_id: str | None,
        expected_theme: str | None,
        expected_welcome: str | None,
        expected_goodbye: str | None,
    ) -> None:
        """Dual-write mapping per case: welcome > goodbye > legacy theme_id pass-through."""
        cfg = GreetingConfig(
            guild_id="g1", theme_id=theme_id, welcome_template_id=welcome_id, goodbye_template_id=goodbye_id
        )
        d = cfg.to_db_dict()
        assert d["themeId"] == expected_theme
        assert d["welcomeTemplateId"] == expected_welcome
        assert d["goodbyeTemplateId"] == expected_goodbye


class TestPerKindRoundtrip:
    """Per-kind template ids survive to_db_dict → from_db_row."""

    def test_roundtrip_preserves_per_kind_ids(self) -> None:
        """Per-kind ids survive a roundtrip.

        Full dataclass equality is intentionally NOT asserted: the dual-write
        contract mirrors the effective per-kind selection into legacy
        ``themeId``, so a config with only per-kind ids re-reads with
        ``theme_id`` set to the welcome id (documented S2 behavior).
        """
        original = GreetingConfig(
            guild_id="g1",
            welcome_template_id="sunset_wave",
            goodbye_template_id="minimal_light",
        )
        restored = GreetingConfig.from_db_row(original.to_db_dict())
        assert restored.welcome_template_id == "sunset_wave"
        assert restored.goodbye_template_id == "minimal_light"
        assert restored.theme_id == "sunset_wave"  # welcome-wins dual-write

    def test_roundtrip_null_per_kind_ids(self) -> None:
        original = GreetingConfig(guild_id="g1")
        restored = GreetingConfig.from_db_row(original.to_db_dict())
        assert restored.welcome_template_id is None
        assert restored.goodbye_template_id is None
        assert restored == original


# ---------------------------------------------------------------------------
# Per-kind fallback chain via select_template (greeting-templates S2)
# ---------------------------------------------------------------------------


def _make_config(**kwargs: object) -> GreetingConfig:
    """Build a GreetingConfig with defaults overridden by *kwargs*."""
    return GreetingConfig(guild_id="g1", **kwargs)  # type: ignore[arg-type]


class TestSelectTemplateFallbackChain:
    """select_template resolves per-kind → legacy theme_id → default (S2 spec)."""

    def test_welcome_resolves_welcome_template_id(self) -> None:
        cfg = _make_config(
            welcome_template_id="sunset_wave",
            goodbye_template_id="default",
            theme_id="gaming_neon",
        )
        assert select_template(cfg, "welcome") == "sunset_wave"

    def test_goodbye_resolves_independently(self) -> None:
        """Same config, goodbye resolves its own kind — kinds MAY differ."""
        cfg = _make_config(
            welcome_template_id="sunset_wave",
            goodbye_template_id="default",
            theme_id="gaming_neon",
        )
        assert select_template(cfg, "goodbye") == "default"

    def test_fallback_to_legacy_theme_id_when_kind_null(self) -> None:
        cfg = _make_config(welcome_template_id=None, theme_id="gaming_neon")
        assert select_template(cfg, "welcome") == "gaming_neon"

    def test_fallback_to_default_when_both_absent(self) -> None:
        cfg = _make_config(welcome_template_id=None, theme_id=None)
        assert select_template(cfg, "welcome") == "default"

    def test_unknown_template_id_falls_back_to_default(self) -> None:
        cfg = _make_config(welcome_template_id="unknown_xyz", theme_id=None)
        assert select_template(cfg, "welcome") == "default"

    def test_unknown_theme_falls_back_to_default(self) -> None:
        cfg = _make_config(welcome_template_id=None, theme_id="unknown_xyz")
        assert select_template(cfg, "goodbye") == "default"


# ---------------------------------------------------------------------------
# DB write/read paths for per-kind columns (greeting-templates S2)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.data = rows if rows is not None else []


class _FakeTable:
    """Minimal greeting_config table stub — records select cols + last upsert."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.last_upsert: dict[str, Any] | None = None
        self.last_select: str | None = None

    def select(self, cols: str) -> _FakeTable:
        self.last_select = cols
        return self

    def eq(self, _col: str, _val: str) -> _FakeTable:
        return self

    def upsert(self, payload: dict[str, Any], on_conflict: str) -> _FakeTable:  # noqa: ARG002
        self.last_upsert = payload
        return self

    async def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeClient:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.table_calls: list[str] = []
        self._table = _FakeTable(rows)

    def table(self, name: str) -> _FakeTable:
        self.table_calls.append(name)
        return self._table


class TestGreetingDbPerKindPaths:
    """greeting_db select columns + upsert payload carry per-kind template ids."""

    @pytest.mark.asyncio
    async def test_get_greeting_config_selects_per_kind_columns(self) -> None:
        """Column list includes welcomeTemplateId/goodbyeTemplateId (no select('*'))."""
        row = {"guildId": "g1", "welcomeTemplateId": "sunset_wave"}
        client = _FakeClient([row])
        db = Database.__new__(Database)
        db._client = client
        db._on_write = None

        result = await db.get_greeting_config("g1")

        assert result == row
        select_clause = client.table_calls and _captured_select(client)
        assert select_clause is not None
        assert "welcomeTemplateId" in select_clause
        assert "goodbyeTemplateId" in select_clause

    @pytest.mark.asyncio
    async def test_upsert_payload_includes_per_kind_columns(self) -> None:
        """Upsert persists welcomeTemplateId/goodbyeTemplateId + dual-written themeId."""
        client = _FakeClient()
        db = Database.__new__(Database)
        db._client = client
        db._on_write = None
        config = GreetingConfig(guild_id="g1", theme_id="gaming_neon", welcome_template_id="minimal_light")

        await db.upsert_greeting_config("g1", config)

        payload = client._table.last_upsert  # noqa: SLF001 — test seam
        assert payload is not None
        assert payload["welcomeTemplateId"] == "minimal_light"
        assert payload["goodbyeTemplateId"] is None
        assert payload["themeId"] == "minimal_light"  # welcome-wins dual-write

    @pytest.mark.asyncio
    async def test_upsert_triggers_cache_invalidation_on_write(self) -> None:
        """CDC contract: upsert fires _on_write('greeting_config', guild_id)."""
        client = _FakeClient()
        db = Database.__new__(Database)
        db._client = client
        on_write = AsyncMock()
        db._on_write = on_write
        config = GreetingConfig(guild_id="g1", welcome_template_id="sunset_wave")

        await db.upsert_greeting_config("g1", config)

        on_write.assert_awaited_once_with("greeting_config", "g1")

    @pytest.mark.asyncio
    async def test_upsert_propagates_non_unique_errors(self) -> None:
        """Non-23505 upsert errors propagate — per-kind payload writes are not swallowed."""
        client = _FakeClient()

        class _BrokenTable(_FakeTable):
            def upsert(self, payload: dict[str, Any], on_conflict: str) -> _FakeTable:  # noqa: ARG002
                exc = RuntimeError("boom")
                exc.code = "42710"  # type: ignore[attr-defined] — non-unique violation
                raise exc

        client._table = _BrokenTable()
        db = Database.__new__(Database)
        db._client = client
        db._on_write = None
        config = GreetingConfig(guild_id="g1", welcome_template_id="minimal_light")

        with pytest.raises(RuntimeError, match="boom"):
            await db.upsert_greeting_config("g1", config)
