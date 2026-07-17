# Proposal: Guard Disabled Welcome Cards and Clear Blocking Typing Diagnostics

## Intent

Prevent disabled welcome cards from producing unexpected CTA messages while completing static cleanup. Empty messages remain silent; non-empty messages remain text-only. Global guard, localization, and card-enabled behavior remain unchanged.

## Proposal Question Round

Product questions are resolved: whitespace is empty, CTA resolution never overrides disabled-card text, and card-enabled behavior is unchanged. No open decisions remain.

## Scope

### In Scope
- Make the card-disabled welcome path format and send only non-empty text.
- Suppress CTA resolution for that path, regardless of channel validity or accessibility.
- Preserve regression coverage for empty, whitespace-only, non-empty, global-disabled, and card-enabled cases.
- Apply automatically to existing guilds without configuration or migration changes.
- Fix seven pre-existing mypy diagnostics in `bot/services/greeting_service.py` (channel narrowing, annotations, and unused ignores).
- Fix the pre-existing generic `Command` type-argument diagnostic at `bot/core/i18n.py:294`.

### Out of Scope
- Goodbye dispatch, migrations, new configuration, notices, or broad type cleanup.
- Changes to shared composition/resolution helpers, the canonical spec, runtime behavior, or unrelated files.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `greeting-config`: clarify welcome dispatch so a disabled card never emits CTA-only content or lets CTA-channel failures block non-empty text. The existing card-enabled contract remains unchanged.

## Approach

Follow exploration Approach A: format disabled-card text directly, apply the welcome-only whitespace gate, and skip CTA resolution. Preserve card composition and CTA behavior. Resolve only the eight identified mypy diagnostics: seven in the service and one `Command` annotation in i18n.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/services/greeting_service.py` | Modified | Guard disabled-card text and resolve seven pre-existing mypy diagnostics without runtime changes. |
| `bot/core/i18n.py` | Modified | Add the generic `Command` type argument at line 294. |
| `tests/test_greeting_service.py` | Safety net | Guard scenarios and preserved CTA behavior. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Card-enabled CTA behavior regresses | Low | Leave composition/resolution unchanged and run guard tests. |
| Typing cleanup changes behavior | Low | Limit edits to annotations, narrowing, and unused-ignore removal; run the full suite. |

## Rollback Plan

Revert the helper and typing edits; retain unrelated worktree content. No database, configuration, or migration rollback is required.

## Dependencies

- Existing formatter and Discord abstractions.

## Success Criteria

- [ ] Disabled card with empty/whitespace text sends nothing, even with a resolvable CTA.
- [ ] Disabled card with non-empty text sends only formatted text; CTA failure cannot block it.
- [ ] Global-disabled and card-enabled CTA contracts remain unchanged.
- [ ] Focused guard tests, full suite, Ruff, and `uv run mypy bot/services/greeting_service.py` pass cleanly, including `bot/core/i18n.py:294`.
