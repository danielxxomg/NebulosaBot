# Delta for Ticket Service

## MODIFIED Requirements

### Requirement: Ticket close

The system MUST close a ticket, generate a transcript, and delete the channel. Manual close MUST use a countdown (5→1 edited message) before channel deletion. Auto-close MUST delete silently. `close_ticket()` MUST accept an optional `close_reason: str | None` parameter and persist it to the Ticket row when provided; when the channel is already missing (zombie repair path), `close_ticket()` MUST skip channel deletion and transcript generation, set `status="closed"`, and persist `close_reason` if supplied. When `close_reason` is `None`, the field MUST NOT be overwritten. The conditional close MUST be idempotent: closing an already-closed ticket MUST raise `ValueError` and perform no mutation.

(Previously: close handled manual countdown and silent auto-close but lacked a conditional `close_reason` transition and a channel-missing zombie path; auto-close silently skipped missing channels without recording a repair)

#### Scenario: Close with transcript

- GIVEN an open ticket with messages
- WHEN the close action is triggered
- THEN a transcript is generated, uploaded to the log channel, the Ticket row status becomes `closed`, and the channel is deleted after countdown

#### Scenario: Close unclaimed ticket

- GIVEN an unclaimed open ticket
- WHEN close is triggered
- THEN the ticket is closed normally and `claimedBy` remains null

#### Scenario: Close records close_reason when provided

- GIVEN an open ticket and `close_reason="channel deleted externally"`
- WHEN `close_ticket(ticket_id, close_reason="channel deleted externally")` is called
- THEN the Ticket row persists `closeReason="channel deleted externally"` and status becomes `closed`

#### Scenario: Close without close_reason leaves field unchanged

- GIVEN an open ticket whose `closeReason` is null
- WHEN `close_ticket(ticket_id)` is called
- THEN status becomes `closed` and `closeReason` remains null

#### Scenario: Close zombie ticket skips channel and transcript

- GIVEN an open ticket whose Discord channel no longer exists
- WHEN `close_ticket(ticket_id, close_reason="zombie:channel_missing")` is called
- THEN `status` becomes `closed`, `closeReason` is persisted, and no channel deletion or transcript generation is attempted

#### Scenario: Re-closing a closed ticket is rejected

- GIVEN a ticket with `status="closed"`
- WHEN `close_ticket(ticket_id)` is called
- THEN `ValueError` is raised and no mutation occurs

## ADDED Requirements

### Requirement: Authoritative channel-delete repair

On the authoritative `on_guild_channel_delete` event, the system MUST perform a conditional active-ticket lookup keyed by the deleted channel's `guild_id` and `channel_id`. An active ticket is one with `status` `open` or `claimed`. When an active ticket maps to the deleted channel, the system MUST repair it via `close_ticket` with `close_reason="zombie:channel_deleted"`, producing a `RepairResult`. When no active ticket maps to the deleted channel, the system MUST do nothing (no provenance). Repair via this path is permitted only after the G.2 deployment/migration preflight gate (see database-layer delta) returns `resolved`. Until then, the event handler MUST log the detection and skip repair.

#### Scenario: Authoritative event repairs active zombie

- GIVEN the G.2 gate is `resolved` and an open ticket maps to channel `c1` in guild `g1`
- WHEN `on_guild_channel_delete` fires for channel `c1`
- THEN the ticket is conditionally closed with `closeReason="zombie:channel_deleted"` and a `RepairResult(action="close", outcome="repaired")` is produced

#### Scenario: No active ticket means no-op

- GIVEN the G.2 gate is `resolved` and no open/claimed ticket maps to channel `c2`
- WHEN `on_guild_channel_delete` fires for channel `c2`
- THEN no `close_ticket` call is made and no ticket mutation occurs

#### Scenario: Gate unresolved blocks automatic repair

- GIVEN the G.2 gate is `gate_unresolved` and an open ticket maps to deleted channel `c1`
- WHEN `on_guild_channel_delete` fires for channel `c1`
- THEN the handler logs detection of the zombie but does not call `close_ticket`

