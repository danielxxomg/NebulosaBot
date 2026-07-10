## Exploration: refactor-ticket-complexity

### Current State

The ticket subsystem spans 3,441 lines across 6 production files and 8,636 lines across 7 test files (341 tests). Previous cycles already extracted pure invariants (`ticket_invariants.py`, 275 LOC), field validation (`ticket_field_service.py`, 159 LOC), and channel helpers (`ticket_helpers.py`, 206 LOC). What remains is complexity and DRY debt in the "thick" layer:

| File | LOC | Methods | Role |
|------|-----|---------|------|
| `bot/services/ticket_service.py` | 1,069 | 16 async + 2 static | God service — lifecycle + orchestration |
| `bot/cogs/tickets.py` | 791 | 20 commands + 3 helpers | Cog — Discord interaction only |
| `bot/views/tickets.py` | 676 | 4 views + 1 modal + 1 deploy fn | Views — button/select callbacks |

The service violates its own architecture rule ("Cogs handle Discord interaction only — no business logic") in reverse: the service handles Discord API calls (channel creation, permission overwrites, member resolution) that belong in an orchestration layer, not a business service.

### Affected Areas

- `bot/services/ticket_service.py` — God service with 3 high-complexity methods and 4 repeated patterns
- `bot/cogs/tickets.py` — `unclaim` (106 LOC) and `subticket_create` (90 LOC) with duplicated guild config resolution
- `bot/views/tickets.py` — `_create_ticket_after_modal` (137 LOC) duplicates config + category resolution from cog
- `bot/utils/ticket_helpers.py` — Natural home for extracted pure helpers
- `tests/test_ticket_service.py` (83 tests, 2,487 LOC) — characterization baseline
- `tests/test_tickets_cog.py` (111 tests, 2,826 LOC) — characterization baseline
- `tests/test_ticket_views.py` (35 tests, 983 LOC) — characterization baseline

### Duplication Inventory

**1. Permission overwrite building** — 2 occurrences
- `ticket_service.py:reopen_ticket` (L547-569) — default_role deny, bot allow, author allow (with try/except), mod allow (with try/except)
- `ticket_service.py:create_ticket_channel` (L904-913) — default_role deny, author allow, bot allow, mod allow
- Both build the same `dict[Role|Member|Object, PermissionOverwrite]` with identical entries

**2. Mod role resolution** — 3 occurrences
- `ticket_service.py:reopen_ticket` L562-568 — `guild.get_role(int(mod_role_id))` + try/except
- `cogs/tickets.py:subticket_create` L484-486 — identical pattern
- `views/tickets.py:_create_ticket_after_modal` L132-134 — identical pattern

**3. Member resolution from snowflake** — 5 occurrences
- `ticket_service.py:reopen_ticket` L557 (author), L598 (display name), L714-715 (transfer audit)
- `cogs/tickets.py:_resolve_parent_owner` L417
- All follow `guild.get_member(int(id))` with `try/except (ValueError, TypeError)`

**4. Category name resolution from UUID** — 2 occurrences
- `ticket_service.py:reopen_ticket` L581-592 — `db.get_ticket_category(uuid)` → `row.get("name", "ticket")`
- `cogs/tickets.py:subticket_create` L488-496 — identical pattern

**5. Audit-trail boilerplate** — 8 methods in ticket_service
- Every mutating method follows: `pre-read → invariant check → audit denial on ValueError → mutate → re-read → audit success`
- The pre-read + guild_id extraction + audit denial wrapping repeats verbatim in close, claim, unclaim, transfer, reopen, subticket_create, note_add, note_delete

### High-Complexity Methods

**`reopen_ticket` (L493-630, 137 LOC)** — cyclomatic complexity ~12
- Fetches ticket, checks invariant, fetches guild config, resolves Discord category
- Builds permission overwrites (duplicated)
- Resolves mod role (duplicated)
- Resolves category name from UUID (duplicated)
- Resolves author display name (duplicated)
- Creates channel, updates DB, updates cache, audits
- Contains inline Spanish error message translation (L535-537)

**`create_subticket` (L362-491, 129 LOC)** — cyclomatic complexity ~8
- Parent validation chain (self-reference check, then pure invariant)
- Sequential numbering retry loop (duplicated from `create_ticket`)
- Inline audit at each denial point

**`_create_ticket_after_modal` (views L74-211, 137 LOC)** — cyclomatic complexity ~10
- Duplicates config fetch, category resolution, mod role resolution from cog
- 5 distinct error paths each with its own embed

