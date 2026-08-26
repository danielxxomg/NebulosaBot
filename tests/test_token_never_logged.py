"""Token never logged at any level (operational-config delta — S0.7/S0.8).

The startup INFO line in ``bot/config.py`` logged the first 8 characters
of the Discord token. The spec requires that NO substring of the token
appear in ANY log record at ANY level, regardless of destination.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

import bot.config as config_mod
from bot.config import BotConfig

_TOKEN = "Sup3rS3cretTokenValue_ABCDEF1234567890abcdef"


class _RecordCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured_boot_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[_RecordCollector, Path]]:
    """Capture every log record emitted while from_env boots, at DEBUG.

    Uses an EMPTY env file so the missing-var WARNING path fires (the
    developer checkout ships a real .env that would otherwise satisfy every
    var) — proving even that record never echoes token/env material.
    """
    monkeypatch.setenv("DISCORD_TOKEN", _TOKEN)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "anon-key-not-secret-here")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    collector = _RecordCollector()
    root = logging.getLogger()
    config_logger = logging.getLogger("bot.config")
    previous_level = config_logger.level
    root.addHandler(collector)
    config_logger.addHandler(collector)
    old_root_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield collector, empty_env
    finally:
        root.removeHandler(collector)
        config_logger.removeHandler(collector)
        root.setLevel(old_root_level)
        config_logger.setLevel(previous_level)


def _token_fragments() -> list[str]:
    """Every contiguous window of the token with length >= 4."""
    return [_TOKEN[i : i + size] for size in range(4, len(_TOKEN) + 1) for i in range(len(_TOKEN) - size + 1)]


def test_boot_logs_contain_no_token_fragment(
    captured_boot_logs: tuple[_RecordCollector, Path],
) -> None:
    """GIVEN a configured token WHEN the bot config loads THEN no record leaks any fragment."""
    collector, empty_env = captured_boot_logs

    BotConfig.from_env(env_path=str(empty_env))

    assert collector.records, "boot must emit records for this test to be meaningful"
    fragments = _token_fragments()
    leaked: list[str] = []
    for record in collector.records:
        text = record.getMessage()
        for fragment in fragments:
            if fragment in text:
                leaked.append(f"{record.levelname}: {text!r}")
                break
    assert not leaked, f"token material leaked to logs: {leaked}"


def test_no_token_fragment_at_debug_level(
    captured_boot_logs: tuple[_RecordCollector, Path],
) -> None:
    """Redaction survives level changes: DEBUG capture stays clean too."""
    collector, empty_env = captured_boot_logs

    BotConfig.from_env(env_path=str(empty_env))

    debug_records = [r for r in collector.records if r.levelno >= logging.DEBUG]
    assert debug_records, "DEBUG-level capture must have seen records"
    for record in debug_records:
        assert _TOKEN not in record.getMessage(), "full token must never appear"
        assert _TOKEN[:8] not in record.getMessage(), "token prefix must never appear"


def test_config_module_has_no_token_logging_callsite() -> None:
    """Guard: the offending INFO callsite is gone from source."""
    src = inspect.getsource(config_mod)
    assert "(token:" not in src, "config.py still logs a token fragment"
