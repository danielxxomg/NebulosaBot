"""Unit tests for bot.config.BotConfig.

Covers the qa-config-coverage spec scenarios:
    - Default config values applied when env vars missing
    - Custom config values override defaults when env vars set
    - Invalid/missing fields fall back to defaults without exception
"""

from __future__ import annotations

import os
from unittest.mock import patch

from bot.config import BotConfig

# ---------------------------------------------------------------------------
# BotConfig dataclass — field defaults
# ---------------------------------------------------------------------------


class TestBotConfigDataclass:
    """Verify BotConfig dataclass fields and _env_vars."""

    def test_env_vars_tuple(self) -> None:
        """_env_vars MUST list DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY."""
        assert BotConfig._env_vars == ("DISCORD_TOKEN", "SUPABASE_URL", "SUPABASE_KEY")

    def test_dataclass_fields_exist(self) -> None:
        """BotConfig MUST have discord_token, supabase_url, supabase_key fields."""
        config = BotConfig(
            discord_token="tok",
            supabase_url="https://example.supabase.co",
            supabase_key="key",
        )
        assert config.discord_token == "tok"
        assert config.supabase_url == "https://example.supabase.co"
        assert config.supabase_key == "key"


# ---------------------------------------------------------------------------
# from_env — all vars present (happy path)
# ---------------------------------------------------------------------------


class TestFromEnvHappyPath:
    """Scenario: custom config values override defaults when env vars set."""

    def test_from_env_loads_all_vars(self) -> None:
        """from_env MUST return a BotConfig with values from env."""
        env = {
            "DISCORD_TOKEN": "test-token-12345",
            "SUPABASE_URL": "https://proj.supabase.co",
            "SUPABASE_KEY": "anon-key-abc",
        }
        with patch.dict(os.environ, env, clear=False):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.discord_token == "test-token-12345"
        assert config.supabase_url == "https://proj.supabase.co"
        assert config.supabase_key == "anon-key-abc"

    def test_from_env_with_partial_existing_env(self) -> None:
        """from_env MUST read only the required vars; other env vars untouched."""
        env = {
            "DISCORD_TOKEN": "tok-xyz",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_KEY": "key-999",
            "UNRELATED_VAR": "should-not-matter",
        }
        with patch.dict(os.environ, env, clear=False):
            config = BotConfig.from_env(env_path="/dev/null")
            assert config.discord_token == "tok-xyz"
            assert os.environ.get("UNRELATED_VAR") == "should-not-matter"


# ---------------------------------------------------------------------------
# from_env — missing vars fall back to defaults (spec: no exception)
# ---------------------------------------------------------------------------


class TestFromEnvFallback:
    """Scenario: invalid/missing fields fall back to defaults without exception.

    Per qa-config-coverage/spec.md, missing or invalid env vars MUST fall
    back to defaults rather than raising. BotConfig fields default to
    empty strings so from_env() always returns a BotConfig instance.
    """

    def test_from_env_missing_all_vars_returns_defaults(self) -> None:
        """from_env MUST return a BotConfig with defaults when all vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.discord_token == ""
        assert config.supabase_url == ""
        assert config.supabase_key == ""

    def test_from_env_missing_one_var_uses_default(self) -> None:
        """from_env MUST use the field default for a single missing var."""
        env = {
            "DISCORD_TOKEN": "tok",
            "SUPABASE_URL": "https://x.supabase.co",
            # SUPABASE_KEY missing
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.discord_token == "tok"
        assert config.supabase_url == "https://x.supabase.co"
        assert config.supabase_key == ""  # falls back to default

    def test_from_env_empty_string_uses_default(self) -> None:
        """An empty string for a required var MUST fall back to the default."""
        env = {
            "DISCORD_TOKEN": "",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_KEY": "key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.discord_token == ""  # empty → falls back
        assert config.supabase_url == "https://x.supabase.co"
        assert config.supabase_key == "key"

    def test_from_env_no_exception_on_missing_vars(self) -> None:
        """from_env MUST NOT raise when env vars are missing (spec requirement)."""
        with patch.dict(os.environ, {}, clear=True):
            # Must not raise — this is the core spec assertion
            config = BotConfig.from_env(env_path="/dev/null")

        assert isinstance(config, BotConfig)
