# Delta for Guards and Contracts

Cycle 2 of 3. Extends the Cycle 1 DRY extracts to the bot side: replaces
`select("*")` with explicit column lists in the Cycle-2-touched DB mixins
(greeting, ticket) — economy/infraction are deferred to Cycle 3 — and
introduces `escape_markdown` + `AllowedMentions` hygiene in bot output to
prevent mention/ping injection. The existing `time.py`/`timeparse.py`
DO-NOT-MERGE contract is REAFFIRMED (Cycle 2 adds `parse_duration_strict` to
`time.py`; the two modules MUST stay separate).

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

## MODIFIED Requirements

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

This delta scopes bot-side `select("*")` removal to the Cycle-2-touched mixins
(greeting, ticket timer) and introduces `escape_markdown`/`AllowedMentions`
on the Cycle-2 echo paths. Economy/infraction `select("*")` and full FK/RLS
policy authoring are deferred to Cycle 3. Cycle 3 (voice/moderation,
ScheduledAction, has_perm) is OUT OF SCOPE.
