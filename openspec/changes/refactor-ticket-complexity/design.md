# Design: Refactor Ticket Complexity

## Technical Approach

Preserve ticket behavior while moving repeated Discord-resolution and naming preparation into `bot.utils.ticket_helpers`. Add characterization tests before each extraction, then replace callers incrementally. `TicketService.reopen_ticket` retains state validation, Spanish user-facing errors, DB mutation, cache update, and audit; its channel-construction block becomes a private async method.

## Architecture Decisions

| Decision | Alternatives / tradeoff | Rationale |
|---|---|---|
| Helpers are dependency leaves | New channel-builder service adds indirection; helper module already imports invariants | Keep scope refactor-only. Helpers receive Discord objects/raw IDs rather than importing bot, cog, view, or `TicketService`. |
| Preserve orchestration ownership | Move all Discord work out of `TicketService` | The proposal defers a full split. The private reopen helper reduces complexity without changing public APIs. |
| Test observable behavior first | Move code then adapt tests | Existing tests cover primary flows but not all fallbacks/permission principals. Pin contracts before rewiring. |

## Data Flow

    cog / modal view ── raw config ID ──> ticket_helpers ──> resolved Role/Member
              │                                      │
              └──── category UUID ──> DB reader ─────┘
    TicketService.reopen_ticket ──> _build_reopen_channel ──> Discord channel
              └── invariant/audit/cache/DB update remain in service

`resolve_category_name` is async because it reads the existing DB facade; the other helpers do no I/O or mutation beyond constructing a new overwrite mapping.

## Helper Interfaces and Extraction Order

```python
def build_ticket_overwrites(
    guild: discord.Guild, author: discord.Member | None, mod_role: discord.Role | None,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]: ...

def resolve_mod_role(guild: discord.Guild, role_id: object) -> discord.Role | None: ...
def resolve_member_safe(guild: discord.Guild, member_id: object) -> discord.Member | None: ...
async def resolve_category_name(db: TicketCategoryReader, category_id: str | None, fallback: str = "ticket") -> str: ...
```

`TicketCategoryReader` is a local `Protocol` exposing only `get_ticket_category`; it prevents a runtime `Database` import. Helpers suppress only the currently suppressed invalid-ID cases; category lookup logs the current warning and returns `fallback` on absence/failure.

Extraction order: (1) characterize existing outputs and failure fallbacks, (2) add helper tests and implementations, (3) wire `create_ticket_channel`, (4) wire `reopen_ticket` through `async _build_reopen_channel(guild, closed_row, guild_row, category_channel)`, (5) wire cog and view config/category lookups. The Spanish non-closed-ticket message remains beside `check_can_reopen` in `reopen_ticket`.

## Circular Import Risks

`ticket_helpers` already imports `ticket_invariants`; `TicketService` imports helpers only locally today. New imports must remain one-way: `cogs`/`views`/`services` → `utils.ticket_helpers` → `services.ticket_invariants`. Do not import `NebulosaBot`, cogs, views, `TicketService`, or `Database` at runtime; use `TYPE_CHECKING` and the narrow protocol. Add an import smoke test or run targeted module imports before wiring.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/utils/ticket_helpers.py` | Modify | Add four leaf helpers and narrow DB protocol. |
| `bot/services/ticket_service.py` | Modify | Reuse helpers; extract private reopen channel builder. |
| `bot/cogs/tickets.py` | Modify | Reuse safe role/category helpers in subticket creation. |
| `bot/views/tickets.py` | Modify | Reuse safe role helper after config lookup. |
| `tests/test_ticket_helpers.py` | Modify | Unit-test helper contracts and fallback paths. |
| `tests/test_ticket_service.py` | Modify | Characterize reopen/create permissions, names, and invalid IDs. |
| `tests/test_tickets_cog.py` | Modify | Characterize subticket role/category wiring. |
| `tests/test_ticket_views.py` | Modify | Characterize modal role-resolution wiring. |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Each helper's valid, missing, malformed, and lookup-failure behavior | `MagicMock` Discord/async DB reader; assert principals and overwrite permissions. |
| Service | Reopen name, fallback, exact Spanish invariant error, DB/cache/audit sequencing | Extend existing async characterization tests; no Discord API. |
| Integration | Ticket modal and subticket callers pass unchanged arguments/results | Existing mocked cog/view flow tests; run `uv run pytest`. |

## Migration / Rollout

No data migration or feature flag. Deliver stacked PRs ultimately to `main`: PR1 tests + helpers (~300 lines), PR2 service wiring/reopen builder (~300 lines), PR3 cog/view wiring (~180 lines). Each later slice targets its immediate predecessor; each remains below 400 changed lines where practical despite the 1500-line review budget.

## Rollback

Revert the affected slice. Reverting wiring restores inline behavior; reverting the service slice restores `reopen_ticket`; helpers introduced by PR1 are harmless dead code. Run the full suite at every boundary.

## Open Questions

None.