#### Scenario: Duplicate close race resolves to no-op

- GIVEN the G.2 gate is `resolved` and two `on_guild_channel_delete` events fire for the same channel concurrently
- WHEN both attempt to close the same active ticket
- THEN exactly one `RepairResult(action="close", outcome="repaired")` is produced and the second attempt produces `RepairResult(action="no_op", outcome="already_closed")`

### Requirement: Evidence-gated reconciliation sweep

The system MUST support startup and hourly reconciliation sweeps that detect and report zombie tickets. Sweeps MUST be evidence-gated: they MUST collect `IntegrityEvidence` per candidate and act only on `corroborated=True` evidence. Repair mutation within a sweep is permitted ONLY when the G.2 gate is `resolved`. When the gate is unresolved, the sweep MUST produce a dry-run report only — no mutations. Sweeps MUST be bounded (a maximum batch size per run) and rate-limit safe: cooperation with Discord API limits, backoff on transient errors, and no unbounded iteration over all guild tickets. A sweep that cannot complete verification for a candidate MUST mark that candidate `outcome="skipped"` rather than mutating.

#### Scenario: Dry-run report when gate unresolved

- GIVEN the G.2 gate is `gate_unresolved` and guild `g1` has two open tickets whose channels are missing
- WHEN the hourly sweep runs
- THEN a dry-run report lists both candidates with `corroborated=True` and no ticket mutation occurs

#### Scenario: Sweep repairs corroborated zombies when gate resolved

- GIVEN the G.2 gate is `resolved` and guild `g1` has one corroborated zombie ticket
- WHEN the hourly sweep runs
- THEN the sweep closes that ticket with `closeReason="zombie:sweep"` and emits `RepairResult(action="close", outcome="repaired")`

#### Scenario: Bounded batch size enforced

- GIVEN guild `g1` has 250 zombie candidates and the batch size is 50
- WHEN the sweep runs
- THEN at most 50 candidates are processed this run and the remainder are left for the next run

#### Scenario: Rate-limit safe backoff

- GIVEN the sweep is running and Discord returns a 429 rate-limit error
- WHEN the error is caught
- THEN the sweep backs off, marks the current candidate `outcome="skipped"`, and proceeds without exceeding Discord rate limits

#### Scenario: Missing evidence means no mutation

- GIVEN a candidate ticket whose channel-existence check could not complete (transient error)
- WHEN the sweep evaluates it
- THEN the candidate is marked `outcome="skipped"` and no mutation occurs

### Requirement: Manual repair fallback

The system MUST provide a manual repair entry point (command/service call) allowing a moderator to trigger repair for a specific ticket or guild without depending on the automatic gate. Manual repair MUST still collect `IntegrityEvidence` and act only on `corroborated=True`, preserving false-positive safety. Manual repair MUST write an audit row with `actorId` set to the triggering mod and `action="manual_repair"`. Manual repair is NOT subject to the G.2 automatic-activation gate, but MUST respect idempotency and bounds.

#### Scenario: Mod repairs a specific zombie manually

- GIVEN mod `userM` triggers manual repair for ticket `t9` which is a corroborated zombie
- WHEN manual repair runs
- THEN the ticket is closed with `closeReason="zombie:manual_repair"`, a `RepairResult(action="close")` is produced, and an audit row records `actorId=userM`

#### Scenario: Manual repair on non-zombie is no-op

- GIVEN mod `userM` triggers manual repair for ticket `t10` whose channel still exists
- WHEN manual repair runs
- THEN `RepairResult(action="no_op", outcome="skipped")` is produced and no mutation occurs

#### Scenario: Manual repair is idempotent

- GIVEN ticket `t9` was already repaired in the same window
- WHEN manual repair is triggered again for `t9`
- THEN `RepairResult(action="no_op", outcome="already_closed")` is produced and no mutation occurs

### Requirement: Repair idempotency, bounds, and auditability

