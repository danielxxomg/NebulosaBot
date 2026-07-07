# Exploration: Exhaustive Code/Architecture/Tooling Audit

## Current State

NebulosaBot is a Discord bot (Python 3.11+, discord.py 2.7.1, supabase 2.31.0, Pillow) with 7 cogs, 8 services, 2 listeners, 24 hybrid commands, 384 tests, and 74.59% coverage. It uses Supabase/PostgreSQL with Realtime CDC for cache invalidation. The codebase is organized with a clean cog → service → database layering.

---

## Findings by Severity

### 🔴 CRITICAL — Bugs That Cause Runtime Failures

#### C1. FK Violation: `member.userId_fkey` — No `user` Row Before Upsert

**File**: `migrations/001_initial_schema.sql:39`
**Evidence**: `member.userId` has `REFERENCES "user"(id) ON DELETE CASCADE`. Every `member` upsert (database.py:801, 877, 914, 957) will fail with a FK violation because the bot **never inserts into the `user` table**.

```
migrations/001_initial_schema.sql:39:  "userId" TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
```

The `user` table exists (`001_initial_schema.sql:27-32`) but there is **zero code** in the bot that inserts/upserts a `user` row. Searching for `ensure_user`, `insert_user`, `upsert_user` across all bot code returns **no results**.

Every path that touches `member` (XP gain, daily claim, warnings, leaderboard) calls `upsert` on `member` without first ensuring a `user` row exists. In Supabase Transaction Mode, FK enforcement is application-level (per AGENTS.md), but the code doesn't enforce it.

**Root cause**: The `user` table is vestigial — designed for the original ER diagram (`Diagramas/DiagramaEntidad-Relación.mmd:3`) but never populated by the bot. The `member` table should either:
1. Drop the FK to `user` (if `user` table is unused), OR
2. Add `ensure_user()` before every `member` upsert

**Evidence the FK is real**: `migrations/001_initial_schema.sql:39` explicitly defines `REFERENCES "user"(id)`. The error `member.userId_fkey` matches this constraint name exactly.

**Recommendation**: Drop the FK. The `user` table is not used by the bot for any purpose — it's a leftover from the original schema design. The bot stores user info (username, avatar) in Discord objects, not in a DB table.

#### C2. Realtime Watchdog Spam — `_event_count` Counts Only PROCESSED Events

**File**: `bot/core/realtime.py:503` and `bot/core/realtime.py:679`
**Evidence**: `_event_count` is incremented only at line 503, which is **after** the guild_id extraction and self-echo filter. If a CDC event arrives but is skipped (guild_id is None, or self-echo filtered), the counter stays at 0.

```python
# line 673-682: watchdog checks _event_count == 0
async def _watchdog_check_once(self) -> None:
    if self._status != "SUBSCRIBED" or self._subscribed_at == 0.0:
        return
    now = time.monotonic()
    elapsed = now - self._subscribed_at
    if elapsed >= WATCHDOG_DELAY and self._event_count == 0:
        logger.warning(
            "No CDC events received — check that supabase_realtime publication includes the required tables"
        )
```

The log from the live session shows `CDC event for None could not resolve a guild_id — skipping` firing repeatedly — these are RECEIVED events that fail extraction, but they don't reset the watchdog. The watchdog then fires every 30s with a misleading "No CDC events received" message.

**Fix**: Either (a) track a separate `_received_count` that increments on every `_cdc_callback`, or (b) increment `_event_count` at the top of `_handle_cdc` before any filtering.

#### C3. `_extract_guild_id` Returns `None` for `guild` Table CDC Events — `table` Is `None`

**File**: `bot/core/realtime.py:77-94` and `bot/core/realtime.py:462`
**Evidence**: The live log shows `CDC event for None could not resolve a guild_id — skipping`. The `%s` format in line 473 prints the `table` variable, which is `None`. This means `payload.get("table")` at line 462 returns `None`.

