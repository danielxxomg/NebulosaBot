# Close Countdown Specification

## Purpose

Visual countdown (5→1) edited in a single channel message before ticket channel deletion on manual close. Auto-close remains silent.

## Requirements

### Requirement: Countdown message on manual close

After close confirmation, the system MUST send ONE message to the ticket channel and edit it counting down from 5 to 1 (one edit per second), then delete the channel.

#### Scenario: Countdown displayed and channel deleted

- GIVEN a confirmed manual ticket close
- WHEN the close flow executes
- THEN a single message is posted in the channel with content "5"
- AND the message is edited to "4" after 1 second, "3" after 2 seconds, etc.
- AND after the message shows "1" and 1 second elapses, the channel is deleted

#### Scenario: Countdown is one message, not five

- GIVEN a confirmed manual ticket close
- WHEN the countdown runs
- THEN exactly ONE message is created and edited multiple times (not five separate messages)

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
