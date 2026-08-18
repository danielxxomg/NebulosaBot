# Apply Progress — refactor-ticket-domain S2.1+S2.2+S2.3

## S2.3 Work Unit
S2.3 Live Verifier (PR3->PR2) -- read-only binder + credential-gated live marker, no DDL, strict TDD.

### TDD Cycle Evidence S2.3

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | `tests/test_schema_inventory_verifier.py` | Unit | 1842 pass | 9 FAIL AttributeError bind_live_evidence | 9 pass 1 skipped | 9 zero-policy / 6 FK / 4 CDC / 19 migrations / drift | ruff format |
| 3.2 | `bot/services/schema_inventory.py` | Unit | bind_live_evidence | N/A | LiveEvidenceReport + verify_live_parity, no DDL, TEXT/UUID flag | category_id_type_mismatch triage | ruff fix |
| 3.3 | `tests/conftest.py` + `pyproject.toml` | Integration | live marker | UnknownMark | live marker registered, --run-live gated skip | LIVE_SUPABASE=1 opt-in | -- |
| 3.4 | full suite | Unit+Typecheck | gates | N/A | mypy 0 ruff 0 pytest 1851 pass | --run-live --collect-only | -- |

### Work Unit Evidence S2.3

| Evidence | Value |
|----------|-------|
| Focused test cmd | `uv run pytest tests/test_schema_inventory_verifier.py --no-cov -q` -> 9 passed, 1 skipped; `uv run pytest -m live --run-live --collect-only -q` -> 1 collected |
| Runtime harness | `LIVE_SUPABASE=1 uv run pytest -m live --run-live -q` -- skipped without creds (default), gated live path would run read-only when SUPABASE_URL present; no DDL |
| Rollback boundary | `bot/services/schema_inventory.py` (LiveEvidenceReport/verifyLiveParity), `tests/test_schema_inventory_verifier.py`, `tests/conftest.py` live gate, `pyproject.toml` marker -- revert restores no live binder |

### Verification S2.3

- `uv run mypy bot tests` -- 0 errors (152 files).
- `uv run ruff check bot tests` -- 0.
- `uv run ruff format --check .` -- clean.
- `uv run pytest --no-cov -q` -- 1851 passed, 4 skipped (was 1842 + 9 new).
- `uv run pytest -m live --run-live --collect-only -q` -- 1 collected (live gated).
- Default pytest remains credential-independent (live skipped without LIVE_SUPABASE=1).
- No DDL -- migrations untouched, SchemaInventory.LiveEvidenceReport.no_ddl true.

### Branch S2.3

`refactor-ticket-domain-s2d3` from 33026d2, 1 work-unit commit, 317 ins + 1 del = 318 (<=400, <=800). Base for S2.4 repair seam.

---

# Apply Progress — refactor-ticket-domain S2.1+S2.2

## S2.1 Work Unit
S2.1 Typed Surface (PR1→main) — stacked-to-main, auto-chain.

