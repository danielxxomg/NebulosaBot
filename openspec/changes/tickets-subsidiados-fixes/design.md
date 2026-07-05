# Design: tickets-subsidiados-fixes

## Overview

Patch four independent ticket-subsidiados blockers without schema changes. Keep Discord interaction logic in `bot/cogs/tickets.py`, service invariants in `bot/services/ticket_service.py`, and extend existing pytest files before implementation. No migrations or new production files are required.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Note privacy | Slash uses ephemeral response; prefix DMs staff author and sends channel confirmation only. | Always `ctx.send`; always DM. | Discord.py hybrid `Context.interaction` identifies slash invocations; prefix has no ephemeral channel privacy. |
| Reopen guard | Guard in cog and in `TicketService.reopen_ticket`. | Service-only guard. | Cog gives precise user-facing error; service prevents duplicate channels for future callers. |
| Sub-ticket access | Grant parent ticket author, not invoker; mod role covers staff. | Keep invoker overwrite. | Spec says child ticket belongs to parent owner; over-granting staff members creates unnecessary access. |
| Error handling | Wrap each critical DB/service call tightly; log with `logger.exception`; return `error_embed`. | Large command-level try/except. | Keeps parsing/help paths normal and avoids hiding unrelated code defects. |
| Delivery | Four blocker-sized work-unit commits. | One bundled commit. | Changes are independent and easy to review/rollback. |

## Per-blocker Implementation Approach

### B1 — `/note list` privacy

Build the notes embed as today, but route by invocation type:

```python
if ctx.interaction is not None:
    await ctx.send(embed=embed, ephemeral=True)
else:
    await ctx.author.send(embed=embed)
    await ctx.send(embed=success_embed("Notes Sent", "Staff notes were sent to your DMs."))
```

For hybrid commands, `ctx.send(ephemeral=True)` delegates to the interaction response/followup when slash-invoked. Direct `ctx.interaction.response.send_message(..., ephemeral=True)` is valid only before the interaction has been responded to, so `ctx.send` is safer here. Prefix responses MUST NOT include note content in channel messages. If DM fails, catch `discord.Forbidden`/`discord.HTTPException`, log, and send an error embed without note content.

### B2 — `/reopen` status guard

In `TicketsCog.reopen`, reuse the existing `ticket_row = await db.get_ticket_by_channel(...)`. Before calling the service:

```python
status = ticket_row.get("status")
if status != "closed":
    await ctx.send(embed=error_embed(
        "Reopen Failed",
        f"Solo se pueden reabrir tickets cerrados. Estado actual: {status}",
    ))
    return
```

In `TicketService.reopen_ticket`, after `get_ticket(ticket_id)` and before category/channel creation, raise `ValueError` when `closed_row.get("status") != "closed"`. This prevents duplicate channel creation even if another caller bypasses the cog.

### B3 — `/subticket create` access grant

Resolve `parent_author_id` from `parent_row["authorId"]`. Use `guild.get_member(int(parent_author_id))`; if missing, `await guild.fetch_member(int(parent_author_id))` for offline members. If resolution fails, log and send `error_embed` before creating the channel.

Build overwrites with `guild.default_role`, `guild.me`, optional mod role, and:

```python
parent_author: discord.PermissionOverwrite(read_messages=True, send_messages=True)
```

Do not add `ctx.author` separately. If invoker is also the parent author, the same parent-author overwrite grants access. The initial channel message should mention `parent_author.mention`, not `author.mention`.

### B4 — Error handling

Wrap DB/service calls that can raise in these commands:

- `subticket_create`: `get_config` (already), parent ticket lookup, `get_max_ticket_number`, `create_subticket`.
- `reopen`: channel ticket lookup, `reopen_ticket`.
- `transfer`: channel ticket lookup, `transfer_ticket`.
- `note_add/list/delete`: channel ticket lookup, `create_note`, `get_notes`, `delete_note`.

Pattern: tight `try` around one call, `logger.exception("...")`, user-safe `error_embed(...)`, then `return`. Use expected exception branches (`ValueError`, `discord.HTTPException`) where meaningful; for Supabase/database client failures, keep a scoped `except Exception` only around the awaited DB/service call, never bare `except:`.

## Test Strategy (TDD)

Add failing tests first in existing files, run targeted pytest, implement, then run `uv run pytest` with coverage gate 0.70.

| Blocker | Tests |
|---|---|
| B1 | In `tests/test_tickets_cog.py`, mock slash `ctx.interaction` and assert `ctx.send(..., ephemeral=True)`; mock prefix `ctx.interaction = None`, `ctx.author.send = AsyncMock()`, assert DM contains notes and channel confirmation does not. |
| B2 | Parametrize service statuses `open`, `claimed`; assert `ValueError` and no channel creation. Cog tests assert exact Spanish error text and service not called. |
| B3 | Mock parent owner member/fetch path; assert `create_text_channel(overwrites=...)` contains parent owner, not invoker, and `channel.send(content=parent_author.mention, ...)`. |
| B4 | Mock each DB/service call to raise; patch `bot.cogs.tickets.logger.exception`; assert `error_embed` response and no traceback text in user-facing embed. |

## File-by-file Changes

| File | Action | Description |
|---|---|---|
| `bot/cogs/tickets.py` | Modify | B1 routing, B2 cog guard, B3 parent-owner overwrites/mention, B4 scoped error handling. |
| `bot/services/ticket_service.py` | Modify | B2 service status guard before category/channel creation. |
| `tests/test_tickets_cog.py` | Modify | Add cog-level RED tests for privacy, guards, access, and DB failure handling. |
| `tests/test_ticket_service.py` | Modify | Add service-level RED tests for non-closed reopen rejection. |

## Risks

- Medium: `fetch_member` can fail for deleted/unavailable users; fail safely before channel creation.
- Low: broad Supabase exception types require scoped `except Exception`; mitigate with one-call try blocks and full logging.
- Low: existing tests call command callbacks directly, so slash/prefix mocks must model `ctx.interaction` accurately.

## Open Questions

None.
