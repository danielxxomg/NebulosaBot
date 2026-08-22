"""RED tests for PR3 Phase 1 — intents.voice_states + portal docs.

Strict TDD: these MUST fail before GREEN (voice_states flag missing).
"""

from __future__ import annotations

import pathlib


def test_intents_voice_states_enabled_in_main() -> None:
    """Spec voice-observatory: intents.voice_states is True after construction."""
    source = pathlib.Path("bot/__main__.py").read_text(encoding="utf-8")
    assert "intents.voice_states = True" in source, "bot/__main__.py must set intents.voice_states = True"
    # Also ensure the intent is not accidentally disabled.
    assert source.count("voice_states") >= 1


def test_portal_voice_states_prerequisite_documented() -> None:
    """Spec: docs state user MUST enable Voice States in Developer Portal."""
    candidates = [
        pathlib.Path("docs/MANUAL.md"),
        pathlib.Path("bot/__main__.py"),
        pathlib.Path("openspec/changes/voice-moderation-permissions/design.md"),
    ]
    haystack = ""
    for p in candidates:
        if p.exists():
            haystack += p.read_text(encoding="utf-8") + "\n"
    # Must mention Voice States intent and Developer Portal.
    assert "Voice States" in haystack or "voice_states" in haystack
    assert "Developer Portal" in haystack or "Discord Developer Portal" in haystack
    # Must convey prerequisite nature.
    assert "MUST enable" in haystack or "must enable" in haystack.lower()
