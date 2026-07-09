# Exploration: Code Quality Consolidation

## Supersedes

This exploration consolidates and supersedes:

- `audit-test-ci-quality/exploration.md` — full (duplication, CI tooling, layering findings)
- `audit-git-hygiene/exploration.md` — full (branch/stash cleanup)
- `audit-docs-gaps/exploration.md` — partial (code-debt warnings: nb! centralization, mypy overrides, coverage gaps)
- `audit-supabase-practices/exploration.md` — partial (SELECT * usage only; NOT RPC grants or RLS)

---

## Current State

NebulosaBot has strong QA gates (ruff, mypy strict, bandit, pytest-cov ≥75%, GGA review) but those gates are blind to **duplication**, **layer violations**, and **dead code**. All tests green (957 passed, 84% coverage). Working tree is clean. 15 merged remote branches and3 stashes remain from completed development arcs.

---

## In Scope

1. Duplication hotspots (nb!, _resolve_avatar_url) — minimal fixes
2. Optional CI tooling (jscpd, vulture) — default ON/OFF recommendation
3. Git hygiene chore tasks (delete merged branches, drop stashes)
4. Layering: document worst offenders, fix if fits 800-line budget
5. SELECT * on hot paths (15 occurrences in db mixins)

## Out of Scope

- UX product features (moderation viewer, deep-link, voice logging)
- Supabase RPC grants / RLS hardening
- Migration repair / FK violation fix
- Persistent view label i18n
- Greeting commands

---

## 1. Duplication Hotspots

### `"nb!"` hardcoded — 5 production files

| File | Line | Context |
|------|------|---------|
| `bot/bot.py` | 44 | `_FALLBACK_PREFIX = "nb!"` — defined and used internally ✅ |
| `bot/models/guild.py` | 17, 48 | Default prefix in dataclass + from_row fallback |
| `bot/core/db/guild_db.py` | 61 | Upsert dict literal |
| `bot/services/guild_service.py` | 87, 138 | GuildConfig construction (2 places) |
| `bot/cogs/core.py` | 243 | `_resolve_prefix` fallback return |

`bot.py` defines `_FALLBACK_PREFIX` but no other file imports it. Four files duplicate the literal.

**Fix**: Import `_FALLBACK_PREFIX` from `bot.bot` (or move to `bot/constants.py`) in the 4 other files. ~8 lines changed.

### `_resolve_avatar_url` duplicated

- `bot/cogs/greetings.py:188` — identical implementation
- `bot/services/greeting_service.py:229` — identical implementation

**Fix**: Delete from cog, import from service. ~7 lines changed.

---

## 2. Optional CI Tooling

### jscpd (copy-paste detection)

| Aspect | Detail |
|--------|--------|
| What | Detects duplicated code blocks across files |
| Install | `npm i -g jscpd` or `npx jscpd` in CI |
| Config | Threshold 5% for `bot/`, 10% for `tests/` |
| Catches | nb! duplication, guild_id boilerplate, copy-pasted helpers |
| CI cost | ~5s on PR only |
| Default | **OFF** initially (report-only), turn ON after first cleanup pass |

### vulture (dead code detection)

| Aspect | Detail |
|--------|--------|
| What | Finds unused imports, variables, functions, classes |
| Install | `pip install vulture` (already in dev deps?) |
| Config | Whitelist `bot/` dynamic discord.py usage with `# noqa: vulture` |
| Catches | Dead code that ruff F841 misses (suppressed for bot/) |
| CI cost | ~2s |
| Default | **OFF** initially (report-only), turn ON after whitelist is stable |

**Recommendation**: Add both as report-only in CI first. Gate ON after initial cleanup pass proves low noise.

---

## 3. Git Hygiene (Chore Tasks)

### Merged Remote Branches — 15, all safe to delete

All have 0 unique commits not in master. No open PRs depend on them.

