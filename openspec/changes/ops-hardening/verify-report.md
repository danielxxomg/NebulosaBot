## Verification Report

**Change**: ops-hardening  
**Version**: N/A  
**Mode**: Strict TDD  
**Date**: 2026-07-08

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 14 |
| Tasks complete | 12 |
| Tasks incomplete | 2 |
| Core SQL/test tasks complete | 12/12 |
| Manual dashboard tasks complete | 0/2 |

Incomplete tasks are Phase 4 manual dashboard checklist items only:

- 4.1 Enable "Leaked Password Protection" in Supabase Dashboard.
- 4.2 Confirm toggle shows ENABLED in dashboard.

### Build & Tests Execution

**Build / validation**: ⚠️ OpenSpec CLI unavailable

```text
$ openspec validate ops-hardening --strict
/usr/bin/bash: line 1: openspec: command not found
```

**Focused migration tests**: ✅ 27 passed

```text
$ uv run pytest tests/test_migrations.py --no-cov
collected 27 items
tests/test_migrations.py ........................... [100%]
27 passed in 0.02s
```

**TDD class checks**: ✅ 9 + 5 passed

```text
$ uv run pytest tests/test_migrations.py::TestMigration010 --no-cov -q
9 passed in 0.01s

$ uv run pytest tests/test_migrations.py::TestMigration011 --no-cov -q
5 passed in 0.01s
```

**Full suite**: ✅ 971 passed, 3 skipped

```text
$ uv run pytest
collected 974 items
971 passed, 3 skipped, 2 warnings in 12.03s
Required test coverage of 75% reached. Total coverage: 84.05%
```

**Coverage**: 84.05% / threshold: 75% → ✅ Above

### Runtime / Production Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| Migration tracking repaired | ✅ Passed | `schema_migrations` contains names `006_drop_user_table`, `007_realtime_publication`, `008_ticket_note_rls`, `009_member_increment_rpc`, plus `010_rpc_revoke_grants` and `011_ticket_channel_index`. |
| RPC grants revoked from `anon` / `authenticated` | ✅ Passed | `information_schema.role_routine_grants` shows only `postgres` and `service_role` for the 4 member RPCs; no `anon` or `authenticated` rows. |
| Security advisor RPC warnings | ✅ Passed | Supabase security advisors returned no RPC grant warning; remaining WARN is `auth_leaked_password_protection`. |
| Ticket channel index exists | ✅ Passed | `pg_indexes` returned `idx_ticket_channel` on `public.ticket` using btree (`"channelId"`). |
| Query uses index | ✅ Passed | `EXPLAIN` for `select * from public.ticket where "channelId" = '0'` returned `Index Scan using idx_ticket_channel`. |
| Bot code untouched | ✅ Passed | `git diff -- bot/` returned empty output. |

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Apply-progress artifact found in Engram with `TDD Cycle Evidence`. |
| All tasks have tests | ✅ | Migration 010 and 011 structural test classes exist. Manual dashboard tasks are not testable in pytest. |
| RED confirmed | ✅ | `tests/test_migrations.py` contains `TestMigration010` and `TestMigration011`. |
| GREEN confirmed | ✅ | `TestMigration010`: 9 passed; `TestMigration011`: 5 passed. |
| Triangulation adequate | ✅ | 14 migration checks cover file existence, exact signatures, target roles, idempotent index DDL, table, index name, and column. |
| Safety net for modified files | ✅ | Full migration suite: 27 passed; full project suite: 971 passed, 3 skipped. |

**TDD Compliance**: 6/6 checks passed.

---

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit / structural | 14 new, 27 migration total | 1 | pytest |
| Integration / runtime DB | 5 verification queries/advisor checks | Supabase MCP | Supabase MCP |
| E2E | 0 | 0 | Not used |
| **Total** | **27 local migration tests + runtime DB checks** | **1 local test file + production DB** | |

---

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `migrations/010_rpc_revoke_grants.sql` | N/A | N/A | N/A | SQL structural + runtime DB verified |
| `migrations/011_ticket_channel_index.sql` | N/A | N/A | N/A | SQL structural + runtime DB verified |
| `tests/test_migrations.py` | N/A | N/A | N/A | Test file, not measured by bot coverage |

**Project coverage**: 84.05% over `bot/`, above 75% gate. No bot runtime file changed in this slice.

