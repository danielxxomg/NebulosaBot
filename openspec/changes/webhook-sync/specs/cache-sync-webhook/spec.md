# Cache Sync Webhook Specification

## Purpose

POST /webhook/sync endpoint for dashboard-triggered cache invalidation via HMAC-SHA256 signed payloads.

## Requirements

### Requirement: HMAC signature verification

The system MUST verify each request carries a valid HMAC-SHA256 signature over the raw body using `WEBHOOK_SECRET`. Constant-time comparison MUST be used.

#### Scenario: Valid signature accepted

- GIVEN the dashboard signs a payload with the correct `WEBHOOK_SECRET`
- WHEN `POST /webhook/sync` is received with the signature header
- THEN the response status is 200 and `invalidate_guild(guild_id)` is called

#### Scenario: Missing signature rejected

- GIVEN a request arrives with no signature header
- WHEN the webhook handler receives it
- THEN the response status is 401 and no invalidation occurs

#### Scenario: Invalid signature rejected

- GIVEN a request signed with a wrong or tampered secret
- WHEN the webhook handler receives it
- THEN the response status is 401 and no invalidation occurs

### Requirement: Payload validation

The system MUST parse the request body as JSON and require a `guild_id` field. `guild_id` is a STRING to match the bot's universal `str` guild_id convention (DB schema stores guild ids as TEXT, cache keys are `{guild_id}:{entity}`, services take `guild_id: str`); an INTEGER `guild_id` is also accepted and coerced to `str`. JSON booleans MUST be rejected (`bool` is an `int` subclass but `true`/`false` are not valid guild ids). The optional `entity` field MAY be present but SHALL NOT alter invalidation behavior (full guild invalidation).

#### Scenario: Valid payload processed

- GIVEN a signed request body `{"guild_id": "12345"}`
- WHEN the payload is parsed
- THEN `invalidate_guild("12345")` is called with the guild id as a string

#### Scenario: Malformed payload rejected

- GIVEN a signed request with malformed JSON body
- WHEN the payload parser fails
- THEN the response status is 400 and no invalidation occurs

#### Scenario: Missing guild_id rejected

- GIVEN a signed request body `{"entity": "guild_config"}`
- WHEN the payload is validated
- THEN the response status is 400 and no invalidation occurs

### Requirement: Idempotent invalidation

The system MUST handle duplicate deliveries safely. Repeated invalidation of the same `guild_id` SHALL be idempotent — `invalidate_guild()` is called each time without side effects.

#### Scenario: Duplicate delivery safe

- GIVEN a valid signed payload for guild G has already been processed
- WHEN the same payload is delivered again (replay)
- THEN the response status is 200 and `invalidate_guild(G)` is called again without error

#### Scenario: Unknown guild_id accepted

- GIVEN a valid signed payload for a guild_id that does not exist in cache
- WHEN the webhook handler processes it
- THEN the response status is 200 (idempotent no-op)

### Requirement: Cache invalidation effect

The system MUST evict the full guild cache entry when a valid webhook request is processed. Subsequent reads for that guild MUST repopulate from Supabase.

#### Scenario: Cache repopulated after invalidation

- GIVEN guild G's config is cached
- WHEN a valid webhook invalidates guild G
- THEN the next read for guild G fetches from the database and repopulates the cache

### Requirement: Server lifecycle

The system MUST start the aiohttp webhook server on the configured port after the bot connects. If the port is unavailable, the system MUST log an error and continue without the webhook endpoint (degraded mode, stale cache until TTL).

#### Scenario: Server starts on connect

- GIVEN `WEBHOOK_PORT` is configured
- WHEN the bot connects to Discord
- THEN the webhook server begins listening on that port

#### Scenario: Port conflict degraded mode

- GIVEN `WEBHOOK_PORT` is already in use
- WHEN the webhook server fails to bind
- THEN an error is logged and the bot continues operating without webhook support

### Requirement: Environment configuration

The system MUST read `WEBHOOK_SECRET` and `WEBHOOK_PORT` from environment variables. If `WEBHOOK_PORT` is absent, the system SHALL use a default port. If `WEBHOOK_SECRET` is absent, the webhook server MUST NOT start (cannot verify signatures).

#### Scenario: Defaults when port missing

- GIVEN `WEBHOOK_SECRET` is set but `WEBHOOK_PORT` is not
- WHEN the bot starts
- THEN the webhook server starts on the default port

#### Scenario: No server without secret

- GIVEN `WEBHOOK_SECRET` is not set
- WHEN the bot starts
- THEN the webhook server does not start and a warning is logged
