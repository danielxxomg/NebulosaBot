# Delta for cache-sync-realtime

## ADDED Requirements

### Requirement: Realtime coverage and deferred cache scope are documented

The cache/Realtime documentation MUST state that CDC coverage is limited to `guild`, `greeting_config`, `ticket`, and `ticket_note`. Member and economy changes MUST be documented as outside the current Realtime publication/invalidation contract, with cross-instance coherence work deferred to S2. S1 MUST NOT claim immediate Realtime invalidation for those entities.

#### Scenario: Published table scope is explicit

- GIVEN the Realtime configuration and cache documentation are reviewed
- WHEN the subscribed table list is compared with the contract
- THEN it contains the four supported tables and excludes member/economy tables

#### Scenario: Member and economy changes remain a documented deferral

- GIVEN a member balance or economy configuration changes
- WHEN S1 cache behavior is evaluated
- THEN no Realtime guarantee is asserted and the S2 deferral is recorded

#### Scenario: Existing CDC behavior is preserved

- GIVEN a supported table emits INSERT, UPDATE, or DELETE
- WHEN the existing subscriber handles the event
- THEN the current guild cache invalidation behavior remains unchanged
