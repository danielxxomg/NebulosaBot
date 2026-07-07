# Delta for Ticket Views

## MODIFIED Requirements

### Requirement: Ticket actions view

The system MUST provide a per-ticket action view with close and claim buttons. Claim button MUST be gated by `@is_mod()` (solo mod). Close button MUST be gated by author OR mod. Non-eligible users clicking a gated button SHALL receive an ephemeral rejection message.

(Previously: both buttons were ungated — any user could trigger claim or close)

#### Scenario: Action view render

- GIVEN a newly created ticket channel
- WHEN the ticket is opened
- THEN an embed with close and claim buttons is sent in the channel

#### Scenario: Mod clicks claim

- GIVEN an open ticket with the action view
- WHEN a mod clicks claim
- THEN the ticket claim flow is triggered

#### Scenario: Non-mod clicks claim rejected

- GIVEN an open ticket with the action view
- WHEN a non-mod user clicks claim
- THEN an ephemeral rejection message is sent

#### Scenario: Author clicks close

- GIVEN a ticket authored by userA
- WHEN userA clicks close
- THEN the ticket close flow is triggered

#### Scenario: Mod clicks close on another's ticket

- GIVEN a ticket authored by userA
- WHEN a mod (not userA) clicks close
- THEN the ticket close flow is triggered

#### Scenario: Non-author non-mod clicks close rejected

- GIVEN a ticket authored by userA
- WHEN userB (not author, not mod) clicks close
- THEN an ephemeral rejection message is sent

#### Scenario: Close from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks close
- THEN the ticket close flow is triggered

#### Scenario: Claim from action view

- GIVEN an open ticket channel with the action view
- WHEN a staff member clicks claim
- THEN the ticket claim flow is triggered

### Requirement: Reopen command accepts ticket-id

The `/reopen` command MUST accept an optional ticket-id argument (e.g. `/reopen ticket:#<number>` or `/reopen <uuid>`) so it can be invoked from any channel — the original ticket channel is deleted on close, making the current channel-scoped lookup unusable for closed tickets. When the ticket-id argument is provided, the command resolves the ticket by id (not by current channel). When omitted, the current behavior (resolve by channel) is preserved for the 5-second window between `status=closed` and `channel.delete()`.

(Previously: `/reopen` resolved the ticket by `ctx.channel.id` only — broken for any closed ticket whose channel was deleted, which is all of them after the 5-second close window)

#### Scenario: Reopen by ticket-id from any channel

- GIVEN a closed ticket #3 whose channel was deleted
- WHEN a mod runs `/reopen ticket:#0003` from any channel
- THEN the bot resolves ticket #3 by id and creates a new channel

#### Scenario: Reopen by channel (legacy window)

- GIVEN a ticket just closed (status=closed, channel still exists in the 5s window)
- WHEN a mod runs `/reopen` (no arg) in that channel
- THEN the bot resolves the ticket by current channel and creates a new channel

#### Scenario: Reopen non-closed ticket rejected

- GIVEN ticket #3 has status `open`
- WHEN a mod runs `/reopen ticket:#0003`
- THEN the operation is rejected (status-guard: reopen only if status==closed)
