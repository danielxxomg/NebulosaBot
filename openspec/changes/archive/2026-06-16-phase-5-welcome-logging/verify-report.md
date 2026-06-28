# Verification Report: Phase 5 — Welcome/Goodbye + Audit Logging

**Change**: phase-5-welcome-logging  
**Version**: N/A  
**Mode**: Strict TDD  
**Branch**: feature/phase-5-welcome-logging  
**Verified on**: 2026-06-16  
**Verifier**: sdd-verify executor  

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 14 |
| Tasks complete | 14 |
| Tasks incomplete | 0 |

All 14 tasks from `tasks.md` are marked `[x]` in the artifact and reflected in the apply-progress memory (`sdd/phase-5-welcome-logging/apply-progress`).

---

## Build & Tests Execution

**Build**: ✅ Passed

```text
$ .venv/bin/python -m py_compile bot/__main__.py
(no output)
```

**Tests**: ✅ 229 passed / ❌ 2 failed / ⚠️ 2 teardown errors

```text
$ .venv/bin/python -m pytest -q
2 failed, 229 passed, 111 warnings, 2 errors in 2.73s

FAILED tests/test_greeting_service.py::TestDispatchGoodbye::test_disabled_skips_entirely
FAILED tests/test_greetings_cog.py::TestGoodbyeTestCommand::test_goodbye_test_card_generation_error
ERROR  tests/test_greeting_service.py::TestDispatchGoodbye::test_disabled_skips_entirely
ERROR  tests/test_greetings_cog.py::TestGoodbyeTestCommand::test_goodbye_test_card_generation_error
```

**Flake analysis**: Both failing tests pass when executed in isolation:

```text
$ .venv/bin/python -m pytest tests/test_greeting_service.py::TestDispatchGoodbye::test_disabled_skips_entirely \
    tests/test_greetings_cog.py::TestGoodbyeTestCommand::test_goodbye_test_card_generation_error -v
2 passed, 4 warnings in 0.02s
```

The failures are caused by a Python 3.14.5 + pytest-asyncio 1.4.0 event-loop teardown bug (`OSError: [Errno 22] Invalid argument` inside `selectors.EpollSelector.poll`). The same two tests flip depending on collection order when run with the Phase 5 subset. They are environmental flakes, not logic failures.

**Coverage**: ➖ Not available (`pytest-cov` / `coverage` not installed; `openspec/config.yaml` has `coverage.available: false`).

---

## Spec Compliance Matrix

### Greeting Configuration (`openspec/specs/greeting-config/spec.md`)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Greeting columns | Default values for new guild | `tests/test_greeting_config.py::TestGreetingConfigDefaults` | ✅ COMPLIANT |
| CRUD via GuildService | Update welcome channel | `tests/test_greeting_service.py::TestSaveConfig` / `TestGetConfig` | ✅ COMPLIANT |
| CRUD via GuildService | Disable welcome card | `tests/test_greeting_config.py::TestGreetingConfigDefaults` | ✅ COMPLIANT |
| Cache-first reads | Cache hit returns cached config | `tests/test_greeting_service.py::TestGetConfig::test_cache_hit_returns_cached_config` | ✅ COMPLIANT |
| Cache-first reads | Cache miss DB hit populates cache | `tests/test_greeting_service.py::TestGetConfig::test_cache_miss_db_hit_populates_cache` | ✅ COMPLIANT |
| Cache invalidation on update | Save invalidates cache | `tests/test_greeting_service.py::TestSaveConfig::test_save_config_upserts_and_invalidates` | ✅ COMPLIANT |

**Note**: The spec states greeting config is stored "in the guild record", but the design and implementation use a separate `greeting_config` table (consistent with `economy_config`). The implementation is coherent with the design; the spec wording is stale.

