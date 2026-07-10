# Verification Report: Ticket UX & Branding Overhaul

**Change:** `ticket-ux-branding`
**Mode:** OpenSpec | Strict TDD (`uv run pytest`)
**Verification date:** 2026-07-09
**Implementation range:** `origin/master..HEAD` (7 commits, 45 files, +3,890 / -181)

## Verdict: FAIL

The complete suite passes and the principal implementation paths are present, but Strict TDD verification found required scenarios without passing covering tests and a checked core task whose cancellation contract is absent from both code and tests. The change is **not ready to archive**.

---

## Completeness

| Check | Result | Evidence |
|---|---:|---|
| Task checkboxes | 43/43 checked | `tasks.md` contains no unchecked task |
| Verified task completion | 42/43 | Task 2.3.1 is marked complete but lacks its required cancellation test and logging behavior |
| Delta specs read | 9/9 | brand-tokens, channel-naming, close-confirmation, close-countdown, docs-manual, ticket-invariants, ticket-service, ticket-views, unclaim-command |
| Design contracts inspected | Yes | `design.md` plus changed source and tests |
| Strict-TDD apply evidence | Present | Engram `sdd/ticket-ux-branding/apply-progress` |

### Checked task that is not substantively complete

`2.3.1` requires a test proving that `CancelledError` is logged, re-raised, and does not delete the channel. Neither `bot/services/ticket_service.py` nor `tests/test_ticket_service.py` contains `CancelledError`. The current implementation naturally propagates cancellation before deletion, but it does **not** log it as the design requires, and no maintained test proves the behavior.

---

## Execution Evidence

| Command | Result | Evidence |
|---|---|---|
| `uv run pytest` | PASS | 1,260 passed, 3 skipped, 8 warnings in 12.40s |
| Coverage (pytest addopts) | PASS | 85.28%; required 75% reached |
| `python -m py_compile bot/__main__.py` | PASS | Exit 0 |
| `uv run ruff check` on changed production files | WARNING | 12 lint errors |
| `uv run mypy bot` | WARNING | 9 errors total; 8 are in changed `embeds.py` / `views/tickets.py` |
| `git diff --check origin/master...HEAD` | WARNING | 5 trailing-whitespace lines in `review-ledger.md` |

The pytest warnings include unawaited-coroutine `RuntimeWarning`s. One is emitted by the new `test_create_ticket_channel_renames_with_sanitized_actual` coverage path; the suite still exits successfully.

---

## TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | `apply-progress` has all four PR tables |
| All test-bearing TDD rows have files | ✅ 13/13 | Every listed test file exists |
| RED confirmed | ✅ 13/13 | The reported test files were inspected |
| GREEN confirmed | ✅ 13/13 | All listed files ran successfully in the full pytest execution |
| Triangulation adequate | ⚠️ 12/13 | 2.3.1 reports three cases, but the required cancellation case is absent |
| Safety net for modified test files | ⚠️ 7/9 | 2.2.1 (`test_ticket_views.py`) and 3.2.1 (`contract/test_ticket_invariants.py`) were existing files but are recorded as `N/A (new)` |

**TDD compliance:** 4/6 checks fully pass. The task-level cancellation gap is CRITICAL.

### Test Layer Distribution

The apply evidence reports 214 change-related test cases: 198 unit and 16 integration. The full suite confirms their containing files execute successfully.

| Layer | Reported cases | Files / examples | Tools |
|---|---:|---|---|
| Unit | 198 | brand, embeds, helpers, service, views, invariants, cog color assertions | pytest, pytest-asyncio, mocks |
| Integration | 16 | ticket cog flow, auto-close wiring, manual documentation | pytest, pytest-asyncio, mocks |
| E2E | 0 | Not available by project capability | Not installed |
| **Total** | **214** | | |

### Assertion Quality

| File | Line(s) | Assertion pattern | Issue | Severity |
|---|---:|---|---|---|
| `tests/test_brand.py` | 18 | `assert mod is not None` | Redundant import-existence assertion; the import itself supplies the meaningful failure signal and no token value is asserted in this test | WARNING |
| `tests/test_manual.py` | 32-38, 44-50, 62-68, 74-81, 87-93 | `any(phrase in manual_text...)` | Broad keyword checks can pass from unrelated text and do not prove required headings, complete command coverage, or the specified Ticket System context | WARNING |

**Assertion quality:** 0 CRITICAL, 2 WARNING. No tautologies, ghost loops, or tests without a production/artifact call were found.

---

## Spec Compliance Matrix

