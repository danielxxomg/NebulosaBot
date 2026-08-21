# Delta for Ticket Service

Cycle 2 of 3. Adds the `,12h` scheduled-close timer to `TicketService`. A mod
in an open/claimed ticket channel types `,12h` (strict regex via
`parse_duration_strict`); the service sets `scheduledCloseAt`/`scheduledCloseBy`
and posts a pinned embed with `⏳ <t:unix:R> (<t:unix:F>)` using
`format_remaining()`. A `@tasks.loop(seconds=60)` batch of 50 closes tickets
whose `scheduledCloseAt <= now()`, idempotent via the existing
`already_closed` path. `,cancel` clears `scheduledCloseAt`/`scheduledCloseBy`.
Overwriting (re-typing `,12h` in the channel) extends the timer. The 48h
`AUTO_CLOSE` sweep and the scheduled timer MUST coexist without double-close.
Channel-not-DM: the timer prefix is only honored inside a ticket channel.

## ADDED Requirements

### Requirement: Scheduled-close timer prefix listener

The system MUST honor a `,<duration>` prefix in ticket channels via the
existing `on_message` listener (`bot/cogs/tickets.py`). The message MUST be
in a ticket channel (channel-not-DM: DMs are ignored) AND the ticket MUST be
`open` or `claimed` AND the author MUST pass `is_mod` (guild-scoped
`is_mod_check`). The duration MUST be parsed with `parse_duration_strict`
(strict regex `^,\s*(\d+\s*[smhdwy])+$`); on failure (e.g. `,hola`) the
listener MUST ignore the message (no error embed, no scheduled close). On
success, the service MUST set `scheduledCloseAt = now() + duration` and
`scheduledCloseBy = author_id`, and post a pinned embed carrying the scheduled
close time. Typing `,12h` again in the same channel MUST overwrite (extend)
the timer to the new `scheduledCloseAt`.

#### Scenario: Mod schedules close in open ticket channel

- GIVEN an open ticket channel and a mod author
- WHEN the mod sends `,12h`
- THEN `scheduledCloseAt = now() + 12h`, `scheduledCloseBy = mod_id`, and a pinned embed is posted

#### Scenario: Mod schedules close in claimed ticket channel

- GIVEN a claimed ticket channel and a mod author
- WHEN the mod sends `,6h`
- THEN the timer is set on the claimed ticket

#### Scenario: Non-mod ignored

- GIVEN an open ticket channel and a non-mod author
- WHEN the author sends `,12h`
- THEN no timer is set and no scheduled-close embed is posted

#### Scenario: DM ignored (channel-only)

- GIVEN a DM channel with a mod author
- WHEN the mod sends `,12h`
- THEN the message is ignored (the timer prefix is channel-only, not DM)

#### Scenario: Closed ticket ignored

- GIVEN a closed ticket channel and a mod author
- WHEN the mod sends `,12h`
- THEN no timer is set (only open/claimed tickets are eligible)

#### Scenario: Non-duration input ignored

- GIVEN an open ticket channel and a mod author
- WHEN the mod sends `,hola`
- THEN `parse_duration_strict` returns `None`, no timer is set, and no error embed is sent

#### Scenario: Overwrite extends the timer

- GIVEN an open ticket channel with `scheduledCloseAt = now() + 1h` and a mod author
- WHEN the mod sends `,4h`
- THEN `scheduledCloseAt` is overwritten to `now() + 4h` (extend), not additive to the prior value

### Requirement: Scheduled-close loop is 60s, batch 50, idempotent

The system MUST run a `@tasks.loop(seconds=60)` that selects scheduled-close
candidates in batches of 50 per run using the partial index
(`status IN ('open','claimed') AND scheduledCloseAt <= now()`). For each
candidate, the loop MUST call `close_ticket_full` (silent — no countdown) and
MUST clear `scheduledCloseAt`/`scheduledCloseBy` on close. The loop MUST be
idempotent: a candidate already closed by another path (the 48h `AUTO_CLOSE`
sweep, manual close, or a duplicate loop tick) MUST produce the existing
`already_closed` no-op and MUST NOT double-close or double-delete the channel.
`cog_unload()` MUST cancel the loop; a stale leftover timer is harmless (the
next loop tick or manual close resolves it). A `TICKET_TIMER_ENABLED` flag
SHOULD allow disabling the loop without disabling the 48h sweep.

#### Scenario: Loop closes a due scheduled ticket

- GIVEN an open ticket with `scheduledCloseAt` in the past and the loop running
- WHEN the loop tick selects it (batch 50)
- THEN `close_ticket_full` closes it silently, `scheduledCloseAt`/`scheduledCloseBy` are cleared, and the channel is deleted

#### Scenario: Loop is idempotent on already-closed ticket

- GIVEN a ticket was already closed by the 48h `AUTO_CLOSE` sweep and still has `scheduledCloseAt` set
- WHEN the loop tick selects it
- THEN `close_ticket_full` returns the `already_closed` no-op, no second close occurs, and `scheduledCloseAt` is cleared

#### Scenario: Batch size 50 is enforced

- GIVEN 120 due scheduled tickets and batch size 50
- WHEN one loop tick runs
- THEN at most 50 candidates are processed; the remainder are left for the next tick

#### Scenario: cog_unload cancels the loop

