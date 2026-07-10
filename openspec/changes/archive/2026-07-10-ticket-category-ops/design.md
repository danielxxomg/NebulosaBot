# Design: Ticket Category Operations

## Technical Approach

Extend the existing Discord-only ticket flow without a migration or dashboard path. `TicketActionsView` will expose a persistent, staff-gated Edit Category button and an ephemeral category selector. The view delegates the mutation and rename to `TicketService`; the service uses the existing DB facade, ticket helpers, audit convention, and warning-only Discord failure handling. Ticket creation gains a pre-insert, guild-scoped count invariant.

## Architecture Decisions

| Decision | Alternatives / tradeoff | Rationale |
|---|---|---|
| Keep interaction, permission, and response handling in the view | Put permission/Discord responses in the service | Existing Claim uses `is_mod_check()` in `TicketActionsView`; services stay Discord-interaction-free and testable. |
| Put category mutation, rename orchestration, and audit in `TicketService` | Update DB directly from the view | Matches lifecycle operations and prevents business logic in cogs/views. |
| Re-validate mod/admin in the service via `check_can_edit_category(actor_id, ticket, *, is_mod)` even though the view already gates UX | View-only auth guard | The service is the security boundary; remote callers (e.g. future dashboard) would otherwise bypass the view check. Mirrors `unclaim_ticket(..., is_mod=...)`. |
| Re-run `check_can_edit_category` AND `check_one_ticket_per_user_per_category` against the NEW category inside `edit_ticket_category` before the DB update | Trust the view, or only enforce the limit on create | Edit can move a ticket into a category where its author already has an open ticket, recreating the two-open-tickets conflict the create guard prevents. |
| Re-check staff auth on the category-select submit callback (300s window) | Trust the button-open check | The ephemeral select persists for 300s; a non-mod could click the select after the button was opened by a mod who left. |
| Reject edit on a closed ticket | Allow edit on any status | Closed tickets are archived; changing category would be misleading and must follow reopen. |
| Query an exact count scoped by guild, author, category, and active statuses | DB unique index/transaction | No migration is in scope. The race remains accepted and documented in the Risks section. |
| Treat DB edit as successful when rename fails | Roll back DB update | The requested durable category is more important; Discord rename rate limits are transient. |

## Data Flow

```text
Staff click ticket:edit-category
  -> TicketActionsView: is_mod_check + active categories
  -> _EditCategorySelect (ephemeral, 300s)
  -> select callback: re-run is_mod_check (300s window) + reject closed tickets
  -> TicketService.edit_ticket_category(ticket_id, new_category_id, *, channel, actor_id, is_mod)
  -> check_can_edit_category(actor_id, ticket, is_mod=is_mod)
  -> check_one_ticket_per_user_per_category(author_id, new_category_id, None, count_fn=...)
  -> ticket DB update + audit -> channel.edit(sanitized name)
```

```text
intake modal -> create_ticket_channel -> Discord channel created
  -> create_ticket -> count_user_open_tickets_in_category -> invariant
  -> insert ticket / or ValueError -> delete orphan channel
```

`create_subticket()` remains the subticket path, so it does not invoke the limit. `create_ticket()` invokes the invariant before the numbering/insert retry loop; `category_id is None` returns from the pure invariant without calling the count function. Closed rows are excluded by the DB status filter, freeing the slot.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/services/ticket_invariants.py` | Modify | Add pure one-ticket invariant and staff edit authorization helper. |
| `bot/core/db/ticket_db.py` | Modify | Add exact, guild-scoped per-author category count query. |
| `bot/services/ticket_service.py` | Modify | Enforce the count before insert; edit category, audit, and rename. |
| `bot/views/tickets.py` | Modify | Add persistent staff button and edit-specific ephemeral select flow. |
| `bot/locales/en.json` | Modify | Add edit-category labels and outcomes. |
| `bot/locales/es.json` | Modify | Add corresponding localized strings. |
| `tests/test_ticket_invariants.py` | Modify | Cover limit exemptions/blocking and edit authorization helper. |
| `tests/test_ticket_db.py` | Modify | Assert exact count and all four query filters. |
| `tests/test_ticket_service.py` | Modify | Cover guard placement, exemptions, edit/audit, and rename failure. |
| `tests/test_ticket_views.py` | Modify | Cover button localization, mod gate, selector, no categories, success, and warning. |

## Interfaces / Contracts

```python
def check_one_ticket_per_user_per_category(
    user_id: str, category_id: str | None, parent_id: str | None,
    count_fn: Callable[[str, str], int],
) -> None