| Capability / required scenario group | Runtime evidence | Source evidence | Status |
|---|---|---|---|
| Brand module exports six specified tokens | `tests/test_brand.py` passed | `bot/utils/brand.py` exports the specified hex values | PASS |
| Factory and ticket embeds use brand tokens | `tests/test_embeds.py` passed | `embeds.py` uses `ERROR`, `INFO`, `SUCCESS`, `WARNING` | PASS |
| Bot footer, guild footer, panel, and logging fallback | `test_embeds`, `test_ticket_views`, `test_logging_service` passed | Asset resolvers and caller wiring present | PASS |
| Manual close confirmation, cancel, timeout, owner-only interaction | `test_ticket_views.py` and `test_confirm_view.py` passed | `TicketActionsView` uses owner-bound ephemeral `ConfirmCancelView` | PASS |
| Manual one-message 5→1 countdown and silent auto-close | `test_ticket_service.py` and `test_tickets_cog.py` passed | `manual=True` calls `_countdown_and_delete`; auto-close passes `manual=False` | PASS |
| Standard, special-character, long, and fallback channel naming | `tests/test_ticket_helpers.py` passed | `sanitize_channel_name()` applies NFKD folding, slugging, fallback, and suffix-preserving truncation | PASS |
| Initial creation, reopen, and post-create rename use sanitized names | `tests/test_ticket_service.py` passed | Service centralizes name construction | PASS |
| Subticket uses sanitized `{category}-{username}-{number}` name | No test asserts the subticket name or sanitized `category_name` passed to the service | Source passes parent category to `create_ticket_channel()` | **CRITICAL — UNTESTED** |
| Claimer unclaims; state resets; audit is recorded | Service, invariant, and cog tests passed | `unclaim_ticket()` validates, updates `open`/`null`, and audits | PASS |
| Configured moderator-role user can run `/unclaim` | No passing command test uses a non-admin member with the configured cached moderator role | Cog contains a duplicated role-cache branch | **CRITICAL — UNTESTED** |
| Non-claimer/non-mod and unclaimed-ticket errors | Service, invariant, and cog tests passed | Permission and claimed-state guards present | PASS |
| Claim-on-claimed opens transfer confirmation; confirm transfers | `tests/test_ticket_views.py` passed | Owner-bound confirmation invokes `transfer_ticket()` | PASS |
| Manual exists and is non-empty | `tests/test_manual.py` passed | `docs/MANUAL.md` present | PASS |
| Manual required structural sections | No test checks the required heading set | Headings were inspected, but source inspection is not runtime proof in Strict TDD mode | **CRITICAL — UNTESTED** |
| Manual documents every command | No test inventories cog commands against the manual | Manual was inspected, but no executable completeness assertion exists | **CRITICAL — UNTESTED** |
| Manual documents close, unclaim, transfer, naming, branding | `tests/test_manual.py` passed | Ticket System text contains the specified flows | PASS WITH WARNING |

---

## Correctness

| Dimension | Result | Notes |
|---|---|---|
| Ticket state changes | PASS | Claim/transfer/unclaim paths use invariant/service checks; unclaim updates `claimedBy=None`, `status='open'` |
| Close lifecycle | PASS WITH WARNING | Confirmed manual close and silent auto-close are wired correctly; cancellation logging contract is missing |
| Naming safety | PASS | Sanitizer is Unicode-safe, bounded to 100 chars, and preserves the ticket suffix |
| Authorization | PASS WITH WARNING | Core claimer/mod invariant is correct; configured mod-role command path lacks runtime coverage |
| Documentation behavior | PASS WITH WARNING | New UX prose is accurate on inspection, but two mandatory documentation scenarios are untested |

---

## Design Coherence

| Design contract | Result | Evidence |
|---|---|---|
| Confirm callback acknowledges ephemeral response before service work | PASS | `bot/views/tickets.py:564-575` |
| Confirm view retains `original_response()` for timeout editing | PASS | Close and transfer flows assign `confirm_view.message` |
| Countdown owned by service; manual vs. auto distinct | PASS | `close_ticket_full(..., manual)` and auto-close caller |
| Cancellation logs and re-raises without deletion | FAIL | No `CancelledError` handling/logging exists; no runtime test exists |
| Unclaim uses shared mod-resolution predicate | WARNING | `is_mod_check()` exists, but `/unclaim` duplicates cache/role logic instead of sharing it |
| All direct embed users use brand tokens | WARNING | New `discord.Color.green()` / `greyple()` calls remain in `bot/views/tickets.py`; `confirmation.py` was not tokenized as proposed |
| Naming shared across create/reopen/subticket paths | PASS | All paths route through `sanitize_channel_name()` via the service |
| Spanish manual documents new UX | PASS | Sections 1 and 8 cover branding, confirm/dismiss, auto-close, unclaim, transfer, and naming |

---

## Changed File Coverage

Aggregate coverage of the changed production-file set is **83%** (1,832 / 2,210 statements). This is above both the OpenSpec 70% threshold and the project 75% test threshold.

