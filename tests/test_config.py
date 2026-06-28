"""Unit tests for bot.config.BotConfig.

Covers the qa-config-coverage spec scenarios:
    - Default config values applied when env vars missing
    - Custom config values override defaults when env vars set
    - Invalid/missing fields fall back to defaults without exception
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from bot.config import BotConfig


# ---------------------------------------------------------------------------
# BotConfig dataclass — field defaults
# ---------------------------------------------------------------------------


class TestBotConfigDataclass:
    """Verify BotConfig dataclass fields and _required_vars."""

    def test_required_vars_tuple(self) -> None:
        """_required_vars MUST list DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY."""
        assert BotConfig._required_vars == ("DISCORD_TOKEN", "SUPABASE_URL", "SUPABASE_KEY")

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
# from_env — missing vars raise ValueError
# ---------------------------------------------------------------------------


class TestFromEnvMissingVars:
    """Scenario: invalid/missing fields fall back to defaults without exception.

    BotConfig.from_env raises ValueError on missing vars — this is the
    expected behavior (no silent fallback for required credentials).
    The spec scenario 'invalid/missing fields fall back to defaults without
    exception' applies to optional fields with defaults, but BotConfig has
    NO optional fields — all three are required.  The test verifies the
    correct error is raised.
    """

    def test_from_env_missing_all_vars_raises(self) -> None:
        """from_env MUST raise ValueError when all vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing required environment variables"):
                BotConfig.from_env(env_path="/dev/null")

    def test_from_env_missing_one_var_raises(self) -> None:
        """from_env MUST raise ValueError listing the missing var name."""
        env = {
            "DISCORD_TOKEN": "tok",
            "SUPABASE_URL": "https://x.supabase.co",
            # SUPABASE_KEY missing
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_KEY"):
                BotConfig.from_env(env_path="/dev/null")

    def test_from_env_empty_string_treated_as_missing(self) -> None:
        """An empty string for a required var MUST be treated as missing."""
        env = {
            "DISCORD_TOKEN": "",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_KEY": "key",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="DISCORD_TOKEN"):
                BotConfig.from_env(env_path="/dev/null")

    def test_from_env_multiple_missing_vars_listed(self) -> None:
        """from_env MUST list ALL missing vars in the error message."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DISCORD_TOKEN.*SUPABASE_URL.*SUPABASE_KEY"):
                BotConfig.from_env(env_path="/dev/null")