```python
# line 462: table = payload.get("table")
# line 472-475:
if guild_id is None:
    logger.warning(
        "CDC event for %s could not resolve a guild_id — skipping",
        table,
    )
```

This fires RIGHT AFTER every `Ticket panel deployed` / PATCH on the `guild` table (timestamps 19:04:01, 19:09:20, 19:09:50, 20:10:37). The Supabase Realtime SDK may not include a `table` field in the payload for certain event types, or the payload format differs from what the code expects.

**Investigation needed**: Add debug logging of the raw `payload` dict to see the actual structure. The code assumes `payload["table"]` exists, but the SDK may use a different key or structure.

#### C4. WebSocket 1006 Reconnection — No Explicit Reconnect Logic

**File**: `bot/core/realtime.py:539-572`
**Evidence**: At 20:29:21 the log shows `realtime._async.client: WebSocket connection closed with code: 1006` then re-SUBSCRIBED. The `_on_subscribe` callback handles `SUBSCRIBED`, `CHANNEL_ERROR`, and `TIMED_OUT`, but there's no explicit reconnection logic — it relies entirely on the Supabase Realtime SDK's built-in reconnect.

The health check (`_health_check_once`) enables poll fallback after 60s unhealthy, and `_on_subscribe` cancels the poll task on recovery. This is correct but fragile — if the SDK doesn't reconnect (e.g., after a prolonged outage), the bot silently degrades.

**Risk**: The SDK's reconnect behavior is not documented in the code. If the SDK gives up after N retries, the bot will be stuck in poll-fallback mode indefinitely without any alert beyond the initial warning.

---

### 🟡 WARNING — Correctness/Quality Issues

#### W1. `Diagramas/DiagramaSecuencia.mmd:29` — Still References Webhook Flow

**File**: `Diagramas/DiagramaSecuencia.mmd:29`
**Evidence**: `Web->>Bot: ⚡ POST /webhook/sync {guild_id, type: "config"}` — this is the OLD webhook flow, now replaced by Supabase Realtime CDC. The diagram is stale.

```mermaid
Web->>Bot: ⚡ POST /webhook/sync {guild_id, type: "config"}
```

#### W2. Ruff Config Missing Critical Rules (bak-cli Gap Analysis)

**File**: `pyproject.toml:77-87`
**Evidence**: Current ruff rules: `E, W, F, I, N, UP, B, SIM, RUF`. Missing equivalents for bak-cli's golangci-lint:

| bak-cli Linter | Python/Ruff Equivalent | Status |
|---|---|---|
| `bodyclose` | N/A (Python auto-closes) | ✅ N/A |
| `dupl` | No ruff equivalent | ❌ Missing (use `jscpd` or `radon`) |
| `errcheck` | `TRY` (tryceratops) | ❌ Missing |
| `errorlint` | `TRY` + `EM` (error-message) | ❌ Missing `TRY` |
| `funlen` (<80 lines) | `ERA` (eradicate) + manual | ❌ No threshold |
| `gocognit` (<35) | `C90` (mccabe) | ❌ Not configured |
| `gocritic` | `B` + `SIM` + `C4` | ⚠️ Partial |
| `gosec` | `S` (bandit via ruff) | ❌ Missing `S` |
| `govet` | `F` + `E` + `W` | ✅ Covered |
| `ineffassign` | `F841` (unused-variable) | ✅ Covered |
| `maintidx` (>20) | No ruff equivalent | ❌ Missing |
| `nestif` (<6) | `SIM` (simplify) | ⚠️ Partial |
| `nilerr` | `RET501` (return-nil) | ❌ Missing `RET` |
| `staticcheck` | `B` + `SIM` + `UP` | ✅ Covered |
| `unused` | `F841` + `RUF` | ✅ Covered |
| `exhaustive` | `ERA` + manual | ❌ Missing |
| `goconst` | No ruff equivalent | ❌ Missing (use `vulture`) |
| `gocyclo` (<15) | `C90` (mccabe) | ❌ Not configured |
| `misspell` | No ruff equivalent | ❌ Missing (use `codespell`) |
| `unconvert` | `UP` (pyupgrade) | ✅ Covered |
| `unparam` | `ARG` (unused-arguments) | ❌ Missing `ARG` |
| `usestdlibvars` | `UP` (pyupgrade) | ✅ Covered |