| File | Line % | Uncovered lines | Rating |
|---|---:|---|---|
| `bot/cogs/core.py` | 64% | 79-80, 104, 115, 166-187, 209-211, 228, 233, 244, 263-296, 307-317 | ⚠️ Low |
| `bot/cogs/sentinel.py` | 73% | 80-86, 107, 134-135, 153, 167-175, 189-251, 277, 285-293, 341, 353-355, 367-368, 399, 405-407, 436, 445-447, 458-459, 512, 524-526, 537-538, 600, 611-627, 662, 673-689, 738-747, 768, 781, 786, 835 | ⚠️ Low |
| `bot/cogs/stellar.py` | 95% | 241-243, 268, 273 | ✅ Excellent |
| `bot/cogs/tickets.py` | 81% | 94-99, 113-115, 120-121, 126-127, 135, 147-148, 175-181, 199, 209-212, 218-221, 229, 235-238, 266, 271-274, 284-287, 293-296, 355-358, 411-412, 440-443, 453-454, 456-457, 482-483, 492-493, 505-507, 534-539, 549-552, 582-585, 598-608, 643-644, 651, 689-693, 741-742, 770-771, 784, 788 | ⚠️ Acceptable |
| `bot/cogs/utility.py` | 97% | 192, 197 | ✅ Excellent |
| `bot/listeners/xp_listener.py` | 85% | 111-112, 141-147, 160, 171-179, 194, 199 | ⚠️ Acceptable |
| `bot/services/logging_service.py` | 91% | 70, 131, 158, 183, 208, 227, 238, 255, 299, 319-320 | ⚠️ Acceptable |
| `bot/services/ticket_invariants.py` | 97% | 106, 267 | ✅ Excellent |
| `bot/services/ticket_service.py` | 83% | 147, 194, 249, 303, 308-309, 478-491, 560-561, 564-569, 577-578, 588-589, 601-602, 622, 641, 647-648, 706, 724-725, 913, 925, 942-946, 954-955, 995-1017, 1027-1028, 1059-1060 | ⚠️ Acceptable |
| `bot/utils/brand.py` | 100% | — | ✅ Excellent |
| `bot/utils/embeds.py` | 99% | 252 | ✅ Excellent |
| `bot/utils/ticket_helpers.py` | 86% | 99, 130-139, 154-163, 165-172 | ⚠️ Acceptable |
| `bot/views/tickets.py` | 82% | 95-105, 120-128, 132-133, 151-182, 316-319, 369-379, 417, 455-465, 479-480, 503-513, 529, 558, 576-586, 589, 619-620, 650-652 | ⚠️ Acceptable |

---

## Quality Metrics

- **Linter:** ⚠️ 12 errors on changed production files. These include unsorted imports in `core.py`, `tickets.py`, and `views/tickets.py`; direct style/line-length issues in `views/tickets.py`; and one missing `zip(..., strict=...)` argument.
- **Type checker:** ⚠️ 8 errors in changed files: nullable `bot.user`, unparameterized `dict` annotations, an untyped local, and nullable `interaction.message` access in `embeds.py` / `views/tickets.py`. One additional mypy error is in unchanged `bot/bot.py`.
- **Whitespace:** ⚠️ `review-ledger.md:3-7` has trailing whitespace.

These are non-blocking quality findings under the Strict-TDD verify rules, but should be resolved before release.

---

## Findings

### CRITICAL

1. **Task 2.3.1 is incomplete despite being checked.** The required `CancelledError` log/re-raise/no-delete test is absent, and the service has no cancellation logging branch. This violates the design contract and strict-TDD task evidence.
2. **Subticket naming is untested.** No passing test proves a subticket receives the sanitized `{category}-{username}-{number}` name, required by `channel-naming`.
3. **Configured moderator-role `/unclaim` flow is untested.** The only cog “mod” success test grants administrator permission; none exercises a non-admin with the configured cached mod role.
4. **Two mandatory manual scenarios are untested.** No runtime test verifies the required manual headings or inventories every bot command against `docs/MANUAL.md`.

### WARNING

1. Two modified test files are inaccurately marked `N/A (new)` in the TDD safety-net evidence.
2. `/unclaim` duplicates moderator-role resolution instead of using the shared predicate specified by the design.
3. New direct embeds in `bot/views/tickets.py` still use `discord.Color.green()` / `greyple()`; the proposed confirmation-view tokenization was not completed.
4. Pytest completes with eight warnings, including unawaited-coroutine warnings; lint, mypy, and diff-whitespace checks also report issues.
5. Changed-file coverage is below 80% for `bot/cogs/core.py` (64%) and `bot/cogs/sentinel.py` (73%).
6. The manual tests use broad keyword checks and do not independently prove their full requirements.

### SUGGESTION

1. Add an assertion that the manual countdown invokes five one-second sleeps, not only the message contents and deletion.
2. Give `PRIMARY` / `ACCENT` a documented production role or remove unused palette tiers after confirming product intent.

---

## Archive Readiness

**Not ready for `sdd-archive`.** Address all CRITICAL findings, update `tasks.md` truthfully, then rerun strict verification.
