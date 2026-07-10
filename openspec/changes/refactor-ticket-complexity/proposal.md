# Proposal: Refactor Ticket Complexity

## Intent

Reduce cyclomatic complexity and DRY debt in the ticket subsystem. `ticket_service.py` (1,069 LOC) and consumers duplicate 4 patterns across 10+ call sites. Extract pure helpers without changing behavior.

## Scope

### In Scope
- `build_ticket_overwrites()` — permission overwrite builder (2 sites)
- `resolve_mod_role()` — mod role from config (3 sites across service/cog/views)
- `resolve_member_safe()` — safe member resolution (5 sites)
- `resolve_category_name()` — category name from UUID (2 sites)
- `_build_reopen_channel()` — private helper, `reopen_ticket` 137→~80 LOC
- Characterization tests FIRST; Spanish error strings stay with invariant checks

### Out of Scope
- `_create_ticket_after_modal` refactor (UX risk — defer)
- Audit-trail decorator (control flow change — defer)
- Full service split (defer after helpers stabilize)
- Any behavior change or spec requirement changes

## Capabilities

None — pure refactor. No new or modified capabilities.

## Approach

Characterization tests first, then extract. Each helper gets a unit test before code moves.

1. Pin current behavior with characterization tests
2. Extract 4 pure helpers to `ticket_helpers.py`
3. Extract `_build_reopen_channel()` as private service method
4. Wire call sites; tests stay green at each step
5. Spanish error text moves with its invariant check

Est. ~125 LOC reduction. Service: 1,069→~950. `reopen_ticket`: 137→~80.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/utils/ticket_helpers.py` | Modified | Add 4 pure helpers |
| `bot/services/ticket_service.py` | Modified | Replace duplication; extract helper |
| `bot/cogs/tickets.py` | Modified | Replace 2 duplication sites |
| `bot/views/tickets.py` | Modified | Replace mod role resolution |
| `tests/test_ticket_helpers.py` | New | Unit tests for helpers |
| `tests/test_ticket_service.py` | Modified | Characterization + mock updates |
| `tests/test_tickets_cog.py` | Modified | Mock updates |
| `tests/test_ticket_views.py` | Modified | Mock updates |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Behavioral drift | Low | Characterization tests pin behavior |
| Spanish strings lost | Low | Text stays with invariant checks |
| Import cycles | Low | Verify no circular imports |
| Fixture churn | Medium | Update mocks; preserve coverage |

## Rollback Plan

Each extraction is one commit. Revert wiring commit to restore inline code; helper is dead code. 341+ tests must pass at each boundary.

## Dependencies

None.

## Success Criteria

- [ ] All 341+ tests pass, zero behavior changes
- [ ] Each helper has unit tests
- [ ] `reopen_ticket` drops to ~80 LOC
- [ ] No duplication for extracted patterns
- [ ] Coverage unchanged
