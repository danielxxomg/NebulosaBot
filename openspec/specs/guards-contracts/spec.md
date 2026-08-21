# Guards and Contracts Specification

## Purpose

Cycle 1 DRY extracts: collapse repeated guards and helpers into single
shared modules so duplication drops ~240 lines. Covers the dashboard
`verifyGuildAdmin` x4, the cog `_err`/`_ok` embed helpers x4, the
`select("*")` x13, the local `INFO` brand bypass, and the explicit contract
that `time.py` and `timeparse.py` MUST NOT be merged.

## Requirements

### Requirement: Shared verifyGuildAdmin guard

The four near-identical `verifyGuildAdmin` definitions in
`dashboard/lib/actions/{economy,guild,greeting,ticket}-actions.ts` (each ~40
lines, differing only in the final error string) MUST be replaced by a single
shared guard in a dashboard lib module. Each action file MUST import the
shared guard and supply its error string, rather than redefining the guard.

#### Scenario: Single shared guard definition

- GIVEN the dashboard action files
- WHEN scanned for `verifyGuildAdmin` definitions
- THEN exactly one definition exists in a shared lib module and the four action files import it

#### Scenario: Error string is parameterized

- GIVEN the shared guard
- WHEN an action invokes it
- THEN the caller supplies its domain-specific error string and the guard behavior is identical across domains

### Requirement: Shared embed error/success helpers

The duplicated `_err`/`_ok` (or equivalent) embed helper pairs across four
cogs MUST be extracted to `bot/utils/embeds.py` as single helpers. Cogs MUST
import those helpers instead of redefining them.

#### Scenario: Single embed helper pair

- GIVEN the four cogs that define `_err`/`_ok` helpers
- WHEN scanned for those definitions
- THEN zero local definitions remain and all four import from `bot/utils/embeds.py`

### Requirement: Explicit column lists replace select star

The four `select("*")` calls in `ticket-actions.ts` (and any other
`select("*")` in the dashboard actions, ~13 occurrences total) MUST be
replaced with explicit column lists. `select("*")` MUST NOT appear in the
dashboard action files after this change.

#### Scenario: No select star in dashboard actions

- GIVEN `dashboard/lib/actions/*-actions.ts`
- WHEN scanned for `select("*")` or `select('*')`
- THEN zero matches are found and each query lists its columns explicitly

### Requirement: Greeting compat shim removed

The untested `_generate_greeting_card_compatibly` shim
(`bot/services/greeting_service.py:202`) MUST be removed. Its fallback branch
is dead because `generate_greeting_card` already accepts the localized kwargs
natively. Removal MUST be guarded by Strict TDD: a RED test exercising the
native-kwargs path MUST be added before the shim is deleted.

#### Scenario: Shim is absent after the change

- GIVEN `bot/services/greeting_service.py` after the change
- WHEN scanned for `_generate_greeting_card_compatibly`
- THEN zero matches are found

#### Scenario: Native kwargs path has a covering test

- GIVEN the shim is about to be removed
- WHEN the test suite is run before deletion
- THEN a test exists that exercises `generate_greeting_card` with the localized kwargs directly and passes

### Requirement: Local INFO brand bypass removed

The two local `INFO = discord.Color.from_str("#5865F2")` definitions in
`bot/cogs/ticket_admin_flow.py` and `bot/cogs/ticket_notes_flow.py` MUST be
removed and replaced by importing `bot.utils.brand.INFO`. (Mirrors the
`brand-tokens` delta; this requirement exists in `guards-contracts` because
the removal is a DRY extract, not a palette change.)

#### Scenario: No local INFO definitions in ticket cogs

- GIVEN the two ticket cog files
- WHEN scanned for `INFO = discord.Color.from_str`
- THEN zero matches are found and both import `INFO` from `bot.utils.brand`

### Requirement: time.py and timeparse.py are not merged

`bot/utils/time.py` (DB timestamp parsing) and `bot/utils/timeparse.py` (duration parsing) are DIFFERENT domains and MUST NOT be merged into a single module. This change MUST NOT introduce a merge or a re-export façade that collapses them. A code comment or docstring in each file MUST state the other file is a separate domain. Cycle 2 adds `parse_duration_strict` to `bot/utils/time.py` (a strict variant of `parse_duration`, for the `,12h` ticket timer); this does not change the separation contract — `parse_duration_strict` lives in the duration domain (`time.py`), NOT in `timeparse.py`.
(Previously: the requirement mandated separation and a docstring in each file; Cycle 2 adds a second duration function to `time.py` and must keep the separation intact.)

