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


# ---------------------------------------------------------------------------
# Webhook configuration — WEBHOOK_SECRET / WEBHOOK_HOST / WEBHOOK_PORT
# ---------------------------------------------------------------------------


class TestWebhookConfig:
    """Spec: cache-sync-webhook — Environment configuration.

    Missing fields MUST fall back to defaults WITHOUT exception.
    WEBHOOK_SECRET absent -> empty string (server won't start).
    WEBHOOK_HOST absent -> default 127.0.0.1.
    WEBHOOK_PORT absent -> default 8080.
    """

    def test_webhook_secret_defaults_empty_when_missing(self) -> None:
        """WEBHOOK_SECRET absent MUST default to empty string (no exception)."""
        with patch.dict(os.environ, {}, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_secret == ""

    def test_webhook_host_defaults_to_loopback_when_missing(self) -> None:
        """WEBHOOK_HOST absent MUST fall back to 127.0.0.1."""
        with patch.dict(os.environ, {}, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_host == "127.0.0.1"

    def test_webhook_port_defaults_to_8080_when_missing(self) -> None:
        """WEBHOOK_PORT absent MUST fall back to 8080."""
        with patch.dict(os.environ, {}, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_port == 8080

    def test_webhook_secret_loaded_from_env(self) -> None:
        """WEBHOOK_SECRET set MUST populate webhook_secret."""
        env = {"WEBHOOK_SECRET": "super-secret-key"}
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_secret == "super-secret-key"

    def test_webhook_host_loaded_from_env(self) -> None:
        """WEBHOOK_HOST set MUST override the default (e.g. 0.0.0.0 for Pterodactyl)."""
        env = {"WEBHOOK_SECRET": "k", "WEBHOOK_HOST": "0.0.0.0"}
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_host == "0.0.0.0"

    def test_webhook_port_loaded_from_env(self) -> None:
        """WEBHOOK_PORT set to a valid integer MUST override the default."""
        env = {"WEBHOOK_SECRET": "k", "WEBHOOK_PORT": "9090"}
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_port == 9090

    def test_webhook_port_invalid_falls_back_to_default(self) -> None:
        """An invalid WEBHOOK_PORT MUST fall back to 8080 without raising."""
        env = {"WEBHOOK_SECRET": "k", "WEBHOOK_PORT": "not-a-number"}
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig.from_env(env_path="/dev/null")

        assert config.webhook_port == 8080
