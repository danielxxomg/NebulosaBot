# Design: cleanup-stability — Hygiene & Stability (S1 L3)

## Technical Approach

Keep the cache-first read path and Supabase Realtime CDC invalidation from `Diagramas/DiagramaSecuencia.mmd`. Deliver five bottom-up slices from `f83e767`; every slice has the blocking `bot/` + `tests/` gate and a revert.

| Slice | Scope | Verification / rollback |
|---|---|---|
| PR1a | Prune refs; align pre-commit, Makefile, CI | `git ls-remote`, all-files gate; revert config |
| PR1b | Mechanical Ruff format batch A (13 files) | format check; revert commit |
| PR1c | Format batch B plus lint cleanup | Ruff check/format; revert commit |
| PR2 | Ruff ratchet, mypy context typing, cache-key helper | mypy + pytest; revert commit |
| PR3 | Read-only schema/RLS/FK/TTL inventory | inventory + negative tests; revert code/docs |

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Slice count | Five stacked PRs, bottom-up to `main` | Formatting alone is 658 authored lines, above the 600-line budget; two mechanical batches avoid mixing database risk into format review. |
| Ruff ratchet | Explicit residual per-code ignores, not family ignores | Removing families exposes 136 `TRY` and 95 `S` findings; exact codes keep deferred `TRY003` auditable. |
| Context typing | `NebulosaContext`/callbacks use `commands.Context[NebulosaBot]` | Generic inference resolves the decorator contract; `type: ignore[arg-type]` would only hide it. |
| Supabase access | Server-side `service_role` only; no new policies | Nine RLS tables have no policies. Without an auth/guild contract, adding policies could expose data; service-role bypass stays server-only. |
| Schema changes | Inventory live/disk metadata and `015_*` before DDL | Live-only `005` and possible redundant `015` indexes make replay unsafe; drift blocks DDL and S1 applies none. |

## Data Flow

`Command → Service → TTLCache ({guild_id}:{entity}) → DB on miss → cache populate`. CDC for `guild`, `greeting_config`, `ticket`, or `ticket_note` calls `invalidate_guild`. Member/economy invalidation is S2. TTLs: guild/config 300 seconds; leaderboard 30 seconds.

### Stacked PR CI gate

```mermaid
sequenceDiagram
    Dev->>PR: Push slice N (explicit base/head)
    PR->>CI: Checkout SHA
    CI->>CI: Five full bot/tests gates
    alt Failure
        CI-->>PR: Red; merge blocked
    else Pass
        CI-->>PR: Green required status
        PR->>main: Merge; retarget child
    end
```

### Service-role startup and negative path

```mermaid
sequenceDiagram
    NebulosaBot->>Database: connect()
    Database->>Validator: Verify present/verifiable service_role
    alt Invalid, anon, publishable, or authenticated
        Validator-->>NebulosaBot: Error; no client/services
        Validator-->>Test: Read denied; zero rows exposed
    else Valid service_role
        Database->>Supabase: guild health probe
        Supabase-->>Database: Success
        Database-->>NebulosaBot: Initialize cache/services
    end
```

### FK retention policy

```mermaid
sequenceDiagram
    Operator->>DB: Delete ticket
    par Notes
        DB->>ticket_note: CASCADE; delete notes
    and Audit
        DB->>ticket_audit: SET NULL; retain row, ticketId=NULL
    end
```

`ticket_audit.ticketId` must become nullable in a future validated migration; S1 records only the policy.

## File Changes

| File | Action | Description |
|---|---|---|
| `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Makefile`, `pyproject.toml` | Modify | Pin Ruff 0.15.20; enforce full gates and ratchets. |
| `bot/core/context.py`, `bot/bot.py`, `bot/cogs/*.py`, `bot/utils/checks.py` | Modify | Parameterized contexts; remove decorator suppressions; preserve `is_mod`. |
| `bot/core/cache.py`, `bot/services/{guild,greeting,economy}_service.py` | Modify | Shared guild keys and TTL documentation. |
| `bot/core/db/base.py`, `bot/config.py`, `bot/services/integrity_report.py` | Modify | Startup role validation and read-only RLS/FK/015 evidence. |
| `tests/test_database.py`, `tests/test_ticket_integrity.py`, new CI/schema tests | Modify/Create | RED-first startup, denial, scope, inventory, and gate tests. |

`TicketService` remains 2,170 lines/31 dependents; no S2 split. Anchors: `GuildService` 17, `Database` 29, `is_mod` 23.

## Interfaces / Contracts

`Database.connect()` raises `ServiceRoleValidationError` before exposing a client on invalid credentials. Read-only `SchemaInventory` reports RLS, FK actions, guild-scope gaps, and `015` filename/object/applied parity; incompatible status forbids DDL.

## Testing Strategy

Strict TDD: write RED tests before each slice. Unit tests cover gate contracts, context inference, cache/TTLs, startup failure, and drift. Integration tests use mocked/read-only Supabase clients for role success and denial. E2E is not applicable.

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior; planned RED test |
|---|---|---|
| Documentation-like paths | N/A — no executable classification; `scripts/` stays outside gate | No execution; no test |
| Git repository selection | Applicable — explicit `origin` and SHA/ref | Wrong path aborts before prune; RED test rejects ambiguity |
| Commit state | Applicable — each head is an exact commit | Dirty/empty state cannot gate; RED test covers staged, `commit -a`, empty index |
| Push state | Applicable — explicit first/follow-up refs | Never infer destination; RED test covers tracking/first/refspec |
| PR commands | Applicable — explicit base/head ownership | Preserve composed args; RED test covers explicit `--head` |

## Migration / Rollout

No migration or DDL. Provision the server-only `service_role` secret before validation; Realtime may degrade to TTL-only. Remote deletion is separately approved; retain `archive/2026-07-pr2a/b` and its tag.

## Open Questions

None. Authenticated Data API policies, economy Realtime invalidation, and the `TicketService` split are explicitly deferred to S2.
