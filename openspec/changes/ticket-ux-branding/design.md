# Design: Ticket UX & Branding Overhaul

## Technical Approach

Keep Discord interaction in views/cogs and lifecycle rules in `TicketService`. Reuse the existing ephemeral confirmation view, centralize deletion timing in the service, and derive names/assets through shared utilities. This implements all ticket, branding, channel-naming, and manual delta specs without schema changes.

## Architecture Decisions

| Decision | Choice | Rejected / tradeoff | Rationale |
|---|---|---|---|
| Confirmation UI | Reuse `ConfirmCancelView` (30s, owner-only) for close and claim-transfer. | New persistent `CloseConfirmView`; unnecessary for ephemeral dialogs. | It already disables on cancel/timeout and enforces ownership; dismiss naturally performs no mutation. |
| Close timing | `TicketService.close_ticket_full(..., manual: bool)` owns countdown/delete. | Sleeps or countdown in `TicketActionsView`/cog. | Keeps Discord UI thin and makes manual versus auto-close testable. |
| Unclaim authorization | Cog resolves shared mod access; service receives `is_mod`, runs a pure invariant, mutates/audits. | `@is_mod()` (would exclude the claimer), DB role lookup. | Supports hybrid prefix/slash invocation and preserves cache-first role resolution. |
| Naming | Service generates both tentative and final names with one sanitizer. | Per-cog string formatting. | Covers initial create, retry rename, subtickets, and reopen consistently. |
| Branding assets | Optional `bot` argument in embed factories plus bot/guild URL resolvers. | Static Imgur URL or CDN asset. | Avatar changes propagate automatically; guild-context embeds remain server-specific. |

## Data Flow

```text
Close click -> permission + ticket lookup -> ephemeral ConfirmCancelView
    Confirm -> acknowledge ephemeral -> TicketService (transcript -> DB close
              -> one 5..1 message/edit loop -> channel delete)
Auto-close ---------------------------------> TicketService(manual=False)
                                             -> silent 5s delay -> delete

/unclaim -> shared mod resolution -> TicketService + invariant -> DB/audit
Claimed Claim -> ephemeral confirmation -> transfer_ticket -> edit original ticket message
```

The confirm callback immediately edits its ephemeral response before service work; failures use an ephemeral follow-up. After sending either dialog, retain `await interaction.original_response()` in `view.message` so timeout can disable it. `close_ticket_full` sends one numeric message, then iterates `5..1`, sleeping once after each display and editing after the first. Only this service helper sleeps. It logs and re-raises `CancelledError`, so a cancelled task never reaches deletion; `discord.HTTPException` during countdown is logged and falls back to the silent delay. Auto-close explicitly passes `manual=False` and retains the silent delay.

## Interfaces / Contracts

```python
async def close_ticket_full(..., *, bot: NebulosaBot, manual: bool) -> str | None
async def unclaim_ticket(ticket_id: str, actor_id: str, *, is_mod: bool) -> Ticket
def check_can_unclaim(actor_id: str, ticket: dict, *, is_mod: bool) -> None
def sanitize_channel_name(category: str, username: str, ticket_number: int) -> str
```

`check_can_unclaim` requires a claimed ticket and permits its claimer or a moderator; the service writes `unclaim` success/denied audits. Add a shared member/context mod predicate in `bot/utils/checks.py` so `is_mod_check` and the hybrid command use identical cached-role logic.

The sanitizer applies Unicode NFKD ASCII folding, lowercase, whitespace-to-hyphen, removes non-`[a-z0-9-]`, collapses/strips hyphens, uses `ticket`/`user` fallbacks, and truncates the prefix while preserving `-{number:04d}` within 100 characters. Creation passes selected category name through modal/service; subtickets resolve the parent category; reopen resolves its category and author member, falling back safely when either is unavailable. Remove cog-side tentative/final string formatting.

`bot/utils/brand.py` exports `PRIMARY`, `ACCENT`, `SUCCESS`, `WARNING`, `ERROR`, and `INFO`. `embeds.py` removes `COLOR_*`/`FOOTER_ICON`, uses tokens, and provides bot-avatar and guild-icon-with-bot-fallback resolvers. Factory callers pass their bot; ticket panel receives its guild and uses the guild icon. Logging applies the guild asset before send. Direct embed users import brand tokens.

## File Changes

| File | Action | Description |
|---|---|---|
| `bot/utils/brand.py` | Create | Palette constants. |
| `bot/utils/embeds.py`, `bot/views/confirmation.py` | Modify | Asset resolvers, tokenized factories/confirmation embeds. |
| `bot/views/tickets.py` | Modify | Confirmed close/transfer flows, panel guild asset, category-name propagation. |
| `bot/services/ticket_service.py`, `bot/services/ticket_invariants.py` | Modify | Countdown, unclaim/audit, centralized naming. |
| `bot/utils/ticket_helpers.py`, `bot/utils/checks.py` | Modify | Sanitizer and reusable mod predicate. |
| `bot/cogs/tickets.py`, `bot/bot.py` | Modify | `/unclaim`, no duplicate naming, explicit close mode, panel guild wiring. |
| `bot/cogs/{core,sentinel,stellar,utility}.py`, `bot/listeners/xp_listener.py`, `bot/services/logging_service.py` | Modify | Brand-token and context-asset adoption. |
| `bot/locales/en.json`, `bot/locales/es.json` | Modify | Close/transfer confirmation and unclaim keys. |
| `docs/MANUAL.md` | Modify | Spanish §§1, 6, 7, and 8: branding note; naming; `/unclaim`; claim transfer; close confirm/countdown/dismiss behavior. |
| `tests/test_{confirm_view,ticket_views,ticket_service,ticket_invariants,tickets_cog,tickets_i18n}.py`, `tests/contract/test_ticket_invariants.py`, `tests/integration/test_ticket_flow.py` | Modify | TDD coverage for new flows. |
| `tests/test_{bot,greetings_cog,utility_cog,ocio_cog,stellar_cog}.py` | Modify | Replace legacy color assertions. |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Sanitizer edge cases; invariant/service audits; countdown send/edit/sleep/cancel; asset fallbacks. | Write RED pytest cases first; mock Discord/DB and patch service sleep. |
| Integration | Close confirm→countdown and claimed-claim→transfer; hybrid unclaim wiring. | Mock interactions/messages; verify public ticket message refresh and silent auto-close. |
| E2E | Not available. | No Discord API calls. |

Run `uv run pytest` after every RED/GREEN slice and for final verification.

## Migration / Rollout

No database migration required. Existing channels retain their names; new, reopened, and subticket channels use the format. Roll back independently by restoring direct close, removing `/unclaim`, and reverting token imports; no persisted data must be reversed.

Suggested chained slices (auto-forecast, ~1,320 lines total / 1,500 budget): (1) branding/assets, ~330; (2) close confirmation/countdown, ~320; (3) unclaim and claim-transfer, ~350; (4) naming plus Spanish manual, ~320. Each is independently testable and revertible.

## Risks

- Cancellation after DB close can retain a closed channel; it is deliberately not deleted and is recoverable through the existing reopen flow.
- Reopen cannot recover a departed author's username; sanitizer uses its documented fallback.
- Brand changes alter visual-only assertions across the suite; token assertions prevent drift.

## Open Questions

None.