### Welcome/Goodbye (`openspec/specs/welcome-goodbye/spec.md`)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Welcome card on join | Member joins guild | `tests/test_greetings_cog.py::TestOnMemberJoin::test_calls_dispatch_welcome` | ✅ COMPLIANT |
| Welcome card on join | Welcome disabled | `tests/test_greeting_service.py::TestDispatchWelcome::test_disabled_skips_entirely` | ✅ COMPLIANT |
| Goodbye card on leave | Member leaves guild | `tests/test_greetings_cog.py::TestOnMemberRemove::test_calls_dispatch_goodbye` | ✅ COMPLIANT |
| Goodbye card on leave | Goodbye disabled | `tests/test_greeting_service.py::TestDispatchGoodbye::test_disabled_skips_entirely` | ✅ COMPLIANT |
| Card generation | Generate welcome card | `tests/test_image_service.py::TestGenerateGreetingCard` | ✅ COMPLIANT |
| Card generation | Missing avatar | `tests/test_image_service.py::TestGenerateGreetingCard::test_handle_missing_avatar_none` | ✅ COMPLIANT |
| Missing channel guard | Welcome channel missing | `tests/test_greeting_service.py::TestDispatchWelcome::test_missing_channel_skips` | ✅ COMPLIANT |

**Note**: The enabled send path of `GreetingService.dispatch_welcome()` / `dispatch_goodbye()` is only indirectly tested through `GreetingsCog`. There is no test asserting that `dispatch_welcome()` actually calls `ImageService.generate_greeting_card()` and `channel.send()` when enabled.

### Logging Service (`openspec/specs/logging-service/spec.md`)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Typed log methods | Moderation action log | `tests/test_logging_service.py::TestLogModerationAction` | ✅ COMPLIANT |
| Embed routing | Missing channel | `tests/test_logging_service.py::TestLoggingRoutingGuards::test_missing_log_channel_skips_send` | ✅ COMPLIANT |
| Embed routing | Logging disabled | `tests/test_logging_service.py::TestLoggingRoutingGuards::test_log_disabled_skips_send` | ✅ COMPLIANT |
| Content detail | Edit log detail | `tests/test_logging_service.py::TestLogMessageEdit` | ✅ COMPLIANT |
| Content detail | Delete log detail | `tests/test_logging_service.py::TestLogMessageDelete` | ✅ COMPLIANT |
| Channel visibility filter | Private channel event | `tests/test_logging_service.py::TestPrivateChannelFilter` | ✅ COMPLIANT |

### Audit Listener (`openspec/specs/audit-listener/spec.md`)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Event coverage | All seven events registered | (none for `on_member_join` / `on_member_remove` audit logging) | ❌ UNTESTED |
| Early-exit guards | Hidden channel skipped | `tests/test_audit_listener.py::TestOnMessageEditEarlyExits::test_skip_when_channel_not_loggable` | ⚠️ PARTIAL |
| Early-exit guards | Logging disabled skipped | `tests/test_logging_service.py::TestLoggingRoutingGuards` | ✅ COMPLIANT |
| Message edit logging | Edit captured | `tests/test_audit_listener.py::TestOnMessageEditEarlyExits::test_calls_log_message_edit_on_valid_message` | ✅ COMPLIANT |
| Message delete logging | Delete captured | `tests/test_audit_listener.py::TestOnMessageDeleteEarlyExits::test_calls_log_message_delete_on_valid_message` | ✅ COMPLIANT |
| Member and channel events | Member update captured | `tests/test_audit_listener.py::TestOnMemberUpdate` | ✅ COMPLIANT |

**CRITICAL**: The spec requires listeners for **seven** events (`on_message_edit`, `on_message_delete`, `on_member_join`, `on_member_remove`, `on_member_update`, `on_guild_channel_create`, `on_guild_channel_delete`). The implementation only registers **five** listeners; `on_member_join` and `on_member_remove` audit logging is not wired. `LoggingService.log_member_join()` and `log_member_leave()` exist but are never called.

### Mod Logging Delta (`openspec/changes/phase-5-welcome-logging/specs/mod-logging/spec.md`)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Log actions to channel | Log a warn | `tests/test_audit_listener.py::TestSentinelCogUsesLoggingService::test_warn_handler_calls_log_moderation_action` | ✅ COMPLIANT |
| Log actions to channel | Log via LoggingService | `tests/test_audit_listener.py::TestSentinelCogUsesLoggingService` | ✅ COMPLIANT |
| Skip logging when disabled | Logging disabled | `tests/test_logging_service.py::TestLoggingRoutingGuards::test_log_disabled_skips_send` | ✅ COMPLIANT |
| Skip logging when no channel | Missing log channel | `tests/test_logging_service.py::TestLoggingRoutingGuards::test_missing_log_channel_skips_send` | ✅ COMPLIANT |
| Include escalation actions | Log auto-mute | (no explicit escalation test) | ⚠️ PARTIAL |

