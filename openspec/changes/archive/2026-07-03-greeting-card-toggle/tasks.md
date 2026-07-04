# Tasks: Greeting Card Toggle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~90-130 (30-50 bot + 60-80 tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-always |
| Chain strategy | not needed |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: not needed
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Implement card toggle with TDD + commit | PR 1 | Single commit; tests co-located with implementation |

## Phase 1: Welcome Card Toggle (TDD)

- [x] 1.1 RED — add 3 welcome card-toggle tests to `tests/test_greeting_service.py` inside `TestDispatchWelcome`:
  - `test_card_enabled_sends_welcome_card` — assert `generate_greeting_card` called, `channel.send` called with `file=`
  - `test_card_disabled_with_message_sends_text_only` — assert `generate_greeting_card` NOT called, `channel.send` called with `content=` only (no `file`)
  - `test_card_disabled_without_message_sends_nothing` — assert `channel.send` NOT called at all
- [x] 1.2 VERIFY RED — run `uv run pytest tests/test_greeting_service.py -k "test_card_enabled_sends_welcome_card or test_card_disabled_with_message_sends_text_only or test_card_disabled_without_message_sends_nothing"` → all 3 FAIL (card toggle not wired)
- [x] 1.3 GREEN — in `bot/services/greeting_service.py:dispatch_welcome()`, insert card-toggle branch after channel-not-found guard (line 116), before `avatar_url` (line 118). Pattern:
  ```python
  if not config.welcome_card_enabled:
      message_template = config.welcome_message or ""
      content = _format_template(message_template, member) if message_template else ""
      if content:
          await channel.send(content=content)
      return
  ```
- [x] 1.4 VERIFY GREEN — run `uv run pytest tests/test_greeting_service.py -k "TestDispatchWelcome"` → all PASS

## Phase 2: Goodbye Card Toggle (TDD)

- [x] 2.1 RED — add 3 goodbye card-toggle tests to `tests/test_greeting_service.py` inside `TestDispatchGoodbye`:
  - `test_card_enabled_sends_goodbye_card`
  - `test_card_disabled_with_message_sends_text_only`
  - `test_card_disabled_without_message_sends_nothing`
- [x] 2.2 VERIFY RED — run `uv run pytest tests/test_greeting_service.py -k "test_card_enabled_sends_goodbye_card or test_card_disabled_with_message_sends_text_only or test_card_disabled_without_message_sends_nothing"` → all 3 FAIL
- [x] 2.3 GREEN — in `bot/services/greeting_service.py:dispatch_goodbye()`, insert identical card-toggle branch after channel-not-found guard (line 159), before `avatar_url` (line 161)
- [x] 2.4 VERIFY GREEN — run `uv run pytest tests/test_greeting_service.py -k "TestDispatchGoodbye"` → all PASS

## Phase 3: Regression Guard (TDD)

- [x] 3.1 RED — add `test_disabled_skips_before_card_toggle` to `TestDispatchWelcome`:
  - config: `welcome_enabled=False`, `welcome_card_enabled=True`
  - assert `channel.send` NOT called, `generate_greeting_card` NOT called
- [x] 3.2 VERIFY RED — run `uv run pytest tests/test_greeting_service.py -k "test_disabled_skips_before_card_toggle"` → FAILS (test asserts behavior not yet asserted)
- [x] 3.3 VERIFY GREEN — run `uv run pytest tests/test_greeting_service.py -k "test_disabled_skips_before_card_toggle"` → PASSES (existing guard logic already handles this; test codifies the contract)

## Phase 4: Refactor

- [x] 4.1 REFACTOR — evaluate if welcome/goodbye card-toggle branches can share a `_send_text_only_if_message(channel, template, member)` helper. Extract only if it reduces duplication without adding indirection. Keep minimal.
- [x] 4.2 VERIFY — run `uv run pytest tests/test_greeting_service.py` → all existing + new tests PASS

## Phase 5: Full Suite + Commit

- [x] 5.1 VERIFY — run `uv run pytest` → full suite green
- [x] 5.2 VERIFY — run `make lint` (or `uv run ruff check bot/ tests/`) → no new violations
- [x] 5.3 VERIFY — run `make type` (or `uv run mypy bot/`) → no new type errors
- [x] 5.4 VERIFY — run `uv run pytest --cov=bot --cov-report=term-missing` → coverage >= 70% gate
- [ ] 5.5 COMMIT — `git add bot/services/greeting_service.py tests/test_greeting_service.py && git commit -m "feat(greeting): respect card toggles in dispatch"` — single work unit, tests co-located with implementation — DEFERRED to orchestrator (apply instructed not to commit; review-reliability runs first)
