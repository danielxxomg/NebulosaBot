# Delta for Economy Service

## ADDED Requirements

### Requirement: Dashboard webhook notification

The dashboard `updateEconomyConfig()` Server Action MUST fire an asynchronous POST to the bot's webhook endpoint after a successful Supabase write. The webhook call MUST NOT block or fail the Supabase write.

#### Scenario: Webhook fired after economy config write

- GIVEN the dashboard writes an economy config change to Supabase
- WHEN the Supabase write succeeds
- THEN a signed POST is sent to the webhook endpoint with `{"guild_id": G}` (guild_id only; the optional `entity` field is omitted because the bot performs a full `invalidate_guild`)

#### Scenario: Webhook failure does not fail write

- GIVEN the webhook endpoint is unreachable or returns an error
- WHEN `updateEconomyConfig()` completes the Supabase write
- THEN the Server Action returns success (fire-and-forget)