**Compliance summary**: 21/23 scenarios fully compliant, 2 partial, 1 untested.

---

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Greeting config table + migration | ✅ Implemented | `migrations/004_greeting_config.sql` + `bot/models/greeting_config.py` |
| Greeting DB CRUD | ✅ Implemented | `bot/core/database.py::get_greeting_config()` / `upsert_greeting_config()` |
| LoggingService | ✅ Implemented | `bot/services/logging_service.py` — 9 typed methods + visibility filter |
| GreetingService | ✅ Implemented | `bot/services/greeting_service.py` — cache-first CRUD + dispatch |
| Welcome/goodbye card generation | ✅ Implemented | `bot/services/image_service.py::generate_greeting_card()` |
| GreetingsCog | ✅ Implemented | `bot/cogs/greetings.py` — listeners + `/welcome_test` + `/goodbye_test` |
| AuditListener | ⚠️ Partial | `bot/listeners/audit_listener.py` — only 5 of 7 required listeners |
| SentinelCog refactor | ✅ Implemented | `bot/cogs/sentinel.py` — 10 calls to `logging_service.log_moderation_action()`; `_log_action()` removed |
| Bot wiring | ✅ Implemented | `bot/bot.py` — `LoggingService`, `GreetingService`, `GreetingsCog`, `AuditListener` wired |

---

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Separate `greeting_config` table | ✅ Yes | Matches `economy_config` pattern |
| Extend `ImageService` for cards | ✅ Yes | Reuses gradient + `_fetch_avatar()` + `_load_font()` |
| Centralized `LoggingService` | ✅ Yes | Replaces `SentinelCog._log_action()` |
| `GreetingsCog` + `AuditListener` split | ✅ Yes | Clear separation of concerns |
| Channel visibility filter in service | ✅ Yes | `LoggingService.can_log_in_channel()` |
| AuditListener 5 listeners | ⚠️ Deviates from proposal/spec | Design says 5; proposal/spec say 7 |

**Deviations documented in apply-progress**:
- `AuditListener` always calls `log_member_update` (role diff handled by `LoggingService`).
- `on_message_delete` does not call `_can_log_in_channel()` in the listener; the service handles it.
- Lock/Unlock pass `ctx.author` as both target and moderator (existing behavior preserved).

---

## TDD Compliance (Strict TDD Active)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Found in Engram `sdd/phase-5-welcome-logging/apply-progress` |
| All tasks have tests | ✅ | 14/14 tasks have associated test files |
| RED confirmed (tests exist) | ✅ | All test files exist in the codebase |
| GREEN confirmed (tests pass) | ⚠️ | 229/231 pass; 2 environmental Python 3.14 asyncio teardown flakes pass in isolation |
| Triangulation adequate | ⚠️ | Most behaviors have multiple cases; `dispatch_welcome()` / `dispatch_goodbye()` enabled send path is only indirectly covered |
| Safety Net for modified files | ✅ | SentinelCog refactor used 214/217 safety net per apply-progress |

**TDD Compliance**: 5/6 checks passed.

---

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 93 | 6 | pytest + pytest-asyncio |
| Integration | 0 | 0 | not installed |
| E2E | 0 | 0 | not installed |
| **Total** | **93** | **6** | |

Phase 5 test files:
- `tests/test_logging_service.py` (28 tests)
- `tests/test_greeting_service.py` (15 tests)
- `tests/test_greetings_cog.py` (10 tests)
- `tests/test_audit_listener.py` (14 tests)
- `tests/test_image_service.py` (21 tests; 10 rank-card, 11 greeting-card)
- `tests/test_greeting_config.py` (11 tests)

---

## Changed File Coverage

Coverage analysis skipped — no coverage tool detected (`coverage` / `pytest-cov` not installed; `openspec/config.yaml` has `coverage.available: false`).

