# Exploration: cycle-4-debt-zero

Date: 2026-08-22 · Mode: read-only investigation · Store: openspec

## Current State

- Sentinel (`bot/cogs/sentinel.py`, 1362 lines) gates commands with two systems:
  `@can_check("moderation.ban")` already on `ban` (L742), `tempban` (L1085), `unban` (L1193);
  `@is_mod()` still on `warn` (L285), `unwarn` (L436), `mute` (L514), `unmute` (L597),
  `kick` (L648), plus `lock` (L849), `unlock` (L924), `modlogs` (L1008) which the brief
  says NOT to touch. `is_mod()` already honors `moderation.*` matrix grants additively
  (`bot/utils/checks.py:380-408`, `_is_mod_via_matrix`), so conversion is outcome-compatible.
- Auto-escalation lives inline in the `warn` command body: MUTE branch L332-369 (~38 lines),
  KICK branch L370-406 (~37 lines), identical shape: Discord action → `insert_infraction` →
  `log_moderation_action` → i18n success msg; both catch `discord.Forbidden` → failed msg.
  `InfractionService` (`bot/services/infraction_service.py`) is `__slots__=("_db",)` and
  already returns `EscalationAction` from `check_escalation()`. Services importing discord
  is established practice (7 of 8 services do).
- jscpd is NOT new: `.github/workflows/code-quality.yml:34-38` already runs
  `npx jscpd@4.0.1` (bot/ threshold 5, tests/ threshold 10) as report-only with
  `continue-on-error: true`. Node v26.3.0 + npm + pnpm + bunx available locally.
  Item B is therefore a *promotion* (CI advisory → prek blocking with baseline/ratchet),
  not an adoption.
- `prek.toml:25` `uv-check` hook runs `uv check`; on uv 0.12.5 this now emits an
  experimental warning and runs TYPE CHECKING. `ty` already runs as its own pre-commit
  hook (`prek.toml:23`), so dropping `uv-check` for `uv lock --check` (verified: works,
  "Resolved 76 packages") loses nothing.
- `pyproject.toml`: `[tool.ruff]` has `preview = true` but no `explicit-preview-rules`,
  no `required-version`; selected families lack ASYNC/BLE/G/A/PT. `[tool.ty]` has no
  `[tool.ty.terminal]`; blanket overrides on `bot/cogs/**` and `tests/**`.
- AGENTS.md sections: Python General, Discord.py, Architecture, Naming, Error Handling,
  Database, Testing, Anti-patterns, GGA Review Discipline, Domain Notes.

## Item-by-Item Verification (Section C brief)

| # | Item | Verified at | Classification |
|---|------|-------------|----------------|
| C1 | `tickets.timer.*` missing | Used 9× (`tickets.py` L332/335/374/377/1008/1014, `ticket_repair_service.py` L960/970, `time.py` L153-154 `unit_{unit}`); key absent from BOTH `bot/locales/es.json` and `en.json`. `t()` returns the RAW KEY on miss → users literally see "tickets.timer.scheduled_title" in Discord. **Live user-facing bug.** | Trivial + needs key inventory (9 keys incl. dynamic `unit_{second,minute,hour,day}`) |
| C1b | `ocio.8ball.embed_title` | `ocio.8ball` has only `r1`–`r20` in both locales; `embed_title` missing | Trivial |
| C1c | key-coverage test for `t()` | No test iterates `t()` keys vs locale JSON (existing `tests/test_*_i18n.py` are per-cog behavioral) | Mechanical; must handle dynamic keys (`unit_{unit}`, `r{n}`) via allowlist/pattern |
| C2 | kick/ban final ephemeral vs tempban permanent | kick final = `edit_message` on ephemeral confirm only (L694); ban same (L798); tempban edits ephemeral AND sends permanent channel embed (L1155). `ephemeral-standard` spec: "Mod action … permanent in the channel". kick/ban violate it | Mechanical — replicate tempban's two-step pattern |
| C3 | spec close-confirmation vs ConfirmCancelView | `close-confirmation` spec + `confirm-dialog` spec both mandate ephemeral dialogs; ConfirmCancelView docstring says "Ephemeral view", `timeout=30`, non-persistent (fine: always attached in-session). Conflict is only in the *final-result* wording, resolved by C2's unification | Design-lite — spec delta clarifying dialog=ephemeral, result=permanent |
| C4 | error handlers without logging | `bot/bot.py:374` `on_app_command_error` — error param literally named `_error` and discarded; `on_command_error` (L404) sends embeds, never logs. Violates AGENTS.md "Log full exceptions" | Trivial |
| C5 | expire_tempbans retry gap | `infraction_service.py:220-227`: `unban_fn` failure logged non-fatal, then `deactivate_infraction` runs anyway → ban stays on Discord but infraction deactivated, never retried | Design-needing: reorder (deactivate only on unban success) or add `unban_failed` flag + retry scan |
| C6 | `__import__("io")` in ocio.py | `ocio.py:86` `fp=__import__("io").BytesIO(data)` | Trivial (`import io`) |
| C7 | no-op `if resp == key` | `ocio_service.py:105` | Trivial (verify intent first — may be leftover of a fallback check) |
| C8 | dead aliases `_err/_ok/_info` | `embeds.py:223-232`, already carry `# noqa: F811` | Trivial delete |
| C9 | stale comments | realtime.py L745-753 (mock-era `.or_` fallback comments); voice_listener.py L140-141 ("no-op in the…" second-eviction); bot.py L216/224/244/256 (duplicated `3d`/`3f` markers) | Trivial |
| C10 | /unban duck-typing | sentinel.py L1236-1240: `discord.Object` + monkey-patched `.mention`/`.name` with `type: ignore[attr-defined]` | Trivial — small `UnbanTarget` dataclass |
| C11 | tempban expires_at drift | sentinel.py L1108: `expires_at` computed BEFORE ConfirmCancelView (30s timeout) → DB `expiresAt` ≠ real ban start | Mechanical — recompute inside `_do_tempban` |
| C12 | log noise | `tickets.py:100` logs "checking due tickets" every cycle; `logging_service.py:270-281` sends embed even at `count == 0` | Trivial (guard `count > 0`; demote loop info to debug) |
| C13 | stellar docstring EN vs locale_str ES | `stellar.py:1` English docstring, Spanish `locale_str` descriptions | Trivial (align docstring; locale_str stays ES by design) |
| C14 | test_bot_probe PARTIAL | `tests/test_bot_probe.py` simulates the probe INLINE (re-implements fallback in the test, L60-72 admits "we test setup_hook wiring via patch") — self-fulfilling, never exercises `NebulosaBot.setup_hook` | Mechanical — patch DB/cache and call real `setup_hook` |