#### Scenario: time.py and timeparse.py remain separate

- GIVEN `bot/utils/time.py` and `bot/utils/timeparse.py`
- WHEN the change is applied
- THEN both files still exist independently, no module re-exports one as the other, and `parse_duration_strict` lives in `time.py`

#### Scenario: Separation is documented

- GIVEN `bot/utils/time.py` and `bot/utils/timeparse.py`
- WHEN their module docstrings are read
- THEN each states that the other file is a separate domain and they MUST NOT be merged

## Scope boundary

Cycle 2 (Neon) and Cycle 3 (timer, 12h, banana, RLS, voice/moderation,
ScheduledAction, has_perm) are OUT OF SCOPE. The DRY extracts target only the
duplications listed above; they do not refactor adjacent code or introduce
new abstractions beyond the shared guard, the shared embed helpers, the
explicit column lists, and the shim removal.


<!-- BEGIN DELTA: welcome-neon-timer-banana (guards-contracts) -->

## ADDED Requirements
### Requirement: Bot-side explicit columns replace select star (Cycle 2 scope)

The `select("*")` calls in the Cycle-2-touched bot DB mixins —
`bot/core/db/greeting_db.py` (e.g. `:32`) and the ticket-timer read paths in
`bot/core/db/ticket_db.py` touched by the scheduled-close loop — MUST be
replaced with explicit column lists. `select("*")` MUST NOT appear in those
mixin files after this change for the queries touched by Cycle 2. The
economy and infraction mixins (`economy_db.py`, `infraction_db.py`,
`member_db.py`, `guild_db.py`, `ticket_audit_db.py`,
`ticket_category_db.py`, `ticket_note_db.py`) are OUT OF SCOPE for Cycle 2
(to keep PR3 within the 800-line budget) and remain on `select("*")` as
deferred tech-debt for Cycle 3. This scoping matches the Cycle 1
`guards-contracts` requirement that scoped `select("*")` removal to the
dashboard actions only.

#### Scenario: No select star in Cycle-2-touched greeting queries

- GIVEN `bot/core/db/greeting_db.py` after the change
- WHEN scanned for `select("*")` or `select('*')`
- THEN the Cycle-2-touched queries (get_greeting_config, upsert read-back) list columns explicitly and the greeting read path has no `select("*")`

#### Scenario: No select star in Cycle-2-touched ticket timer queries

- GIVEN the ticket timer read path (scheduled-close candidate lookup) in `bot/core/db/ticket_db.py`
- WHEN the scheduled-close candidate query is inspected
- THEN it selects explicit columns (status, scheduledCloseAt, channelId, guildId, etc.) and does not use `select("*")`

#### Scenario: Economy/infraction mixins unchanged (deferred)

- GIVEN `economy_db.py`, `infraction_db.py`, `member_db.py`, `guild_db.py`
- WHEN scanned for `select("*")`
- THEN those files MAY still contain `select("*")` (deferred to Cycle 3, documented as tech-debt — not a Cycle 2 failure)

### Requirement: escape_markdown and AllowedMentions hygiene

Bot output that echoes user-controlled text (ticket subjects, custom field
values, 8ball questions, ban/kick reasons echoed back) MUST apply
`discord.utils.escape_markdown` to prevent formatting injection and MUST use
`AllowedMentions` to prevent unwanted pings from echoed content. Today `rg`
finds zero usages of `escape_markdown` or `AllowedMentions` in `bot/`; Cycle 2
introduces them on the moderation-reason and ticket-subject echo paths (the
paths touched by Cycle 2). This is additive defense-in-depth; it MUST NOT alter
the displayed content beyond escaping markdown and suppressing pings.

#### Scenario: Ticket subject echo escapes markdown

- GIVEN a ticket subject containing markdown (`**bold**`, `@everyone`)
- WHEN the bot echoes the subject in an embed
- THEN the markdown is escaped and `@everyone` does not ping

#### Scenario: Ban reason echo uses AllowedMentions

- GIVEN a ban reason containing a user mention string
- WHEN the bot echoes the reason in the confirmation/log embed
- THEN `AllowedMentions` suppresses the mention and no unintended ping occurs

#### Scenario: 8ball question echo escapes markdown

- GIVEN an 8ball question containing markdown
- WHEN the bot echoes the question in the ephemeral reply
- THEN the markdown is escaped
<!-- END DELTA: welcome-neon-timer-banana (guards-contracts) -->