Changed files for this phase:
- `migrations/004_greeting_config.sql`
- `bot/models/greeting_config.py`
- `bot/core/database.py`
- `bot/services/logging_service.py`
- `bot/services/greeting_service.py`
- `bot/services/image_service.py`
- `bot/cogs/greetings.py`
- `bot/cogs/sentinel.py`
- `bot/listeners/audit_listener.py`
- `bot/bot.py`
- `tests/test_logging_service.py`
- `tests/test_greeting_service.py`
- `tests/test_greetings_cog.py`
- `tests/test_audit_listener.py`
- `tests/test_image_service.py`
- `tests/test_greeting_config.py`

---

## Assertion Quality

✅ All assertions verify real behavior. No tautologies, ghost loops, or mock-only tests were found in the Phase 5 test files.

Minor observations:
- `tests/test_greetings_cog.py` asserts `embed.color.value == 0xE74C3C` for error embeds — this couples to the concrete error color constant but verifies visible error styling.
- `tests/test_greeting_service.py` Phase 1 dispatch guard tests are shallow (only verify no exception / DB call) but are supplemented by Phase 2 `GreetingsCog` tests.

---

## Quality Metrics

**Linter**: ➖ Not available (ruff/flake8/pylint not installed).  
**Type Checker**: ➖ Not available (mypy not installed).  

Manual static note: `bot/services/greeting_service.py` has unusual indentation in the `__init__` parameter list (`image_service` is under-indented relative to `db` and `cache`). This is cosmetic and does not affect runtime.

---

## Issues Found

### CRITICAL

1. **AuditListener does not implement 2 of 7 required events.**  
   The `audit-listener` spec and proposal require listeners for `on_message_edit`, `on_message_delete`, `on_member_join`, `on_member_remove`, `on_member_update`, `on_guild_channel_create`, and `on_guild_channel_delete`. The implementation only registers 5 listeners; `on_member_join` and `on_member_remove` audit logging is missing. `LoggingService.log_member_join()` / `log_member_leave()` exist but are never invoked. This breaks the spec requirement "All seven events registered" and the proposal success criterion "All 7 audit events produce log embeds".

### WARNING

2. **Python 3.14 asyncio teardown flakes.**  
   Two tests fail non-deterministically when the full suite runs due to a `selectors.EpollSelector.poll` `OSError: [Errno 22]` during pytest-asyncio teardown. Both pass in isolation. This is an environment/dependency issue, not a code bug, but it prevents a clean CI signal.

3. **Spec/design mismatch on greeting config storage.**  
   The `greeting-config` spec says settings are stored "in the guild record", but the design and implementation use a separate `greeting_config` table. The implementation is correct per design; the spec should be updated.

4. **Weak triangulation on enabled greeting dispatch.**  
   `GreetingService.dispatch_welcome()` / `dispatch_goodbye()` have no test asserting the enabled path actually calls `ImageService.generate_greeting_card()` and `channel.send()`. The behavior is only indirectly covered through `GreetingsCog` listener delegation.

5. **No escalation-specific moderation logging test.**  
   The mod-logging delta requires automatic escalation actions to be logged. The existing SentinelCog approval test only exercises `/warn`; an auto-mute escalation path is not explicitly covered.

### SUGGESTION

6. Add `on_member_join` / `on_member_remove` listeners to `AuditListener` that delegate to `LoggingService.log_member_join()` / `log_member_leave()`.
7. Update the `greeting-config` spec to reflect the separate `greeting_config` table.
8. Add a direct unit test for `GreetingService.dispatch_welcome()` / `dispatch_goodbye()` enabled path.
9. Consider pinning `pytest-asyncio` or adding an event-loop fixture workaround for Python 3.14 flakes.
10. Add `pytest-cov` / `coverage` to the dev dependencies so changed-file coverage can be reported in future phases.

---

## Verdict

**FAIL**

The implementation is functionally complete against the 14 tasks and follows the design, but it violates a required spec scenario: the `AuditListener` must listen to seven Discord events per the `audit-listener` spec and proposal, yet `on_member_join` and `on_member_remove` audit logging is not wired. This is a CRITICAL spec gap. Once member join/leave audit listeners are added (or the spec is officially reduced to five events), the change can be re-verified and will likely pass with warnings only.