## Ruff Findings (verified today, uv run ruff)

- BLE001: **38 in bot/ + 1 in scripts/ + 0 in tests/** (brief said 76 — stale or
  different-scope count; tests/ currently has zero blind-excepts).
- ASYNC240 ×5: **ALL in tests/** (`test_bot_probe.py:89`, `test_pr3_ocio_service_red.py:78`,
  `test_remediation_final_partials.py:149`, `test_s2d1_context_typing_chars.py:111`,
  `test_schema_inventory_verifier.py:261`) — blocking-path-in-async in tests is usually
  intentional simulation → needs narrow per-file-ignores, not bot/ fixes.
- G201 ×3, A002 ×5, PT011 ×8, PLW1510 ×17 (exact match to brief).
- PLC0415: **67 in bot/** (brief said 983 repo-wide) — advisory-only conclusion unchanged.
- PT family also surfaces PT018 ×109, PT001 ×12, PT022 ×2 etc. — auto-fixable noise to
  triage before making PT selective-blocking.

## Approaches

### A) Sentinel hardening

1. **Decorator swap + `InfractionService.apply_escalation()`**
   - Replace 5 `@is_mod()` with `@can_check("moderation.warn"/"moderation.mute"/"moderation.kick")`;
     extract escalation into the service:
     `async def apply_escalation(self, *, guild_id: str, member: discord.Member, moderator: discord.Member, escalation: EscalationAction, unban-free) -> str`
     returning the i18n message fragment; cog keeps only `ctx.send`. i18n `t()` stays callable
     from service (established: `ticket_repair_service.py` calls `t()`).
   - Pros: single dedup (~75→~40 lines), business logic out of cog (AGENTS.md Architecture),
     matrix-gated commands consistent with ban/tempban/unban.
   - Cons: service gains `discord.Member` dependency (already normal); tests asserting
     `is_mod` on those 5 commands must migrate to matrix semantics.
   - Effort: Medium
2. **Cog-private helper only (no service move)**
   - Dedup into `SentinelCog._apply_escalation()`.
   - Pros: smallest diff. Cons: business logic stays in cog (anti-pattern per AGENTS.md);
     still needs the same test churn for decorators.
   - Effort: Low

### B) jscpd promotion

1. **prek local hook + baseline file + ratchet in CI**
   - `prek.toml` pre-push hook `uv run scripts/jscpd_check.py` (or `npx jscpd@4.0.1 … --threshold` read
     from a committed `reports/jscpd-baseline.json`); CI job fails only if duplication % >
     baseline (ratchet down over time). Keep dashboard/web advisory-only.
   - Pros: no new dependency in uv lock; reuses existing npx pin; ratchet is one JSON number.
   - Cons: requires node in pre-push path (present locally; CI already has setup-node).
   - Effort: Medium
2. **uvx/pip jscpd alternative**
   - jscpd has no maintained pip port of equal fidelity; `uvx jscpd` is not a thing (npm tool).
   - Effort: n/a — rejected.

### F) Toolchain

1. F1: swap `uv check` → `uv lock --check` in prek.toml; `ty` stays as its own pre-commit hook (already there).
2. F2: add `explicit-preview-rules = true`, `required-version` (pin to ruff 0.15.20 from lock);
   add ASYNC/BLE/G/A blocking after fixing bot/ findings (BLE001 ×38, G201 ×3, A002 ×5);
   ASYNC240 needs 5 narrow test ignores or fixes; PT selective = PT011 only initially
   (8 sites); PLC0415 + PLW1510 documented advisory (67 / 17).
3. F3: `[tool.ty.terminal] error-on-warning = true`; live warning to fix first:
   `invalid-argument-type is_mod_check` at `bot/cogs/ticket_integrity_flow.py:73`;
   then narrow `bot/cogs/**` / `tests/**` overrides toward per-file exceptions.

### D) AGENTS.md V2→V3

Slot additions: `cache_key()` mandate → Architecture; `IF NOT EXISTS` migrations → Database;
`t()` i18n mandatory in cogs + `can_check` strict on all matrix-gated commands → Discord.py.
GGA Review Discipline section preserved verbatim (anti-false-positive criteria intact).

## Recommendation

Approach A1 (service-level `apply_escalation`), B1 (prek + baseline ratchet reusing npx jscpd@4.0.1),
and F as specified. Sequence C items by risk: C1 (user-visible i18n bug) first, then C5 (retry gap —
needs a design decision: reorder-deactivate vs retry flag), C2/C11 mechanical batch, C4/C6-C13
trivia batch, C14 last (test rework). D lands as docs-only commit after code rules are true in
practice (V3 must not document rules the tree violates).

## Risks

- **CRITICAL**: none blocking exploration.
- **WARNING**: C5 changes `expire_tempbans` semantics — existing tests assert
  deactivate-even-on-unban-failure behavior; spec `sentinel-commands`/`infraction-service`
  deltas required.
- **WARNING**: decorator conversion changes error surface: `is_mod()` raises
  `MissingRole`/`CheckFailure` with mod-role messaging; `can_check` raises matrix-gated
  errors. Tests in `tests/test_checks.py` + `tests/integration/test_moderation_flow.py`
  assert current behavior — expect churn.
- **WARNING**: BLE001 ×38 in bot/ — many are `except Exception` around Discord/DB calls
  where broad catch is intentional; each needs either narrowing or `# noqa: BLE001` with
  reason (AGENTS.md allows narrow noqa with justification per PR4c precedent).
- **SUGGESTION**: brief's BLE001=76 / PLC0415=983 counts don't match today's tree
  (39 / 67+tests) — re-baseline before ratchet commitments.
- **SUGGESTION**: key-coverage test must allowlist dynamic keys (`tickets.timer.unit_*`,
  `ocio.8ball.r*`) or it will false-fail.
- **SUGGESTION**: `uv check` removal — verify no other caller (Makefile/scripts) before swap.

## Affected Areas

- `bot/cogs/sentinel.py` — A (decorators, escalation extraction, C2, C10, C11, C12-adjacent)
- `bot/services/infraction_service.py` — A (`apply_escalation`), C5 (retry gap)
- `bot/locales/es.json`, `bot/locales/en.json` — C1 keys
- `bot/core/i18n.py` + new test — C1c coverage test
- `bot/bot.py` — C4 (handler logging), C9 (3d/3f markers), F3-adjacent
- `bot/cogs/ocio.py`, `bot/services/ocio_service.py`, `bot/utils/embeds.py` — C6, C7, C8
- `bot/core/realtime.py`, `bot/listeners/voice_listener.py` — C9 stale comments
- `bot/cogs/stellar.py` — C13
- `tests/test_bot_probe.py` — C14
- `pyproject.toml`, `prek.toml` — F1/F2/F3, B hook
- `.github/workflows/code-quality.yml` — B ratchet job
- `AGENTS.md` — D
- `openspec/specs/{ephemeral-standard,close-confirmation,confirm-dialog,infraction-service,sentinel-commands}/spec.md` — deltas for C2/C3/C5/A

## Ready for Proposal

Yes. All brief items located and classified; two need explicit design decisions at
spec/design time: (1) C5 retry semantics, (2) jscpd ratchet mechanics (baseline file
format + who lowers it). Scope fits the 800-line review budget only if split —
recommend chained slices: (1) Sentinel A+C5, (2) C-trivia batch, (3) toolchain F+B,
(4) AGENTS.md D + E convergence.
