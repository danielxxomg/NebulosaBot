# Tasks: Guard Disabled Welcome Cards from CTA-Only Sends

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 130–180 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Guard disabled CTA + typing cleanup | PR 1 | `uv run pytest tests/test_greeting_service.py -v --no-cov` | N/A — service-local, Discord send mocked | Revert `greeting_service.py`, `i18n.py:294`, + test file |

## Phase 1: RED — Failing Regression Tests

- [x] 1.1 `tests/test_greeting_service.py` — `test_global_disabled_ignores_card_toggle_and_message` (req1-s1) `welcome_enabled=False`, card on, non-empty → zero sends.
- [x] 1.2 `test_global_disabled_ignores_resolvable_cta` (req1-s2) CTA resolves → no CTA sent.
- [x] 1.3 `test_disabled_card_none_message_sends_nothing` (req2-s1,s2) `message=None`, resolvable CTA → nothing sent.
- [x] 1.4 `test_disabled_card_empty_string_sends_nothing` (req2-s3) `message=""` → nothing sent.
- [x] 1.5 `test_disabled_card_whitespace_only_sends_nothing` (req2-s4) `"   \n\t "` → zero-length.
- [x] 1.6 `test_disabled_card_template_substitutes_to_whitespace_sends_nothing` (req2-s5) empty nick → zero-length.
- [x] 1.7 `test_disabled_card_non_empty_sends_text_only_no_cta` (req3-s1) non-empty, resolvable CTA → text-only, no CTA call.
- [x] 1.8 `test_disabled_card_invalid_cta_does_not_block_text` (req3-s2) invalid CTA → text-only sent.
- [x] 1.9 `test_disabled_card_missing_cta_sends_text` (req3-s3) `onboarding_channel_id=None` → text-only.
- [x] 1.10 `test_disabled_card_empty_despite_resolvable_cta` (req4-s1) empty, resolvable CTA → nothing.
- [x] 1.11 `test_disabled_card_empty_despite_invalid_cta` (req4-s2) empty, invalid CTA → nothing.
- [x] 1.12 `test_disabled_card_preserves_localization` (req5) localized template → substituted value sent.
- [x] 1.13 `test_card_enabled_empty_msg_resolvable_cta_sends_cta_only` (req6-s1) card on, empty → CTA-only.
- [x] 1.14 `test_card_enabled_with_msg_appends_cta` (req6-s2) card on, non-empty → card + CTA.
- [x] 1.15 RED `TestDispatchWelcome::test_existing_guild_old_row_loads_without_write_or_notice` (req7-s1) pre-change row missing `onboardingChannelId`, readable defaults, no `upsert_greeting_config`, no card generation, no CTA resolution, no send; (req7-s2) existing silent-guild scenario preserved — nothing sent, no user-facing notice.

## Phase 2: GREEN — Implement CTA Guard

- [x] 2.1 `bot/services/greeting_service.py` — add `normalize_whitespace` kwarg to `_send_text_only_if_message()`. When `True`: direct `_format_template()`, gate on `formatted.strip()`, send unstripped. Verify 1.3–1.6, 1.10–1.11.
- [x] 2.2 When `normalize_whitespace=True`, skip CTA resolution. Verify 1.7–1.9.
- [x] 2.3 `dispatch_welcome()` card-disabled branch: pass `normalize_whitespace=True`. Verify 1.1–1.2, 1.12, 1.15.
- [x] 2.4 Card-enabled path untouched — 1.13, 1.14 pass unchanged.

## Phase 3: REFACTOR and Verify

- [x] 3.1 `uv run pytest tests/test_greeting_service.py -v` — 47 passed, no regressions.
- [x] 3.2 `uv run pytest` — full suite green.
- [x] 3.3 `uv run ruff check bot/services/greeting_service.py && uv run mypy bot/services/greeting_service.py` — clean.

## Phase 4: Static Typing Cleanup (8 bounded diagnostics)

Static RED/GREEN: mypy fails before, passes after. No runtime changes.

- [x] 4.1 RED: `uv run mypy bot/services/greeting_service.py` — 8 diagnostics (7 service + 1 i18n).
- [x] 4.2 GREEN: `bot/services/greeting_service.py` — narrowed `GuildChannel` → `Messageable`, added renderer annotation, removed inaccurate ignores; mypy clean.
- [x] 4.3 GREEN: `bot/core/i18n.py:294` — added `Command` generic arguments; mypy clean.
- [x] 4.4 `uv run pytest tests/test_greeting_service.py -v --no-cov` (47 passed) + `uv run pytest` (1766 passed, 3 skipped) — no regression.