```bash
git push origin --delete \
  feat/arch-debt-pr5 feat/arch-debt-pr3-pr4 feat/arch-debt-pr2 feat/arch-debt-pr1 \
  feat/i18n-pr4-ephemeral feat/i18n-pr3-sentinel feat/i18n-pr2-tickets \
  chore/tooling-rigor-pr3 chore/tooling-rigor-pr2 chore/tooling-rigor-pr1 \
  fix/ticket-category-id-null feat/i18n-ephemeral-pr1 fix/runtime-bugfixes \
  cache-sync-realtime-pr2 cache-sync-realtime-pr1
```

### Stashes — 3, all safe to drop

- `stash@{0}` — WIP arch-debt PR2 recovery, code diverged significantly
- `stash@{1}` — i18n verify report append (doc artifact)
- `stash@{2}` — i18n verify report append (doc artifact)

```bash
git stash drop stash@{0} && git stash drop stash@{0} && git stash drop stash@{0}
```

---

## 4. Layering — Worst Offenders

AGENTS.md says: **Cogs handle Discord interaction only — no business logic. Services handle business logic.**

### Direct `bot.db.*` calls from cogs

| Cog | Count | Examples |
|-----|-------|---------|
| `bot/cogs/tickets.py` | 14 | `get_open_ticket_channel_ids`, `update_ticket_last_activity`, `insert_ticket_category`, `get_ticket_by_channel`, etc. |
| `bot/cogs/sentinel.py` | 5 | All `insert_infraction` calls |
| `bot/cogs/core.py` | 1 | `health_check` (acceptable — infra concern) |

**tickets.py** is the worst offender: 14 direct DB calls bypass TicketService entirely. However, fixing all 14 is a ~200+ line refactor (exceeds review budget slice). **Backlog note only** — do not fix in this cycle.

**sentinel.py** has 5 `insert_infraction` calls. These could route through an `InfractionService` but that service doesn't exist yet. **Backlog note only.**

### SELECT * in db mixins — 15 occurrences

Every `get_*` method uses `.select("*")`. At current scale this is an observation, not a blocker. The 3 hot paths (`get_member`, `get_guild`, `get_ticket_by_channel`) could benefit from explicit column lists, but the maintenance cost is high. **Backlog note — defer until scale demands it.**

---

## Recommendation

**Do in this cycle (minimal, high-value):**

1. **Centralize `"nb!"` constant** — import `_FALLBACK_PREFIX` from `bot.bot` in 4 files. ~8 lines, zero risk.
2. **Remove `_resolve_avatar_url` duplication** — delete from cog, import from service. ~7 lines.
3. **Git cleanup** — delete 15 merged branches, drop 3 stashes. Zero code risk.
4. **Document layering debt** — add backlog notes for tickets.py (14 db calls) and sentinel.py (5 db calls).
5. **Add jscpd + vulture to CI** — report-only initially, default OFF. Low install cost.

**Do NOT in this cycle:**

- Fix layering violations (too large for review budget)
- Replace SELECT * (defer until scale)
- Add import-linter/tach (needs layering fix first)

---

## Risks

- **Import cycle risk**: Moving `_FALLBACK_PREFIX` to a shared module could create circular imports if not placed carefully (`bot.bot` → `bot.cogs.core` is already an import path). Mitigation: use `bot.constants` or keep in `bot.bot` and verify no cycles.
- **vulture false positives**: discord.py uses dynamic attribute access extensively. Whitelist will need iteration.
- **jscpd threshold tuning**: Shared test boilerplate may trigger at 5%. May need per-directory thresholds.

---

## Ready for Proposal

**Yes** — this is a tight, low-risk code quality cycle. ~20 lines of duplication fixes + CI tooling + git cleanup. The orchestrator should tell the user:

> "This cycle centralizes the 'nb!' constant (currently hardcoded in5 files), removes a copy-pasted helper, adds jscpd + vulture as report-only CI gates, and cleans up 15 merged branches + 3 stale stashes. Total code change: ~20 lines. Layering fixes (14 direct DB calls in tickets.py) are documented as backlog — too large for this review budget."
