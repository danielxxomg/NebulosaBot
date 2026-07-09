# Exploration: Ticket Intake UX

## Current State

The ticket intake flow is:

1. User clicks **Open Ticket** button on panel (`TicketPanelView` → `bot/views/tickets.py:39`)
2. Bot sends ephemeral category select dropdown (`_CategorySelectView`)
3. User picks a category → `_CategorySelect.callback()` (line 261) fires
4. Bot creates the Discord channel via `TicketService.create_ticket_channel()`
5. Bot sends a welcome embed + `TicketActionsView` (claim/close) in the new channel (line 356)
6. User gets an ephemeral success message with the channel link

**What's missing:**
- No modal — user never enters a subject or description
- No pinning — the welcome embed is sent but never pinned
- Ticket model (`bot/models/ticket.py`) has NO `subject` or `description` columns
- `build_ticket_embed()` (`bot/utils/embeds.py:137`) only shows ticket number, status, and author mention
- No `discord.ui.Modal` exists anywhere in the codebase
- No `.pin()` call exists anywhere in the codebase

## Affected Areas

| File | Why |
|------|-----|
| `bot/views/tickets.py` | `_CategorySelect.callback()` — insert modal before channel creation; pin message after |
| `bot/models/ticket.py` | Add `subject` and `description` fields |
| `bot/core/db/ticket_db.py` | `insert_ticket()` — accept and store new columns |
| `bot/services/ticket_service.py` | `create_ticket()` / `create_ticket_channel()` — pass subject/description through |
| `bot/utils/embeds.py` | `build_ticket_embed()` — display subject in the welcome embed |
| `bot/locales/es.json` | New i18n keys for modal title, labels, placeholders, pin message |
| `bot/locales/en.json` | Same |
| `openspec/specs/ticket-model/spec.md` | Delta: new model fields |
| `openspec/specs/ticket-views/spec.md` | Delta: modal flow + pinning |
| `openspec/specs/ticket-service/spec.md` | Delta: create_ticket accepts subject/description |

## Approaches

### A) Field Templates: How to define what the modal shows

| Option | Description | Pros | Cons | Effort |
|--------|-------------|------|------|--------|
| **Hardcoded per category slug** | Map known category names (e.g. "Report", "Bug") to fixed field sets in code | Simple, no DB schema change, predictable UX | Not configurable per guild, requires code change to add new templates | Low |
| **DB-configurable field schemas** | Store a JSON schema per `ticket_category` row defining field labels, placeholders, required/optional | Fully configurable per guild, admins control their own forms | Complex schema design, migration, admin UX for configuring fields, validation logic | High |
| **Hybrid (recommended)** | Hardcoded universal fields (title + description) for ALL categories; optional per-category `extra_fields` JSON on `ticket_category` later | Ships fast with universal fields, extensible later without breaking | Phase 2 still needed for category-specific fields | Low now, Med later |

**Recommendation: Hybrid.** This cycle ships universal Title + Description for all categories. Category-specific fields are a separate cycle.

### B) Where to Store Subject/Description

| Option | Description | Pros | Cons | Effort |
|--------|-------------|------|------|--------|
| **New DB columns on `ticket`** | Add `subject TEXT` and `description TEXT` nullable columns | Queryable, structured, transcript can include them, audit-friendly | Requires migration, model update | Low |
| **Embed-only (no DB)** | Subject/description only live in the welcome embed text | No migration | Lost on channel delete, not queryable, can't include in transcripts reliably | Low |
| **First pinned message only** | Store in the pinned message content | No migration, visible in channel | Lost on channel delete, not queryable, no structured data | Low |

**Recommendation: New DB columns.** The fields are valuable for transcripts, audit, and future search. Nullable columns are backward-compatible with existing tickets. The migration is trivial (two `ALTER TABLE ADD COLUMN` statements).

### C) Pin Strategy

| Option | Description | Pros | Cons | Effort |
|--------|-------------|------|------|--------|
| **Pin the welcome embed** | `message.pin()` on the existing welcome embed that already has ticket# + author + actions | Single message, already exists, contains claim/close buttons | Pinned message includes interactive buttons (slightly unusual but functional), embed may get long if we add subject+description | Low |
| **Dedicated reason message** | Send a separate lightweight message with subject + description, pin that, keep welcome embed unpinned | Clean separation, pinned message is pure information | Two messages in channel, extra API call, need to manage unpin on close | Low |
| **Both** | Pin welcome embed AND a reason message | Maximum context | Two pinned messages = clutter, more cleanup on close | Med |

**Recommendation: Pin the welcome embed.** It already contains ticket# + author. We add subject to the embed. One pin, one message, minimal complexity. On close, the channel is deleted anyway so unpin is unnecessary.

### D) Modal API Constraints (Discord.py / Discord API)

Verified constraints:

