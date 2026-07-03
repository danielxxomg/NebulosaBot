# Delta for Greeting Configuration

## ADDED Requirements

### Requirement: Dashboard webhook notification

The dashboard `updateGreetingConfig()` Server Action MUST fire an asynchronous POST to the bot's webhook endpoint after a successful Supabase write. The webhook call MUST NOT block or fail the Supabase write.

#### Scenario: Webhook fired after greeting config write

- GIVEN the dashboard writes a greeting config change to Supabase
- WHEN the Supabase write succeeds
- THEN a signed POST is sent to the webhook endpoint with `{"guild_id": G, "entity": "greeting_config"}`

#### Scenario: Webhook failure does not fail write

- GIVEN the webhook endpoint is unreachable or returns an error
- WHEN `updateGreetingConfig()` completes the Supabase write
- THEN the Server Action returns success (fire-and-forget)