- GIVEN the loop is running
- WHEN the cog unloads
- THEN the loop is cancelled and no new tick fires (a stale leftover timer is harmless)

### Requirement: ,cancel clears the scheduled timer

The system MUST honor a `,cancel` prefix in a ticket channel with an
`is_mod` author (open/claimed ticket). It MUST clear `scheduledCloseAt = NULL`
and `scheduledCloseBy = NULL` and post a confirmation. Cancelling a ticket
with no scheduled close MUST be a safe no-op (no error). `,cancel` MUST NOT
affect the 48h `AUTO_CLOSE` sweep (it clears only the scheduled timer, not
the inactivity clock).

#### Scenario: Mod cancels a scheduled close

- GIVEN an open ticket with `scheduledCloseAt` set and a mod author
- WHEN the mod sends `,cancel`
- THEN `scheduledCloseAt` and `scheduledCloseBy` are set to NULL and a confirmation is posted

#### Scenario: Cancel with no scheduled close is a no-op

- GIVEN an open ticket with `scheduledCloseAt = NULL` and a mod author
- WHEN the mod sends `,cancel`
- THEN a safe confirmation is posted and no error is raised

#### Scenario: Cancel does not disable AUTO_CLOSE

- GIVEN an open ticket inactive for 47h and a mod author
- WHEN the mod sends `,cancel` (clearing a prior `,12h`)
- THEN the 48h `AUTO_CLOSE` sweep still applies to the ticket's inactivity clock

### Requirement: format_remaining and <t:R>/<t:F> display

The system MUST provide `format_remaining(seconds: int) -> str` that formats
a remaining duration as a localized human string (e.g. "12h", "1d 6h"). The
scheduled-close embed MUST carry `⏳ Cierra <t:unix:R> (<t:unix:F>)` — the
Discord relative timestamp (`<t:R>`, "in 12 hours") and the absolute formatted
timestamp (`<t:F>`, full date/time) — computed from `scheduledCloseAt`. The
embed text MUST be localized via `t()` (Spanish and English). The pinned
embed MUST be editable/extendable when the timer is overwritten (the service
SHOULD edit the existing pinned embed on overwrite rather than post a new one).

#### Scenario: format_remaining localizes a duration

- GIVEN `format_remaining(43200)`
- WHEN it runs with the guild locale `es`
- THEN it returns a localized "12h"-style string

#### Scenario: Scheduled-close embed carries <t:R> and <t:F>

- GIVEN a scheduled close set to `now() + 12h`
- WHEN the embed is posted
- THEN it contains `⏳ <t:{unix}:R> (<t:{unix}:F>)` with `unix` = the `scheduledCloseAt` epoch seconds

#### Scenario: Overwrite edits the pinned embed

- GIVEN a pinned scheduled-close embed exists and the mod sends `,4h`
- WHEN the timer is overwritten
- THEN the pinned embed is edited to the new `<t:R>`/`<t:F>` rather than a second pinned embed being created

## MODIFIED Requirements

### Requirement: Auto-close stale tickets

The system MUST automatically close tickets that have been inactive for 48 hours via the existing `@tasks.loop(hours=1)` `AUTO_CLOSE` sweep. The 48h sweep and the Cycle 2 scheduled-close `@tasks.loop(seconds=60)` MUST coexist: both may select the same ticket, but `close_ticket_full` MUST be idempotent (`already_closed` no-op on the second), so a ticket is never double-closed or double-deleted. The 48h sweep MUST clear `scheduledCloseAt`/`scheduledCloseBy` when it closes a ticket that also had a scheduled timer, so no stale scheduled time lingers. The 48h sweep is silent (no countdown); the scheduled timer loop is also silent.
(Previously: the 48h sweep was the only auto-close path and silently deleted stale tickets; no scheduled timer or coexistence contract existed.)

#### Scenario: Stale ticket

- GIVEN a ticket with `lastActivity` older than 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket is closed silently without warning and the channel is deleted

#### Scenario: Active ticket

- GIVEN a ticket with `lastActivity` within 48 hours
- WHEN the hourly auto-close task runs
- THEN the ticket remains open

#### Scenario: AUTO_CLOSE and scheduled timer coexist without double-close

- GIVEN a ticket with `lastActivity` older than 48h AND `scheduledCloseAt` in the past
- WHEN both the 48h sweep and the 60s loop tick fire
- THEN exactly one `close_ticket_full` succeeds and the other returns `already_closed`; `scheduledCloseAt`/`scheduledCloseBy` are cleared; the channel is deleted once

#### Scenario: AUTO_CLOSE clears a lingering scheduled timer

- GIVEN a ticket with `lastActivity` older than 48h and `scheduledCloseAt` still set (future)
- WHEN the 48h sweep closes it
- THEN `scheduledCloseAt`/`scheduledCloseBy` are cleared so no stale scheduled time lingers

## Scope boundary

This delta adds the `,12h`/`,cancel` listener, the 60s loop, `format_remaining`,
`<t:R>`/`<t:F>` display, and the AUTO_CLOSE coexistence contract. The strict
parser is specified in `time-parsing`; the scheduled-close columns and partial
index in `ticket-model`; the `<2h`/`>5d` confirm in `close-confirmation`;
the silent-vs-countdown distinction in `close-countdown`. Cycle 3
(voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
