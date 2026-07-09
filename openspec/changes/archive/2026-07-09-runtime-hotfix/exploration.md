## Exploration: runtime-hotfix

### Current State

Three production bugs confirmed from runtime logs. All are code-level defects, not infrastructure. The bot continues running in degraded mode (TTL-only cache, broken XP cooldown, broken ticket audit) but no crash loop.

**Bug 1 — ticket_audit table missing (BLOCKER, ops-fixed, code/docs need parity)**
- `ticket_service.py` `claim_ticket` (line 241) and `close_ticket` (line 192) call `insert_audit_row` AFTER mutating the ticket.
- If audit insert fails, the entire function raises — but the ticket is already mutated in Supabase. The cog gets an unhandled exception, user sees a raw error, and the UI action (channel delete on close, role assignment on claim) never runs.
- Migration `005_ticket_audit.sql` was never applied under that name (remote had different 005). Ops applied `012_ticket_audit` live. Local `migrations/012_ticket_audit.sql` exists (untracked).

**Bug 2 — Realtime `_on_connect_error` AttributeError (CRITICAL)**
- `realtime.py` line 481: `self._client._on_connect_error` — accesses a private SDK attribute directly.
- Newer `realtime-py` versions renamed or removed this attr. `AttributeError` at line 481 aborts `start()` in `bot.py` line 282.
- Exception is caught by `_start_realtime` (line 287), subscriber set to `None`, bot continues with TTL-only cache.
- Later log shows "Realtime channel SUBSCRIBED" — the `subscribe()` call at line 381 succeeded before `_wire_close_logging` at line 383. So the channel IS subscribed but health/poll/watchdog tasks (lines 385-387) are never created because the exception aborts before them.

**Bug 3 — XP gain datetime TypeError (CRITICAL)**
- `economy_service.py` line 134: `(now - last_gain).total_seconds()` — `now` is `datetime`, `last_gain` is a raw ISO string from Supabase.
- `claim_daily` (line 194-203) already has a `_to_datetime` helper that handles this. `gain_xp` does NOT use it.
- `Member.from_db_row` (line 40) assigns `lastXpGain` raw from the row without parsing.

### Affected Areas

- `bot/core/realtime.py` (lines 473-503) — `_wire_close_logging` accesses `client._on_connect_error` directly; needs defensive getattr or try/except
- `bot/services/economy_service.py` (lines 130-134) — `gain_xp` cooldown check uses raw string without datetime parsing
- `bot/services/economy_service.py` (lines 193-203) — `_to_datetime` helper exists but is local to `claim_daily`
- `bot/models/member.py` (lines 28-41) — `from_db_row` assigns raw timestamps without parsing
- `bot/services/ticket_service.py` (lines 169-199) — `close_ticket` audit failure aborts UI after mutation
- `bot/services/ticket_service.py` (lines 219-243) — `claim_ticket` audit failure aborts UI after mutation
- `migrations/012_ticket_audit.sql` — exists locally, untracked, needs git tracking
- `migrations/005_ticket_audit.sql` — stale file, never applied, candidate for removal or archival note
- `tests/test_realtime.py` (lines 219, 1027-1065) — test mock has `_on_connect_error` pre-set; new test needed for missing attr
- `tests/test_economy_service.py` — needs test for string-type `lastXpGain` in `gain_xp`

### Approaches

#### 1. Realtime close logging resilience

**A. getattr guard** — Wrap `_on_connect_error` access in `getattr(client, "_on_connect_error", None)`.
- Pros: Minimal change, no new abstraction, handles any SDK version.
- Cons: Silently disables close logging if attr is gone — less debuggable.
- Effort: Low

**B. try/except around _wire_close_logging** — Catch `AttributeError` in the method, log a warning, continue.
- Pros: Explicit failure signal in logs, rest of `start()` continues (health/poll/watchdog tasks get created).
- Cons: Slightly more code.
- Effort: Low

**Recommendation**: B. The current bug is that `_wire_close_logging` at line 383 throws and aborts lines 385-387 (health/poll/watchdog tasks). Wrapping the method body in try/except means the channel stays subscribed AND the background tasks start. Log a WARNING so ops knows close-logging is degraded.

#### 2. XP gain datetime parsing

**A. Reuse `_to_datetime` inline in `gain_xp`** — Copy the same pattern from `claim_daily`.
- Pros: Minimal change, follows existing pattern.
- Cons: DRY violation; `_to_datetime` is a nested function, can't be shared as-is.
- Effort: Low