**Recommended ruff additions**:
```toml
[tool.ruff.lint]
select = [
    "E", "W", "F", "I", "N", "UP", "B", "SIM", "RUF",  # existing
    "S",     # bandit (security) — replaces standalone bandit for most rules
    "C4",    # comprehensions
    "C90",   # mccabe complexity
    "RET",   # return statements
    "T20",   # print() statements
    "ARG",   # unused arguments
    "DTZ",   # datetime timezone awareness
    "EM",    # error messages (no string literals in exceptions)
    "T10",   # debugger statements
    "TRY",   # exception handling (tryceratops)
    "RSE",   # raise statements
    "FLY",   # static join to f-string
    "PERF",  # performance anti-patterns
    "FURB",  # refurb modernization
]

[tool.ruff.lint.mccabe]
max-complexity = 15  # matches bak-cli gocyclo <15

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]  # allow assert in tests
```

#### W3. Mypy Not in Strict Mode

**File**: `pyproject.toml:92-101`
**Evidence**: `strict_optional = true` is set, but `strict = true` is NOT. The config also disables `attr-defined` project-wide. bak-cli's equivalent (staticcheck + govet) is much stricter.

```toml
[tool.mypy]
python_version = "3.11"
strict_optional = true
warn_unused_ignores = true
disable_error_code = "attr-defined"  # too broad — should be per-file
```

**Recommendation**: Enable `strict = true` and scope overrides per-file. The current `disable_error_code = "attr-defined"` at project level suppresses legitimate errors.

#### W4. Coverage Gate Too Low — 70% vs bak-cli's 75% Global / 80% Per-Package

**File**: `Makefile:29` and `pyproject.toml:53`
**Evidence**: `--cov-fail-under=70` in both `Makefile` and `pyproject.toml`. bak-cli uses 75% global / 80% per-package. Current actual coverage is 74.59%.

```makefile
test:
	uv run pytest --cov-fail-under=70
```

**Recommendation**: Raise to `--cov-fail-under=75` and add per-module gates.

#### W5. Pre-commit Hooks Scoped to Subset of Files

**File**: `.pre-commit-config.yaml:18`
**Evidence**: Ruff and mypy hooks only run on a hardcoded list of files (economy_service, config, conftest, tests). This means `bot/cogs/`, `bot/core/`, `bot/listeners/`, `bot/models/`, `bot/utils/` are **not linted on commit**.

```yaml
- id: ruff
  files: ^(bot/services/economy_service\.py|bot/config\.py|tests/conftest\.py|...)$
```

**Recommendation**: Expand to `^(bot/|tests/)` or remove the `files` filter entirely.

#### W6. CI Coverage Gate Missing — No `--cov-fail-under` in CI

**File**: `.github/workflows/ci.yml:65`
**Evidence**: CI runs `pytest --cov-fail-under=70` which matches the Makefile, but there's no per-module coverage gate. bak-cli has 80% per-package gates.

```yaml
- name: Tests with coverage
  run: uv run --extra dev pytest --cov-fail-under=70
```

#### W7. CI Missing Matrix for Python 3.13

**File**: `.github/workflows/ci.yml:27`
**Evidence**: Matrix tests `["3.11", "3.12", "3.14"]` but skips 3.13. The `pyproject.toml` classifiers list 3.11, 3.12, 3.13.

```yaml
python-version: ["3.11", "3.12", "3.14"]
```

#### W8. `tickets.py` Is 1953 Lines — Extreme Complexity

**File**: `bot/cogs/tickets.py` (1953 lines)
**Evidence**: This is the largest file in the codebase by 2x. bak-cli's `funlen` linter flags functions >80 lines. A 1953-line cog file almost certainly contains multiple functions exceeding this threshold. This is a major maintainability risk.