### TDD Cycle Evidence S2.1

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_s2d1_context_typing_chars.py` | Unit | ✅ 1814 pass baseline | ✅ 4 FAIL (Context[Any] present) | ✅ 9 pass | ✅ decorator + inline is_mod probes | ✅ format |
| 1.2 | same + `bot/cogs/*` | Unit | ✅ mypy bot 0 | N/A (GREEN) | ✅ NebulosaContext in sentinel/utility | ✅ interaction preserved | ✅ Any scoped |
| 1.3 | 7 files (verify/views/embeds/help/sentinel/tickets) | Unit | ✅ 28 mypy errors | N/A | ✅ mypy bot tests 0 | ✅ guards + TYPE_CHECKING | ✅ ruff 0 |
| 1.4 | full suite | Unit+Typecheck | ✅ 1823 pass | N/A | ✅ ruff 0 mypy 0 pytest 1823 | N/A | ✅ py_compile |

### Work Unit Evidence S2.1

| Evidence | Value |
|----------|-------|
| Focused test cmd | `uv run mypy bot tests` → Success 150 files; `uv run pytest tests/test_s2d1_context_typing_chars.py --no-cov -q` → 9 passed; `uv run ruff check bot tests` → All checks passed |
| Runtime harness | N/A — typed surface, no runtime boundary (is_mod behavior unchanged, views retain inline gate). |
| Rollback boundary | `bot/cogs/sentinel.py`, `bot/cogs/utility.py`, `tests/test_s2d1_context_typing_chars.py`, `tests/test_{verify,views,embeds,help,sentinel,tickets}*.py` — revert restores Context[Any] + 28 errors |

### Verification S2.1

- `uv run mypy bot tests` — 0 errors (was 28).
- `uv run ruff check bot tests` — 0.
- `uv run pytest -q` — 1823 passed, 3 skipped, 88.61%.
- `python -m py_compile bot/__main__.py` — OK.

### Commit S2.1

`f3012b7` on `refactor-ticket-domain-s2d1` (1 work-unit commit).

---

## S2.2 Work Unit
S2.2 Guild DB (PR2→PR1) — 12 gaps + one vertical, strict TDD, no DDL.

### TDD Cycle Evidence S2.2

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/test_guild_scope_gaps.py` | Unit | ✅ 1842 baseline | ✅ 16 FAIL (guild_id unexpected) | ✅ 19 pass | ✅ all 12 gaps probed | ✅ ruff format |
| 2.2 | `bot/core/db/*.py` | Unit | ✅ 19 pass | N/A | ✅ guildId filters + ownership before mutate | ✅ Note/audit non-empty reason | ✅ ruff fix |
| 2.3 | `bot/services/ticket_service.py` + `bot/views/tickets.py` | Integration | ✅ claim/transfer paths | N/A | ✅ claim/unclaim/transfer guild-scoped | ✅ _get_ticket guild_id | ✅ mypy 0 |
| 2.4 | full suite | Unit+Typecheck | ✅ gates | N/A | ✅ mypy bot tests 0 ruff 0 pytest 1842 | N/A | ✅ no DDL |

### Work Unit Evidence S2.2

| Evidence | Value |
|----------|-------|
| Focused test cmd | `uv run pytest tests/test_guild_scope_gaps.py -k guild_scope --no-cov -q` → 19 passed; `uv run pytest -q` → 1842 passed, 3 skipped, 88.74% |
| Runtime harness | N/A DB — mock Supabase; one vertical migrated (claim/unclaim/transfer + view). |
| Rollback boundary | `bot/core/db/ticket*.py`, `bot/services/ticket_service.py`, `bot/views/tickets.py`, `tests/test_guild_scope_gaps.py` — revert restores ID-only DB |

### Implementation Details S2.2

- DB: `ticket_db` get_ticket/get_ticket_by_channel/get_tickets_by_parent optional guild_id filter, update_ticket guild_id pop+eq; note/audit validate ownership before mutate (ValueError cross_guild_denied); get_* returns []/None on mismatch; audit bypass for empty ticket_id (sweep failures) and missing ticket (allow audit).
- Service: claim/unclaim/transfer now accept guild_id, pass to DB scoped get/update, audit denied with non-empty cross_guild_denied when not found.
- View: TicketActionsView._get_ticket now passes guild_id to get_ticket_by_channel.
- Branch: `refactor-ticket-domain-s2d2` from 5b82dda, commit ee055e4 (495 ins + 52 del = 547, <800).

### Verification S2.2

- `uv run mypy bot tests` — 0 errors.
- `uv run ruff check bot tests` — 0.
- `uv run pytest -q` — 1842 passed, 3 skipped, 88.74%.
- `uv run ruff format --check .` — clean.
- No DDL — `migrations/` untouched, `SchemaInventory.no_ddl` true.

## Next

S2.3 Live Verifier (PR3→PR2) — read-only FK/RLS/publication/index/migration binder.

