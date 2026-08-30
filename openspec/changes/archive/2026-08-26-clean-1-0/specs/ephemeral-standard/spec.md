# Delta for Ephemeral Standard

## MODIFIED Requirements

### Requirement: Slash-only error visibility

With the prefix surface disabled (see `bot-core`), no prefix-invocation error path exists. Application (slash) command error responses MUST be ephemeral — visible only to the invoking user. Permission-denial branches (`CheckFailure`, `MissingPermissions`) MUST produce an ephemeral localized reply through the global handler — they MUST NOT surface as unhandled errors and MUST NOT post publicly, even for commands whose normal response is permanent.

#### Scenario: Admin slash error stays ephemeral

- GIVEN an admin invokes `/config` and the command raises a handled error
- WHEN the error response is produced
- THEN the embed is ephemeral (no DM is sent, nothing is posted permanently)

#### Scenario: Prefix invocation produces no output

- GIVEN a user types `nb!ticket_panel` in #general
- WHEN the message is processed
- THEN no command executes and the bot posts no response (the prefix surface is inert)

#### Scenario: CheckFailure denial is ephemeral on a permanent command

- GIVEN a user without the required matrix grant invokes a permanent-response guarded command
- WHEN `CheckFailure` is raised
- THEN an ephemeral localized denial reply is sent and nothing is posted publicly

### Requirement: Fun commands permanent standard

Fun/economy commands (balance, daily, work, leaderboard) MUST respond permanently. Ocio fun commands `/dice`, `/8ball`, and `/banana` MUST also respond permanently — the prior ocio-ephemeral exception is REMOVED from this standard. Their cooldown-error replies remain ephemeral (error feedback).

(Previously: ocio `/banana` and `/8ball` were documented as an ephemeral exception; this delta closes it.)

#### Scenario: /balance permanent

- GIVEN a user invokes `/balance`
- WHEN the command executes
- THEN the balance embed is visible to all users in the channel

#### Scenario: Ocio fun responses are permanent

- GIVEN users invoke `/dice`, `/8ball`, or `/banana`
- WHEN each command executes successfully
- THEN each reply is permanent and visible to all users in the channel

#### Scenario: Ocio cooldown errors stay ephemeral

- GIVEN a user re-invokes an ocio command inside its cooldown window
- WHEN the cooldown handler replies
- THEN that retry-after feedback is ephemeral, not public
