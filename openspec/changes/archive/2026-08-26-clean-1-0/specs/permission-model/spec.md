# Delta for Permission Model

## ADDED Requirements

### Requirement: Setup surface reuses existing matrix keys — no new key

The `/setup` panel and its modules MUST NOT introduce any new permission-matrix key. The `PERMISSIONS` frozenset MUST remain exactly the seven existing permissions (`moderation.warn`, `moderation.mute`, `moderation.kick`, `moderation.ban`, `tickets.manage`, `economy.manage`, `greeting.manage`). Panel invocation visibility uses `default_permissions(administrator=True)` (relaxable by server admins via Integrations) and administrators pass implicitly; module-level mutations authorize through the EXISTING keys via the standard `can()`/`can_check()` path: `tickets.manage` gates Tickets-module actions, `greeting.manage` gates Welcome/Goodbye-module actions.

(Decided contract: a previously drafted "new setup matrix key" is explicitly REJECTED.)

#### Scenario: Matrix key set is unchanged

- GIVEN `PERMISSIONS` after this change
- WHEN its contents are inspected
- THEN it contains exactly the seven pre-existing keys and no setup-panel key

#### Scenario: Administrator opens panel implicitly

- GIVEN a user with the Administrator permission
- WHEN they invoke `/setup`
- THEN the panel opens without consulting the matrix (admin implicit pass)

#### Scenario: Tickets module gated by tickets.manage

- GIVEN a relaxed-integration non-admin whose role holds `tickets.manage`
- WHEN they perform a Tickets-module mutation
- THEN it succeeds via the existing matrix grant path

#### Scenario: Welcome module denied without greeting.manage

- GIVEN a relaxed-integration non-admin whose role lacks `greeting.manage`
- WHEN they attempt a Welcome-module save
- THEN the action is denied ephemerally and nothing persists