Every repair — automatic, sweep, or manual — MUST be idempotent: applying the same repair twice MUST NOT produce two close mutations. Repairs MUST be bounded: each run processes a finite batch and backs off on rate limits. Every repair attempt MUST emit a `RepairResult` and a `ticket_audit` row with `action`, `actorId` (system for automatic/sweep, mod for manual), and `outcome`. Audit rows for repair are best-effort: a failure to write the audit row MUST NOT block the documented repair mutation but MUST be logged at WARNING level. Re-running repair after `already_closed` MUST be a deterministic no-op.

#### Scenario: Idempotent re-run after repair

- GIVEN ticket `t1` was repaired and closed
- WHEN repair is triggered again for `t1`
- THEN the second run produces `RepairResult(action="no_op", outcome="already_closed")` and writes no second close mutation

#### Scenario: Audit row written on automatic repair

- GIVEN an automatic or sweep repair closes ticket `t1`
- WHEN the repair completes
- THEN a `ticket_audit` row with `action="repair"`, `actorId="system"`, and `outcome="repaired"` is written

#### Scenario: Audit row written on manual repair

- GIVEN mod `userM` manually repairs ticket `t1`
- WHEN the manual repair completes
- THEN a `ticket_audit` row with `action="manual_repair"`, `actorId="userM"`, and `outcome="repaired"` is written

#### Scenario: Audit failure does not block repair

- GIVEN repair closes ticket `t1` but the audit insert raises
- WHEN the audit insert is caught
- THEN the close mutation persists and a WARNING log is emitted

#### Scenario: Bounded run processes finite batch

- GIVEN a sweep with batch size 50 and 120 candidates
- WHEN the run completes
- THEN exactly 50 or fewer candidates are mutated and the run terminates without unbounded iteration

### Requirement: False-positive safe channel verification

Before any repair mutation, the system MUST verify corroborating evidence that the channel truly does not exist. The channel-existence check MUST tolerate transient Discord errors (network, 5xx, 429) by treating them as `channel_exists=unknown` and skipping that candidate rather than mutating. The system MUST NOT close a ticket based solely on a single transient Discord error. Corroboration requires a DB-backed active-ticket mapping AND a channel-existence check; absence of either means no mutation.

#### Scenario: Transient Discord error skips candidate

- GIVEN an active ticket `t2` and the channel-existence check raises a transient `discord.HTTPException`
- WHEN repair evaluates `t2`
- THEN `RepairResult(action="no_op", outcome="skipped")` is produced and no mutation occurs

#### Scenario: Rate-limit error treated as skip

- GIVEN the channel-existence check returns a 429 response
- WHEN repair evaluates the candidate
- THEN the candidate is skipped and no mutation occurs

#### Scenario: DB mapping but no channel check means no mutation

- GIVEN an active ticket `t3` whose channel-existence check never ran
- WHEN repair evaluates `t3`
- THEN no close mutation occurs and `Outcome="skipped"` is recorded

### Requirement: Rollback and no-op behavior

When the repair slice is disabled (gate unresolved or feature flag off), the system MUST revert to prior close and channel-delete behavior and MUST NOT rely on migration 015 until parity returns. Existing reports MUST be retained, tickets MUST be left untouched, and the prior `on_guild_channel_delete` audit-logging behavior (deletion only logged) MUST continue. A no-op repair run MUST return without side effects and without claiming completion.

#### Scenario: Disabled slice leaves tickets untouched

- GIVEN the repair gate is disabled and guild `g1` has corroborated zombies
- WHEN the sweep would run
- THEN no ticket mutation occurs and prior close/channel-delete behavior is preserved

#### Scenario: Audit logging of channel delete continues

- GIVEN the repair slice is disabled and a channel is deleted
- WHEN `on_guild_channel_delete` fires
- THEN the prior audit-logging behavior (deletion logged) continues unchanged

#### Scenario: No-op run returns without side effects

- GIVEN a sweep finds no corroborated zombies
- WHEN the run completes
- THEN no audit rows for repair are written and no `RepairResult(action="close")` is emitted