---

### Assertion Quality

**Assertion quality**: ✅ All added assertions verify concrete SQL artifacts or migration file existence. No tautologies, ghost loops, or smoke-only assertions found in the added tests.

---

### Quality Metrics

**Linter**: ⚠️ `uv run ruff check tests/test_migrations.py` returned pre-existing issues outside the added diff (`pytest` unused import and ambiguous variable `l` in older Migration008/009 tests). No added-line ruff errors were reported.  
**Type Checker**: ✅ `uv run mypy tests/test_migrations.py` passed with no issues.

### Spec Compliance Matrix

| Requirement | Scenario | Evidence | Result |
|-------------|----------|----------|--------|
| RPC EXECUTE revoked from anon and authenticated | service_role can call RPCs | Runtime grants query shows `service_role` retains EXECUTE for all 4 functions. | ✅ COMPLIANT |
| RPC EXECUTE revoked from anon and authenticated | anon cannot call RPCs | Runtime grants query shows no `anon` EXECUTE grants; advisor has no RPC grant warning. | ✅ COMPLIANT |
| RPC EXECUTE revoked from anon and authenticated | authenticated cannot call RPCs | Runtime grants query shows no `authenticated` EXECUTE grants; advisor has no RPC grant warning. | ✅ COMPLIANT |
| RPC EXECUTE revoked from anon and authenticated | Security advisor warnings resolved | Supabase security advisors show no RPC grant warning. | ✅ COMPLIANT |
| Zero bot code impact | Bot RPC calls unaffected | `service_role` grants remain; full suite passes. | ✅ COMPLIANT |
| Zero bot code impact | No bot code diff | `git diff -- bot/` empty. | ✅ COMPLIANT |
| Ticket channelId index | Index exists after migration | `pg_indexes` returns `idx_ticket_channel` on `public.ticket ("channelId")`. | ✅ COMPLIANT |
| Ticket channelId index | Index is idempotent | `TestMigration011::test_creates_index_if_not_exists` passed and migration uses `CREATE INDEX IF NOT EXISTS`. | ✅ COMPLIANT |
| Ticket channelId index | Query uses index | Runtime `EXPLAIN` returns `Index Scan using idx_ticket_channel`. | ✅ COMPLIANT |

**Compliance summary**: 9/9 scenarios compliant.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Migration 010 revokes member RPC grants | ✅ Implemented | Exact 4 function signatures from migration 009 are present; `FROM anon, authenticated` is present. |
| Migration 011 creates ticket channel index | ✅ Implemented | Idempotent `CREATE INDEX IF NOT EXISTS idx_ticket_channel ON public.ticket ("channelId")`. |
| Zero bot Python changes | ✅ Implemented | No `bot/` diff. |
| Manual leaked password protection toggle | ⚠️ Pending | Supabase advisor still reports `auth_leaked_password_protection` WARN. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Repair migration drift through `schema_migrations` instead of re-running DDL | ✅ Yes | Production table contains repaired 006-009 rows by migration name. Actual Supabase schema uses timestamp versions and no `executed_at`, so apply adapted the design contract safely. |
| Forward-only migration 010 for RPC permission hardening | ✅ Yes | New migration file exists and production grants reflect least privilege. |
| Forward-only migration 011 for ticket lookup performance | ✅ Yes | New migration file exists, production index exists, and query plan uses it. |
| Zero bot Python changes | ✅ Yes | `git diff -- bot/` is empty. |
| Manual dashboard leaked password toggle | ⚠️ Pending | Still disabled according to Supabase advisor. |

### Issues Found

**CRITICAL**: None.

**WARNING**:
- Manual dashboard tasks 4.1 and 4.2 are incomplete: Leaked Password Protection remains disabled (`auth_leaked_password_protection` WARN).
- `ruff check tests/test_migrations.py` is non-zero because of pre-existing issues outside the added diff; not a blocker for this ops-hardening slice.

**SUGGESTION**:
- Update the ops-hardening design note before archive to reflect actual Supabase migration tracking shape: timestamp `version`, `name`, no `executed_at` column.

### Verdict

PASS WITH WARNINGS

All SQL work, production verification, structural tests, full suite, coverage gate, and zero-bot-diff criteria passed. The only open product/ops warning is the manual Supabase Auth leaked password protection toggle.
