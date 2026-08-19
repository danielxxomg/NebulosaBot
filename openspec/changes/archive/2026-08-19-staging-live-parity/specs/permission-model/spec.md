# Delta for Permission Model

## ADDED Requirements

### Requirement: Historical guild-scope ledger is separate from runtime truth

The 12 names formerly exposed as `GUILD_SCOPE_GAPS` MUST be renamed to `GUILD_SCOPE_GAP_HISTORY` and preserved as audit history. Reports and tests MUST expose a separate `guild_scope_runtime_closed` fact. That fact MUST equal 12 only when every listed database entry point enforces guild ownership; the historical tuple MUST NOT itself block or authorize runtime behavior.

#### Scenario: Historical rename preserves all entries

- GIVEN the ledger contains the 12 previously identified scope entries
- WHEN the S4 rename is applied
- THEN the historical name is used, all 12 entries remain, and no entry is silently deleted

#### Scenario: Runtime closure is truthful

- GIVEN all 12 entry points enforce guild ownership
- WHEN the permission/parity report is built
- THEN `guild_scope_runtime_closed` equals 12 and the historical ledger remains informational

#### Scenario: Partial enforcement does not claim closure

- GIVEN one or more listed entry points lacks an enforceable guild boundary
- WHEN the report is built
- THEN the runtime-closed value is below 12 or unresolved and acceptance cannot claim full closure

#### Scenario: Cross-guild access remains denied

- GIVEN equivalent identifiers exist in guilds A and B
- WHEN guild A invokes a listed database path for guild B's identifier
- THEN no guild B data is returned or mutated, regardless of the historical ledger name