#### W9. `sentinel.py` Is 843 Lines — High Complexity

**File**: `bot/cogs/sentinel.py` (843 lines)
**Evidence**: Second-largest cog. Likely contains functions exceeding bak-cli's complexity thresholds.

---

### 🔵 SUGGESTION — Improvements

#### S1. `banana.png` at Repo Root — Wrong Location

**File**: `banana.png` (repo root, 12888 bytes)
**Evidence**: The code references `assets/images/banana.png` (`bot/cogs/ocio.py:25`) but the actual file is at the repo root. The `_BANANA_IMAGE_PATH` constant will fail `exists()` at runtime.

```python
# bot/cogs/ocio.py:25
_BANANA_IMAGE_PATH = Path("assets/images/banana.png")
```

**Fix**: Move `banana.png` to `assets/images/banana.png` (the directory exists: `assets/images/`).

#### S2. Tunnel Residues in Archived Openspec — Acceptable

**Evidence**: All webhook/tunnel references are in `openspec/changes/archive/` and `openspec/specs/cache-sync-webhook/spec.md`. These are historical records and SHOULD remain. The active code (`bot/`, `app.py`, `.env.example`) is clean — verified by `rg` returning no matches in `bot/`.

**One exception**: `Diagramas/DiagramaSecuencia.mmd:29` still references the webhook flow (see W1).

#### S3. `ticket_category` Table Not in SUBSCRIBED_TABLES

**File**: `bot/core/realtime.py:48-53`
**Evidence**: `SUBSCRIBED_TABLES` includes `guild`, `greeting_config`, `ticket`, `ticket_note`. The `ticket_category` table exists (`migrations/002_ticket_categories.sql`) and is queried by the bot (`database.py:635-649`), but it's NOT in the Realtime subscription.

From the Supabase publication query, `ticket_category` is NOT in the `supabase_realtime` publication either. This means changes to ticket categories via the dashboard won't invalidate the bot's cache — the 5-minute TTL is the only sync mechanism.

**Impact**: Low — ticket categories change infrequently. But if the dashboard adds category management, this will become a stale-cache issue.

#### S4. No `radon`/`vulture` for Complexity/Duplicate Detection

**Evidence**: bak-cli uses `dupl` for duplicate code detection and `gocognit`/`gocyclo` for complexity. ruff has `C90` (mccabe) but it's not configured. No duplicate code detection tool is configured.

**Recommendation**: Add `radon` for cyclomatic complexity and `vulture` for dead code detection. Or at minimum enable `C90` in ruff with `max-complexity = 15`.

#### S5. No `Dockerfile.ci` for Local CI Mirroring

**Evidence**: bak-cli has Docker CI. NebulosaBot has no Dockerfile at all. This is acceptable for a Discord bot (not containerized for production) but means local CI can't exactly mirror GitHub Actions.

#### S6. `requirements.txt` Exists But `uv.lock` Is Primary

**File**: `requirements.txt` exists alongside `uv.lock`
**Evidence**: The project uses `uv` as the primary package manager. Having both `requirements.txt` and `uv.lock` can cause drift. Consider removing `requirements.txt` or documenting its purpose.

#### S7. `Diagramas/DiagramaCasosUso.mmd` — Check for Stale Content

**File**: `Diagramas/DiagramaCasosUso.mmd`
**Evidence**: Should verify this diagram doesn't reference removed features (webhook, tunnel).

#### S8. No `ensure_user` Before Member Upserts — Design Decision Needed

**File**: `bot/core/database.py:801, 877, 914, 957`
**Evidence**: All member upserts go directly to the `member` table without ensuring a `user` row exists. The migration defines `member.userId REFERENCES "user"(id)`, but the bot never writes to `user`. This is the FK violation root cause (C1).