**B. Extract `_to_datetime` to a shared utility** — Move to `bot/utils/time.py` or similar, import in both methods.
- Pros: DRY, single source of truth for ISO string parsing.
- Cons: Slightly larger scope, new module.
- Effort: Low-Medium

**C. Fix `Member.from_db_row` to parse timestamps** — Centralize in the model so all consumers get `datetime` objects.
- Pros: Fixes the root cause; any future code using Member won't hit this.
- Cons: Larger blast radius — every consumer of `from_db_row` now gets `datetime` instead of `str`. Need to verify no code compares with `None` using string semantics.
- Effort: Medium

**Recommendation**: C is the right long-term fix but risky for a hotfix. Do **A+B combined**: extract `_to_datetime` to a small shared helper (`bot/utils/timeparse.py`), use it in both `gain_xp` and `claim_daily`. Then fix `Member.from_db_row` as a follow-up. This keeps the hotfix small and the fix centralized.

#### 3. Ticket audit resilience (post-mutation audit failure)

**A. Best-effort audit (try/except + log)** — Wrap `insert_audit_row` calls in try/except, log the error, continue with the UI action.
- Pros: Ticket operations never fail due to audit. User experience is unaffected. Audit gaps are logged for ops.
- Cons: Silent data loss — an audit row is missing. If audit table is down for extended period, the audit trail has holes.
- Effort: Low

**B. Hard fail (current behavior)** — Audit failure aborts the operation.
- Pros: Audit trail is guaranteed complete (or the operation doesn't happen).
- Cons: Already proven broken in production — user can't claim/close tickets when audit table is missing or slow. Operation is already mutated in DB but UI never completes.
- Effort: N/A (status quo)

**C. Transactional (audit before mutation)** — Move audit insert before the mutation. If audit fails, mutation never happens.
- Pros: Atomic semantics — either both happen or neither.
- Cons: Changes the audit semantics (audit row would appear before the action completes). Also, Supabase Transaction Mode has no FK enforcement, so this doesn't buy true atomicity across two tables.
- Effort: Medium

**Recommendation**: **A**. Audit is a log, not a business invariant. The spec says "audit on every operation" but a missing audit row is an ops problem, not a user-facing failure. The current behavior (mutation succeeds, audit fails, user sees error, UI action skipped) is strictly worse than (mutation succeeds, audit fails silently, UI action proceeds, ops gets a warning log). Wrap each `insert_audit_row` call in a `try/except Exception` that logs at WARNING level.

#### 4. Migration repo parity

- `migrations/012_ticket_audit.sql` is untracked — `git add` it.
- `migrations/005_ticket_audit.sql` is stale (never applied, different 005 exists remotely). Options:
  - **A. Delete it** — clean, but loses the original intent.
  - **B. Rename to `005_ticket_audit_NEVER_APPLIED.sql`** — documents the history.
  - **C. Leave it** — confusing, future devs might try to apply it.
- **Recommendation**: A. The content is identical to 012. Git history preserves the file. Delete 005, track 012.

### Recommendation

**Single focused hotfix PR** with these changes (in order):

1. **Ticket audit resilience** — Wrap `insert_audit_row` calls in `claim_ticket`/`close_ticket` with try/except + WARNING log. ~10 lines changed.
2. **Datetime parsing** — Extract `_to_datetime` to `bot/utils/timeparse.py`, use in `gain_xp` cooldown check. ~15 lines new + 3 lines changed.
3. **Realtime close logging** — Wrap `_wire_close_logging` body in try/except AttributeError + WARNING log. ~5 lines changed.
4. **Migration parity** — `git add migrations/012_ticket_audit.sql`, delete `migrations/005_ticket_audit.sql`.

Total estimated diff: ~50-70 lines. Well within 400-line review budget. No chained PRs needed.

### Risks

- **Blast radius of audit resilience**: Wrapping audit in try/except means audit gaps are silent. Mitigated by WARNING-level logs + existing monitoring.
- **Datetime helper extraction**: New module `bot/utils/timeparse.py` touches a shared concern. Risk is low — it's a pure function with no side effects.
- **Realtime SDK version**: The fix handles missing `_on_connect_error` gracefully, but we don't know which SDK version removed it. If the attr was renamed (not removed), the fix still works because we skip wrapping entirely.
- **Test coverage**: Existing tests mock `_on_connect_error` into existence. Need new tests for the missing-attr path and string-type datetime path.

### Ready for Proposal

**Yes.** Scope is tight, all root causes verified in code, approaches are clear. The orchestrator should proceed to `sdd-propose` with:
- Change name: `runtime-hotfix`
- Scope: 4 bugs, ~50-70 line diff, single PR
- No UX changes, no new features
- Strict TDD: tests first for each fix
