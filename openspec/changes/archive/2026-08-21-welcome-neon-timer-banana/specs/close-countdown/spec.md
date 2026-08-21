# Delta for Close Countdown

Cycle 2 of 3. Clarifies that the Cycle 2 scheduled-close timer loop
(`@tasks.loop(seconds=60)`, batch 50) closes tickets SILENTLY — like auto-close,
no countdown — because it is an automatic path, not a manual close. The
existing manual-close countdown (5→1 edited message) and the 48h auto-close
silence are UNCHANGED. This delta only extends the "automatic path is silent"
rule to cover the new scheduled-close loop.

## MODIFIED Requirements

### Requirement: Auto-close has no countdown

Auto-close (48h inactivity) and the Cycle 2 scheduled-close timer loop (`,12h` → 60s batch) MUST delete the channel silently without posting or editing any countdown message. Both are automatic paths: the 5→1 countdown is reserved for the manual close button flow only. A scheduled-close ticket MUST NOT post a countdown before deletion.
(Previously: the requirement named only the 48h auto-close path as silent; the scheduled-close loop did not exist.)

#### Scenario: Auto-close is silent

- GIVEN a ticket inactive for 48 hours
- WHEN the auto-close task runs
- THEN the channel is deleted without any countdown messages

#### Scenario: Scheduled-close loop is silent

- GIVEN an open ticket with `scheduledCloseAt` in the past and the scheduled-close loop running
- WHEN the loop closes the ticket
- THEN the channel is deleted silently without any 5→1 countdown messages

## Scope boundary

This delta only extends the silence rule to the scheduled-close loop. The
loop itself, the `,12h`/`,cancel` listener, and `format_remaining` are
specified in `ticket-service`; the `<2h`/`>5d` confirm in `close-confirmation`.
Cycle 3 (voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