**Decision**: Either drop the FK or add `ensure_user()`. Since the `user` table stores `username`, `avatarUrl`, and `lastSeen` — all of which the bot gets from Discord objects — the table is vestigial. **Recommend dropping the FK.**

---

## Affected Areas

- `migrations/001_initial_schema.sql` — FK definition for member→user (C1)
- `bot/core/realtime.py` — Watchdog counter, extract_guild_id, reconnection (C2, C3, C4)
- `bot/cogs/ocio.py:25` — banana.png path mismatch (S1)
- `Diagramas/DiagramaSecuencia.mmd:29` — stale webhook reference (W1)
- `pyproject.toml` — ruff/mypy config gaps (W2, W3)
- `.pre-commit-config.yaml` — hook scope too narrow (W5)
- `.github/workflows/ci.yml` — missing Python 3.13, no per-module coverage (W6, W7)
- `bot/cogs/tickets.py` — 1953 lines, extreme complexity (W8)

## Approaches

### Approach A: Surgical Fixes (Low Effort)
Fix the 4 critical bugs (C1-C4) and the banana path (S1). Minimal scope, fast delivery.

- **Pros**: Fixes runtime failures immediately
- **Cons**: Doesn't address tooling debt
- **Effort**: Low

### Approach B: Full Audit Remediation (High Effort)
Fix all critical + warning + suggestion items. Upgrade ruff config, expand pre-commit scope, fix CI, restructure large cogs.

- **Pros**: Brings project to bak-cli-level rigor
- **Cons**: Large scope, risk of regressions, many files touched
- **Effort**: High

### Approach C: Critical + Tooling (Medium Effort)
Fix critical bugs (A) plus tooling improvements (W2-W6). Skip structural refactors (W8, W9).

- **Pros**: Fixes bugs AND prevents future regressions
- **Cons**: Large cogs remain complex
- **Effort**: Medium

## Recommendation

**Approach C** — Fix the 4 critical bugs and upgrade tooling. The large cog refactors (W8, W9) should be a separate change.

Priority order:
1. **C1** — Drop the `member.userId_fkey` FK (migration + code cleanup)
2. **C3** — Debug `_extract_guild_id` for `table=None` payloads
3. **C2** — Fix watchdog counter to track received events
4. **C4** — Add reconnection resilience logging
5. **S1** — Move `banana.png` to `assets/images/`
6. **W2** — Upgrade ruff config
7. **W3** — Enable mypy strict mode
8. **W5** — Expand pre-commit hooks
9. **W6** — Raise coverage gate

## Risks

- **C1 FK drop**: Requires a migration SQL file. If the `user` table is used by the dashboard, dropping the FK could break dashboard features. Verify dashboard doesn't query `user` table first.
- **C3 payload investigation**: Need to see the actual CDC payload structure. May require adding debug logging to production.
- **W2 ruff strictness**: Enabling new rules will likely surface existing violations. May need a debt-clearing pass.

## Ready for Proposal

**Yes** — with the following clarifications for the user:
1. Does the dashboard use the `user` table? (Determines whether to drop FK or add `ensure_user`)
2. Should the large cog refactors (tickets.py 1953 lines) be part of this change or a separate one?
3. Is there a way to capture a raw CDC payload for debugging C3?

---

## Supabase Publication Verification

**Verified via MCP**: The `supabase_realtime` publication includes exactly the 4 tables in `SUBSCRIBED_TABLES`:

| Table | Published | In SUBSCRIBED_TABLES | Match |
|---|---|---|---|
| `guild` | ✅ | ✅ | ✅ |
| `greeting_config` | ✅ | ✅ | ✅ |
| `ticket` | ✅ | ✅ | ✅ |
| `ticket_note` | ✅ | ✅ | ✅ |
| `ticket_category` | ❌ | ❌ | ✅ (both absent) |

The previous exploration's claim that "the supabase_realtime publication is not configured" is **CONFIRMED FALSE**. CDC events ARE arriving — the bug is in `_extract_guild_id` receiving `table=None`.