- **Max 5 components** per modal (each `TextInput` = 1 component, each occupies 1 `ActionRow`)
- **Modal title**: max 45 characters
- **TextInput label**: max 45 characters
- **TextInput placeholder**: max 100 characters
- **TextInput style.short** (single-line): max 100 characters input
- **TextInput style.paragraph** (multi-line): max 4000 characters input
- **No images, no selects, no buttons** inside a modal — only `TextInput`
- **No nested modals** — can't open a modal from a modal
- Modal is **ephemeral** — only the interacting user sees it
- `interaction.response.send_modal()` must be the FIRST response (can't defer then send modal)
- Timeout: modal interaction expires after ~10 minutes of inactivity

**Impact on this feature:**
- 2 fields (Title + Description) = 2 of 5 components used — plenty of room
- Title field: `TextInput(style.short, max_length=100, required=True)`
- Description field: `TextInput(style.paragraph, max_length=2000, required=False)` — 4000 is the API max but 2000 is practical for a ticket description
- Category-specific fields later would use remaining 3 slots (max 5 total)
- **Critical**: Current code does `await interaction.response.defer(ephemeral=True)` before channel creation (line 267). Modal must be sent BEFORE deferring — the flow must change to: category select → send modal → modal callback does the rest.

### E) Scope for ONE Focused SDD Cycle

**Recommended scope (shippable, reviewable, ~200-300 lines changed):**

1. **Modal after category selection** — `TicketIntakeModal` with Title (required, short) + Description (optional, paragraph)
2. **New DB columns** — `subject TEXT`, `description TEXT` on `ticket` table (nullable, backward-compatible)
3. **Model update** — `Ticket` dataclass gets `subject` and `description` fields
4. **Service update** — `create_ticket()` / `create_ticket_channel()` accept and pass through subject/description
5. **Embed update** — `build_ticket_embed()` shows subject as embed title or field
6. **Pin the welcome embed** — `await message.pin()` after sending the welcome embed
7. **i18n** — New keys for modal title, labels, placeholders in `es.json` and `en.json`
8. **Specs** — Delta specs for ticket-model, ticket-views, ticket-service

**Out of scope for this cycle:**
- Category-specific extra fields (needs DB schema design for field definitions)
- Guild/server icon in modal (impossible — modals don't support images)
- Editing subject/description after creation
- Subject in transcript output (separate transcript-service change)

## Recommendation

**Go with the hybrid approach in a single focused cycle.**

The flow changes from:

```
Panel → Category Select → Defer → Channel Create → Send Welcome → Followup Success
```

To:

```
Panel → Category Select → Send Modal → Modal Submit → Defer → Channel Create → Send+Pin Welcome → Followup Success
```

Key design decisions:
- Modal is sent as the response to the category select interaction (replaces the current `defer`)
- Modal callback does everything the current `_CategorySelect.callback()` does
- Welcome embed gets the subject as its title (or a field), and is pinned
- `description` goes in the embed body if present
- Both fields are nullable in DB — existing tickets show "Ticket #XXXX" as before

**Estimated scope**: ~250-350 lines across 8-10 files. One PR, well within the 400-line review budget.

## Risks

- **Modal blocks the current defer pattern** — the `_CategorySelect.callback()` currently defers immediately. With a modal, we must send the modal as the first response. If channel creation takes >3s, Discord's interaction timeout (15 min for modals, but the modal submit interaction has a 3-second initial response window) could be an issue. Mitigation: defer on modal submit, not on category select.
- **Pin rate limits** — Discord rate-limits pin operations (~5 per 5 seconds per channel). Since tickets are created one at a time per user, this is unlikely to hit in practice.
- **Backward compatibility** — Existing tickets with `subject=NULL` must render gracefully in `build_ticket_embed()`. The embed should fall back to the current "Ticket #XXXX" title when subject is null.
- **subticket flow** — `create_ticket_channel()` is also called for sub-tickets (via `create_subticket`). The modal only fires for the main panel flow; sub-tickets created via `/subticket create` won't have a modal. Subject/description should be optional parameters.

## Ready for Proposal

**Yes** — the exploration is complete. One product question remains (see below) that the orchestrator should resolve before proposing.

## PRODUCT QUESTIONS for Orchestrator

1. **Description field required or optional?** The modal can make it required or optional. My recommendation: Title = required, Description = optional. Confirm with user.

2. **Subject as embed title or field?** Two options:
   - Subject replaces the embed title: `"Ticket #0003 — My report subject"` (concise, visible)
   - Subject as a named field inside the embed: title stays as "Ticket #0003", subject is a field (more structured)
   - Recommendation: replace the embed title with subject, keep "Ticket #XXXX" as a footer or prefix.

3. **Pin cleanup on close?** The channel is deleted on close, so pins are destroyed with it. No cleanup needed. But if the channel is ever NOT deleted (future change), we'd need unpin logic. Confirm this is acceptable.

4. **Category-specific fields — any immediate need?** If any category has an urgent need for custom fields (e.g., "Report" needs a player nickname), we could squeeze a 3rd field into this cycle using the remaining modal slots. Otherwise, defer to next cycle.
