# Delta for Close Confirmation

Cycle 2 of 3. Reuses the existing `ConfirmCancelView` (30s default timeout,
`bot/views/confirmation.py:24-144`) to guard the `,12h` scheduled-close timer
when the requested duration is "too soon" (`<2h`) or "too far" (`>5d`). The
existing manual-close confirmation (Close button → ephemeral Confirm/Cancel)
is UNCHANGED. The timer confirmation is a NEW, separate use of the same view,
gated by duration thresholds, not by the close-button flow.

## ADDED Requirements

### Requirement: Timer confirmation under <2h and >5d thresholds

When a mod schedules a close with `,<duration>` in an open/claimed ticket
channel, the system MUST show an ephemeral `ConfirmCancelView` confirmation
when the duration is below 2 hours (`<2h`) or above 5 days (`>5d`). The
confirmation MUST display the requested duration, the proposed
`scheduledCloseAt`, and Confirm/Cancel buttons. Only the mod who issued the
timer MAY confirm (the view is owner-only, same contract as manual close). On
Confirm, the timer is set (the `scheduledCloseAt`/`scheduledCloseBy` write and
the pinned `<t:R>`/`<t:F>` embed). On Cancel or 30s timeout, no timer is set
and the ticket remains unchanged. Durations within `2h..5d` (inclusive) MUST
set the timer immediately without confirmation.

#### Scenario: Duration under 2h requires confirmation

- GIVEN an open ticket channel and a mod who sends `,1h`
- WHEN the parser returns 3600 (below 2h)
- THEN an ephemeral ConfirmCancelView is shown; the timer is set only on Confirm

#### Scenario: Duration over 5d requires confirmation

- GIVEN an open ticket channel and a mod who sends `,10d`
- WHEN the parser returns 864000 (above 5d)
- THEN an ephemeral ConfirmCancelView is shown; the timer is set only on Confirm

#### Scenario: Duration within 2h..5d sets timer immediately

- GIVEN an open ticket channel and a mod who sends `,12h`
- WHEN the parser returns 43200 (within 2h..5d)
- THEN the timer is set immediately with no confirmation dialog

#### Scenario: Confirm sets the timer

- GIVEN an ephemeral timer confirmation is shown for `,1h`
- WHEN the issuing mod clicks Confirm
- THEN `scheduledCloseAt`/`scheduledCloseBy` are set and the pinned `<t:R>`/`<t:F>` embed is posted

#### Scenario: Cancel or timeout leaves the ticket unchanged

- GIVEN an ephemeral timer confirmation is shown for `,1h`
- WHEN the mod clicks Cancel OR 30 seconds elapse with no interaction
- THEN no timer is set, `scheduledCloseAt`/`scheduledCloseBy` remain NULL, and the ticket remains open/claimed

#### Scenario: Only the issuing mod can confirm

- GIVEN modA issued `,1h` and sees the confirmation dialog
- WHEN modB clicks Confirm
- THEN an ephemeral message indicates only the issuing mod can confirm and no timer is set

## Scope boundary

This delta adds only the `<2h`/`>5d` timer confirmation reusing
`ConfirmCancelView`. The manual-close confirmation is UNCHANGED. The
scheduled-close columns, loop, and `,cancel` are specified in `ticket-model`
and `ticket-service`; the silent-vs-countdown distinction in `close-countdown`.
Cycle 3 (voice/moderation, ScheduledAction, has_perm) is OUT OF SCOPE.
