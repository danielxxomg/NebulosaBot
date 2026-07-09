# Design: Ticket Intake UX

## Technical Approach

Replace the category-select creation path with a two-interaction flow: category selection opens a `TicketIntakeModal`; modal submission defers and reuses the existing channel, permission, persistence, welcome, and success flow. This implements the proposal and the planned `ticket-model`, `ticket-views`, and `ticket-service` deltas without changing cache or Realtime behavior.

`subject` and `description` are nullable ticket metadata. The welcome embed renders a subject-specific title and, when supplied, a non-inline details field; existing rows retain the current localized fallback title and welcome text.

## Architecture Decisions

### Interaction acknowledgement

| Option | Tradeoff | Decision |
|---|---|---|
| Defer the select, then open a modal | A deferred interaction cannot issue the modal response | Reject |
| Send the modal from the select, defer on submit | Uses one response per interaction and preserves time for I/O | Use |

`_CategorySelect.callback()` MUST call `interaction.response.send_modal(...)` as its first response. `TicketIntakeModal.on_submit()` MUST call `interaction.response.defer(ephemeral=True)` before config/DB/Discord I/O.

### Metadata persistence

| Option | Tradeoff | Decision |
|---|---|---|
| Embed or pinned-message only | Context is not structured or durable | Reject |
| Nullable `ticket.subject` and `ticket.description` | Requires an additive migration | Use |

Nullable fields preserve old tickets and keep sub-ticket callers compatible. Existing `TicketDBMixin` writes continue to invoke `_on_write`; no new cache key or Realtime subscription is needed.

### Welcome message and pin

| Option | Tradeoff | Decision |
|---|---|---|
| Separate pinned intake message | Extra message and lifecycle | Reject |
| Pin existing welcome/action message | Buttons and context remain together | Use |

After `channel.send(...)`, pin the returned message before sending success. A pin `HTTPException` is logged and does not roll back the already-persisted, usable ticket.

### Form scope

| Option | Tradeoff | Decision |
|---|---|---|
| Category-specific schemas now | Needs schema, validation, and admin UX | Defer |
| Universal title and description | Fits the focused intake change | Use |

## Data Flow

```text
User -> _CategorySelect: choose category
_CategorySelect -> Discord: send_modal(TicketIntakeModal)  [first response; no defer]
User -> TicketIntakeModal: submit title + optional description
TicketIntakeModal -> Discord: defer(ephemeral=True)         [first submit response]
TicketIntakeModal -> GuildService/DB: config, category, next number
TicketIntakeModal -> TicketService -> TicketDBMixin: create channel + insert metadata
TicketIntakeModal -> TextChannel: send welcome/actions -> pin message
TicketIntakeModal -> Discord: ephemeral success follow-up
```

The modal owns immutable `guild` and `category_id` context. Its submit handler delegates the existing post-validation workflow to a private view helper, avoiding duplicated creation/error handling.

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/013_ticket_intake_metadata.sql` | Create | Idempotently add nullable `subject` and `description` text columns. |
| `bot/models/ticket.py` | Modify | Map and serialize nullable metadata. |
| `bot/core/db/ticket_db.py` | Modify | Accept metadata and include it in `insert_ticket()` rows. |
| `bot/services/ticket_service.py` | Modify | Thread optional metadata through main and sub-ticket channel creation. |
| `bot/views/tickets.py` | Modify | Add modal, modal-first timing, shared creation helper, and welcome pin. |
| `bot/utils/embeds.py` | Modify | Render subject title, optional details field, and null fallback. |
| `bot/locales/en.json`, `bot/locales/es.json` | Modify | Add modal, title-format, and details-field keys. |
| `tests/test_ticket_model.py`, `tests/test_database.py`, `tests/test_ticket_service.py`, `tests/test_tickets_cog.py`, `tests/test_tickets_i18n.py` | Modify | Add strict-TDD coverage for the contracts below. |

## Interfaces / Contracts

```python
Ticket.subject: str | None = None
Ticket.description: str | None = None

async def create_ticket(..., *, subject: str | None = None, description: str | None = None) -> Ticket: ...
async def create_ticket_channel(..., *, subject: str | None = None, description: str | None = None) -> tuple[discord.TextChannel, Ticket]: ...
```

`TicketIntakeModal` uses a required short Title (maximum 100 characters) and optional paragraph Description (maximum 2,000 characters). Blank optional input persists as `None`; sub-ticket creation passes neither field and remains valid.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Model/DB mapping, service forwarding, embed subject/fallback, locale keys | `pytest` with existing fake Supabase and mocks |
| Integration | Select opens modal; submit defers before service I/O; metadata, send, and pin sequence | Mocked Discord interactions/channels in ticket flow tests |
| E2E | Not available | No Discord API calls; validate with `uv run pytest` |

## Migration / Rollout

Apply `013_ticket_intake_metadata.sql` to Supabase before deploying bot code. It is additive, idempotent, and requires no backfill; pre-existing tickets read `NULL` and use the fallback. Roll back application code first; dropping columns is optional and destructive for newly captured intake metadata.

## Open Questions

None.