def check_can_edit_category(
    actor_id: str, ticket: dict[str, Any], *, is_mod: bool,
) -> None

async def count_user_open_tickets_in_category(
    self, guild_id: str, author_id: str, category_id: str,
    *, exclude_ticket_id: str | None = None,
) -> int

async def edit_ticket_category(
    self, ticket_id: str, new_category_id: str, *,
    channel: discord.TextChannel, actor_id: str, is_mod: bool = False,
) -> tuple[Ticket, bool]
```

For the limit, the service awaits the DB count first and supplies the resulting value through `lambda _user, _category: count`; the invariant therefore remains synchronous and side-effect-free. The edit service resolves the new category name and ticket author from existing helpers/Discord cache, calls `sanitize_channel_name(name, display_name, ticket_number)`, writes `categoryId`, and returns `rename_succeeded`. It writes `edit_category/success` after the DB update; `discord.HTTPException` logs a warning and returns `False`.

`count_user_open_tickets_in_category` accepts an optional keyword-only `exclude_ticket_id: str | None = None`. On the create path the service omits it (the ticket does not exist yet, so nothing to exclude). On the edit path the service passes `exclude_ticket_id=ticket_id` so the ticket being edited is subtracted from the count; this prevents a same-category no-op rename (or any edit staying in the same category) from counting the edited ticket against itself and self-blocking the limit. The invariant's `count_fn` adapter forwards the exclusion: the service builds `count = await count_user_open_tickets_in_category(guild_id, author_id, new_category_id, exclude_ticket_id=ticket_id)` and passes `lambda _user, _category: count` into `check_one_ticket_per_user_per_category`.

`edit_ticket_category` is the security boundary: the view still gates UX with `is_mod_check()` on both button open AND select submit (the 300s ephemeral window is re-validated), but the service re-runs the pure `check_can_edit_category(actor_id, ticket, *, is_mod)` (mod role / admin permission, matching `check_can_unclaim`'s `is_mod` keyword pattern). The service additionally rejects edits on closed tickets (edit_category is only valid for `open`/`claimed`; closed tickets must be reopened first) and enforces `check_one_ticket_per_user_per_category` against the NEW category for the ticket's author before the DB update, counting the author's other open|claimed tickets in that category and excluding the ticket being edited from the count by passing `exclude_ticket_id=ticket_id` to `count_user_open_tickets_in_category` (`new_category_id` is non-null in the edit path). On limit violation the service raises the same `ValueError` used on create; the view maps that specific failure to the `tickets.actions.edit_category_limit_*` ephemeral message (NOT a generic `creation_failed`), because the duplicate is created by an edit, not by ticket creation.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Invariant skips/raises; DB filters; service DB-before-rename and count-before-insert | pytest + AsyncMock/FakeSupabaseClient |
| Integration | Channel creation cleans up when the service rejects the duplicate | Service/channel mocks in existing ticket tests |
| E2E | Not applicable | Discord API is never called in tests |

## Migration / Rollout

No migration required. Persistent button uses static `custom_id="ticket:edit-category"`; startup registration of `TicketActionsView()` already restores it.

## Open Questions

None.

## Risks

| Risk | Severity | Mitigation (in scope) |
|---|---|---|
| App-level count-then-insert race on `create_ticket` | Accepted | Two concurrent `create_ticket` calls for the same user+category can both pass the count guard, read 0 open tickets, and both insert, briefly producing two open tickets. AGENTS.md double-click idempotency is enforced best-effort via UX (the intake modal's submit button is single-use; Discord de-duplicates rapid modal submits) and `ValueError` cleanup (the orphan channel is deleted on violation), NOT via a DB unique index. A unique index is out of scope (no migration). The accept window is the service's pre-insert count, which is sufficient under normal UX. |
| App-level count-then-insert race on `edit_ticket_category` | Accepted | AGENTS.md double-click idempotency is enforced best-effort via UX (button is disabled after click; the select ephemeral returns an immediate error on the second submit) and the ephemeral error message, NOT via a DB unique index. A unique index is out of scope (no migration). The accept window is the service's pre-update count, which is sufficient under normal UX. |
