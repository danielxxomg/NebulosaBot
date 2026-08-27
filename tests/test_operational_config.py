"""S4.1 — Typed TOML loader RED (operational-config).

Scenarios:
- valid file applies typed values
- absent file → env-only boot (no error, defaults)
- malformed → TOMLDecodeError fail-fast naming parse failure
- secrets-scan (no token/DB creds in config.toml)
- unknown keys → WARNING + ignored
- .env never feeds operational settings

Ref: operational-config Typed TOML loader.
"""

from __future__ import annotations

import dataclasses
import logging
import tomllib
from pathlib import Path

import pytest


def _valid_toml_content() -> str:
    return """
[logging]
level = "DEBUG"
file = "logs/bot.log"

[limits]
rank_render_max_concurrent = 5
backfill_concurrency = 10

[timeouts]
integrity_backoff_seconds = 2.5

[retention]
tickets = 7
infractions = 14
crash = 21

[features]
retention_enabled = false
"""


class TestOperationalConfigLoader:
    def test_valid_file_applies_typed_values(self, tmp_path: Path) -> None:
        try:
            from bot.operational_config import load_operational_config  # noqa: PLC0415 -- cycle-safe probe in test
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(_valid_toml_content(), encoding="utf-8")
        cfg = load_operational_config(cfg_path)

        # Logging
        assert cfg.logging.level == "DEBUG"
        assert cfg.logging.file == "logs/bot.log"
        # Limits
        assert cfg.limits.rank_render_max_concurrent == 5
        assert cfg.limits.backfill_concurrency == 10
        # Timeouts
        assert cfg.timeouts.integrity_backoff_seconds == 2.5
        # Retention
        assert cfg.retention.tickets == 7
        assert cfg.retention.infractions == 14
        assert cfg.retention.crash == 21
        # Flags
        assert cfg.flags.retention_enabled is False
        # Frozen
        assert cfg.__dataclass_params__.frozen is True

    def test_absent_file_falls_back_to_defaults(self, tmp_path: Path) -> None:
        try:
            from bot.operational_config import load_operational_config as load_fn  # noqa: PLC0415 -- test probe
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        missing = tmp_path / "no_such_config.toml"
        assert not missing.exists()
        cfg = load_fn(missing)
        # Must boot without error and expose defaults
        assert cfg.retention.tickets == 30
        assert cfg.retention.infractions == 180
        assert cfg.retention.crash == 30
        assert cfg.flags.retention_enabled is True

    def test_malformed_fails_fast_toml_decode_error(self, tmp_path: Path) -> None:
        try:
            from bot.operational_config import load_operational_config  # noqa: PLC0415 -- test probe
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        bad = tmp_path / "bad.toml"
        bad.write_text("[[[ not valid toml = ", encoding="utf-8")
        try:
            load_operational_config(bad)
        except tomllib.TOMLDecodeError:
            return
        except Exception as exc:  # noqa: BLE001 -- test asserts specific error type
            msg = f"expected TOMLDecodeError, got {type(exc).__name__}: {exc}"
            raise AssertionError(msg) from exc
        raise AssertionError("expected TOMLDecodeError for malformed config.toml") from None

    def test_secrets_scan_no_token_or_db_creds(self) -> None:
        repo_toml = Path("config.toml")
        example_toml = Path("config.example.toml")
        # At least example must exist after S4.4
        assert example_toml.exists(), "config.example.toml missing — S4.4 not landed"

        for p in (repo_toml, example_toml):
            if not p.exists():
                continue
            with p.open("rb") as fh:
                data = tomllib.load(fh)
            # Scan TOML keys (not comments) — documenting a secret in a comment is allowed
            seen: set[str] = set()
            for section, value in data.items():
                if isinstance(value, dict):
                    for k in value:
                        seen.add(str(k).lower())
                else:
                    seen.add(str(section).lower())
            for secret_key in (
                "discord_token",
                "supabase_url",
                "supabase_key",
                "supabase_jwt",
                "database_url",
            ):
                assert secret_key not in seen, f"{p} must not contain secret key {secret_key!r} as a TOML key"

    def test_unknown_keys_warning_and_ignored(self, tmp_path: Path, caplog: pytest.Caplog) -> None:  # type: ignore[unresolved-attribute]
        _ = pytest  # noqa: F401 -- keep import alive for type checker

        try:
            from bot.operational_config import load_operational_config  # noqa: PLC0415 -- test probe
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        base = _valid_toml_content()
        # Inject unknown_key into existing [logging] (avoid duplicate-table TOML error)
        # and add a fresh unknown section at the end.
        base_with_unknown = base.replace(
            'level = "DEBUG"',
            'level = "DEBUG"\nunknown_key = 123',
        )
        content = base_with_unknown + '\n[unknown_section]\nfoo = "bar"\n'
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(content, encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            cfg = load_operational_config(cfg_path)
        # Unknown keys ignored — typed values still applied
        assert cfg.logging.level == "DEBUG"
        assert cfg.retention.tickets == 7
        # Must have logged a WARNING about unknown keys
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "unknown keys must log WARNING and be ignored"
        assert any("unknown" in r.getMessage().lower() for r in warnings)

    def test_env_never_feeds_operational_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _ = pytest  # keep import

        try:
            from bot.operational_config import load_operational_config  # noqa: PLC0415 -- test probe
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        # Set env vars that must NOT affect operational config
        monkeypatch.setenv("RETENTION_TICKETS", "999")
        monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(_valid_toml_content(), encoding="utf-8")
        cfg = load_operational_config(cfg_path)
        # File values win; env is ignored
        assert cfg.retention.tickets == 7
        assert cfg.logging.level == "DEBUG"

    def test_frozen_dataclass_tree_immutability(self, tmp_path: Path) -> None:
        try:
            from bot.operational_config import load_operational_config  # noqa: PLC0415 -- test probe
        except ModuleNotFoundError as err:
            raise AssertionError("bot/operational_config.py missing — S4.3 not landed") from err

        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(_valid_toml_content(), encoding="utf-8")
        cfg = load_operational_config(cfg_path)

        assert dataclasses.is_dataclass(cfg)
        # All leaves frozen
        for attr in ("logging", "limits", "timeouts", "retention", "flags"):
            leaf = getattr(cfg, attr)
            assert dataclasses.is_dataclass(leaf)
            assert leaf.__dataclass_params__.frozen is True
