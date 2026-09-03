# Delta for greeting-config

## ADDED Requirements

### Requirement: Per-kind template columns via migration 030 — idempotent with COALESCE backfill

The system MUST add nullable `welcomeTemplateId` (`welcome_template_id`) and `goodbyeTemplateId` (`goodbye_template_id`) TEXT columns via `030_greeting_templates.sql` using `ADD COLUMN IF NOT EXISTS`. Migration MUST be re-runnable without raise and MUST backfill nulls from legacy `themeId` via `COALESCE`/`WHERE IS NULL`. Rollback MUST be `DROP COLUMN IF EXISTS "welcomeTemplateId","goodbyeTemplateId"`.

#### Scenario: Existing rows remain valid

- GIVEN existing row without new columns
- WHEN `030` applied
- THEN row preserved, new cols read as `NULL` or backfilled legacy value

#### Scenario: New guild defaults to null

- GIVEN bot joins guild with no row
- WHEN default `GreetingConfig` created
- THEN `welcome_template_id`/`goodbye_template_id` are `NULL` → `default` render

#### Scenario: IF NOT EXISTS guards re-run

- GIVEN `030` already applied
- WHEN applied again
- THEN no error, schema unchanged

#### Scenario: COALESCE backfills from legacy

- GIVEN row `themeId="gaming_neon"`, `welcomeTemplateId IS NULL`
- WHEN backfill runs
- THEN `welcomeTemplateId`/`goodbyeTemplateId` set to `"gaming_neon"`

### Requirement: Dual-write with legacy themeId and per-kind fallback chain

The system MUST dual-write `themeId` alongside per-kind cols for one cycle and MUST resolve via `select_template(config, kind)` chain `welcome_template_id`/`goodbye_template_id` → `theme_id` → `default`. Kinds MAY differ; unknown/null → `default`.

#### Scenario: Welcome resolves welcome_template_id

- GIVEN `welcome_template_id="sunset_wave"`, `goodbye_template_id="default"`, `theme_id="gaming_neon"`
- WHEN `select_template(config,"welcome")` called
- THEN returns `sunset_wave`

#### Scenario: Goodbye resolves independently

- GIVEN same config
- WHEN `select_template(config,"goodbye")` called
- THEN returns `default`

#### Scenario: Fallback to legacy

- GIVEN `welcome_template_id=None`, `theme_id="gaming_neon"`
- WHEN `select_template(config,"welcome")` called
- THEN returns `gaming_neon`

#### Scenario: Fallback to default when both absent or unknown

- GIVEN `welcome_template_id=None`, `theme_id=None` or `"unknown_xyz"`
- WHEN `select_template(...,"welcome")` called
- THEN returns `default`, renders without raise

#### Scenario: Dual-write persists legacy

- GIVEN `welcome_template_id="minimal_light"`
- WHEN `to_db_dict()`/`upsert` called
- THEN dict includes `"welcomeTemplateId":"minimal_light"` and `"themeId":"minimal_light"`

### Requirement: CDC invalidation contract unchanged

The system MUST reuse existing `greeting_config` Realtime CDC + `cache_key(guild_id,"greeting_config")` TTLCache to invalidate when `welcomeTemplateId`/`goodbyeTemplateId` change. No new table/publication/webhook.

#### Scenario: Cache invalidated on welcome template update

- GIVEN cached config for G
- WHEN `welcomeTemplateId` updated
- THEN `cache_key(G,"greeting_config")` invalidated via Realtime

#### Scenario: Cache invalidated on goodbye template update

- GIVEN cached config for G
- WHEN `goodbyeTemplateId` updated
- THEN guild G cache invalidated

#### Scenario: Realtime covers new columns

- GIVEN Realtime subscribed to `greeting_config`
- WHEN `welcomeTemplateId`/`goodbyeTemplateId` change emitted
- THEN bot invalidates as for `themeId`

## MODIFIED Requirements

### Requirement: Greeting columns

The system MUST store `welcome_channel_id`, `goodbye_channel_id`, `welcome_message_template`, `goodbye_message_template`, `welcome_card_enabled`/`goodbye_card_enabled`, optional nullable `onboarding_channel_id`, optional nullable `updatedAt` (timestamptz), optional nullable `theme_id` (retained for dual-write, default null → `default`), and optional nullable `welcome_template_id` (default null → `default`) and `goodbye_template_id` (default null → `default`) in the guild greeting record.
(Previously: stored channels/templates/toggles/onboarding/updatedAt plus single shared theme_id; no per-kind template fields.)

#### Scenario: Default values for new guild

- GIVEN bot joins guild with no row
- WHEN default config created
- THEN channels/onboarding null, toggles false, `updatedAt`/`theme_id`/`welcome_template_id`/`goodbye_template_id` null → default

#### Scenario: Onboarding round-trips

- GIVEN config `onboarding_channel_id=C`
- WHEN saved and re-read
- THEN `onboardingChannelId` preserved unchanged

#### Scenario: updatedAt round-trips

- GIVEN `updatedAt=T`
- WHEN saved and re-read
- THEN `updatedAt` equals T

#### Scenario: theme_id round-trips

- GIVEN `theme_id="gaming_neon"`
- WHEN saved and re-read
- THEN `themeId` equals `"gaming_neon"`

#### Scenario: welcome_template_id round-trips

- GIVEN `welcome_template_id="sunset_wave"`
- WHEN saved and re-read
- THEN `welcomeTemplateId` equals `"sunset_wave"`

#### Scenario: goodbye_template_id round-trips

- GIVEN `goodbye_template_id="minimal_light"`
- WHEN saved and re-read
- THEN `goodbyeTemplateId` equals `"minimal_light"`

## Scope boundary

Dashboard catalogue deferred; bot tolerates unknown→default. `rank_renderer.py` untouched; text/CTA untouched.