### Approaches

1. **Extract pure helpers to ticket_helpers.py** — Pull the 4 duplicated patterns into pure functions: `build_ticket_overwrites()`, `resolve_mod_role()`, `resolve_member_safe()`, `resolve_category_name()`. Use them in service, cog, and views.
   - Pros: Minimal risk, biggest DRY win, no architectural change, easy to test
   - Cons: Doesn't address the service size or audit boilerplate
   - Effort: Low

2. **Extract Discord orchestration from service** — Move `create_ticket_channel`, `close_ticket_full`, `reopen_ticket` Discord-specific logic (channel creation, permissions, member resolution) into a new `bot/services/ticket_channel_builder.py`. Keep pure business logic (create_ticket, close_ticket, claim, etc.) in ticket_service.
   - Pros: Aligns with architecture rules ("services = business logic, no Discord"), reduces service from 1,069 to ~600 LOC
   - Cons: More files to maintain, requires careful interface design, moderate risk
   - Effort: Medium

3. **Audit-trail decorator** — Extract the pre-read → invariant check → audit denial → mutate → audit success pattern into a decorator or context manager that wraps each mutating method.
   - Pros: Eliminates the most repeated boilerplate (8 methods)
   - Cons: Decorator obscures control flow, harder to debug, may not fit all methods uniformly (reopen has different pre-read pattern)
   - Effort: Medium

### Recommendation

**Approach 1 (Extract pure helpers) + partial Approach 2 (move `reopen_ticket` channel-building into a helper)**.

Rationale:
- Approach 1 is the lowest-risk DRY win — 4 pure helper functions eliminate 5× duplication across 3 files
- The `reopen_ticket` method (137 LOC, complexity ~12) is the worst offender; extracting its Discord channel-building into a `_build_reopen_channel()` helper (or into `ticket_helpers.py`) cuts it in half
- Approach 3 (audit decorator) is too clever for a no-behavior-change cycle — it changes control flow semantics and makes debugging harder
- Full Approach 2 is better deferred to a dedicated "split ticket service" change after this cycle proves the helpers work

Specific extraction targets:

| New function | Location | Eliminates | Source lines saved |
|-------------|----------|------------|-------------------|
| `build_ticket_overwrites(guild, author, mod_role)` | `ticket_helpers.py` | 2 blocks in service | ~20 |
| `resolve_mod_role(guild, guild_row)` | `ticket_helpers.py` | 3 blocks across service/cog/views | ~15 |
| `resolve_member_safe(guild, user_id)` | `ticket_helpers.py` | 5 blocks across service/cog | ~25 |
| `resolve_category_name(db, category_id, fallback)` | `ticket_helpers.py` | 2 blocks in service/cog | ~15 |
| `_build_reopen_channel(...)` | `ticket_service.py` (private) | Inline block in reopen_ticket | ~50 |

Total estimated line reduction: ~125 LOC across production files, with the service dropping from 1,069 to ~950 and complexity hotspot `reopen_ticket` dropping from 137 to ~80 LOC.

### Risks

- **Behavioral drift**: Pure helper extraction must preserve exact error messages and exception types. Characterization tests (341 existing) catch regressions, but `reopen_ticket` has inline Spanish error text (L535-537) that must move with the invariant check, not get lost.
- **Import cycles**: `ticket_helpers.py` already imports from `ticket_invariants.py`. Adding Discord-aware helpers (`build_ticket_overwrites`) means it would import `discord` — acceptable since it's a utility module, but verify no circular imports with `bot.bot`.
- **Test fixture churn**: Extracting helpers means some service tests become helper tests. Must update mocks for the new call sites without losing coverage.
- **Scope creep**: The `_create_ticket_after_modal` (137 LOC) in views has the same duplication but touches the modal callback flow. Refactoring it risks the intake UX — defer to a follow-up.

### Ready for Proposal

**Yes** — the exploration is complete. The orchestrator should tell the user:

- 4 pure helper extractions + 1 service-internal helper cover the DRY debt with minimal risk
- Characterization tests exist (341 tests, 8,636 LOC) as the safety net
- The change is strictly no-behavior-change: pure refactoring with test-first
- Estimated scope: 5 new/modified production files, ~5 test file updates, ~125 LOC reduction
- Forecast: well under the 400-line review budget per PR if split into 2 slices (helpers first, then wiring)
