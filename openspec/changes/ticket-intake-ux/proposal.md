# Proposal: Ticket Intake UX

## Intent

The ticket intake flow creates a channel immediately after category selection — users never provide context. Staff open tickets blind, wasting time asking "what's this about?". This change inserts a Title+Description modal between category select and channel creation, giving tickets structured metadata from the start.

## Scope

### In Scope
- `TicketIntakeModal` (Title required, Description optional) shown after category select
- `subject` and `description` columns on `ticket` table (nullable, backward-compatible)
- `Ticket` dataclass updated with new fields
- `create_ticket()` / `create_ticket_channel()` accept and persist subject/description
- `build_ticket_embed()` shows subject as embed title (`"#0003 — My subject"`)
- Welcome embed pinned after channel creation
- i18n keys for modal labels/placeholders in `es.json` and `en.json`

### Out of Scope
- Category-specific field schemas (future cycle)
- Server image in modal (Discord API limitation — cannot embed images in modals)
- Editing subject/description after creation
- Subject in transcript output (separate change)
- Sub-ticket modal (sub-tickets created via command, not panel)

## Capabilities

### New Capabilities
- `ticket-intake-modal`: Modal-based ticket intake with subject (required) and description (optional), triggered after category selection in the panel flow

### Modified Capabilities
- `ticket-model`: Add `subject` and `description` nullable text fields to Ticket dataclass and DB row mapping
- `ticket-views`: Replace deferred category callback with modal-first flow; pin welcome embed after channel creation
- `ticket-service`: `create_ticket()` accepts optional subject/description parameters and persists them

## Approach

Replace the current category-select → defer → create flow with category-select → modal → submit → defer → create → pin.

**Flow change:**
```
Before: Panel → Category Select → Defer → Channel Create → Send Welcome → Success
After:  Panel → Category Select → Modal → Submit → Defer → Channel Create → Send+Pin Welcome → Success
```

Key implementation details:
- `_CategorySelect.callback()` sends `TicketIntakeModal` as the interaction response (replaces `defer`)
- Modal submit callback defers, then runs the existing channel creation + welcome flow
- `subject` passed to `build_ticket_embed()` as the embed title prefix
- `message.pin()` called on the welcome embed after send
- Nullable columns ensure existing tickets render with fallback `"Ticket #XXXX"` title
- `create_ticket_channel()` accepts optional `subject`/`description` for sub-ticket passthrough

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `bot/views/tickets.py` | Modified | New `TicketIntakeModal` class; `_CategorySelect.callback()` sends modal instead of deferring |
| `bot/models/ticket.py` | Modified | Add `subject: str | None` and `description: str | None` fields |
| `bot/core/db/ticket_db.py` | Modified | `insert_ticket()` maps new columns |
| `bot/services/ticket_service.py` | Modified | `create_ticket()` / `create_ticket_channel()` accept subject/description |
| `bot/utils/embeds.py` | Modified | `build_ticket_embed()` includes subject as title when present |
| `bot/locales/es.json` | Modified | New i18n keys for modal |
| `bot/locales/en.json` | Modified | New i18n keys for modal |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Modal submit timeout (>3s before defer) | Low | Defer is the first action in modal callback; channel creation is fast |
| Backward compat — existing tickets with null subject | Low | Embed falls back to "Ticket #XXXX" when subject is null |
| Pin rate limits | Low | One pin per ticket creation; sequential per user flow |
| Sub-ticket flow bypasses modal | Low | subject/description are optional params; sub-tickets work without them |

## Rollback Plan

1. Revert `_CategorySelect.callback()` to pre-modal flow (defer → create directly)
2. Drop `subject` and `description` columns via `ALTER TABLE ticket DROP COLUMN subject, DROP COLUMN description`
3. Remove `TicketIntakeModal` class
4. Remove `message.pin()` call
5. Existing tickets unaffected — nullable columns mean no data loss during rollback window

## Dependencies

- None — pure Discord.py modal API, no external services

## Success Criteria

- [ ] User sees Title+Description modal after selecting a ticket category
- [ ] Title is required; Description is optional
- [ ] Welcome embed displays subject as title (e.g. "#0003 — My subject")
- [ ] Welcome embed is pinned in the ticket channel
- [ ] Existing tickets (null subject) render with fallback title
- [ ] All new i18n keys present in `es.json` and `en.json`
- [ ] Sub-ticket creation still works without subject/description
