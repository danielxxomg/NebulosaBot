# Delta for setup-panel

## ADDED Requirements

### Requirement: Per-kind template selection via StringSelect (both welcome and goodbye)

The system MUST provide a `StringSelect` in `WelcomeSetupModule.components()` (`bot/views/setup_modules/welcome.py`) with `custom_id="setup:welcome:select_template"` and in `GoodbyeSetupModule.components()` (`bot/views/setup_modules/goodbye.py`) with `custom_id="setup:goodbye:select_template"`. Each picker MUST offer exactly four options — `default`, `gaming_neon`, `sunset_wave`, `minimal_light` — whose labels and descriptions are resolved via `t()` (no hardcoded literals). Selection change MUST persist via the existing `greeting.manage` gated path: `WelcomeSetupModule.set_welcome_template_id` / `GoodbyeSetupModule.set_goodbye_template_id` → `GreetingService.save_config` dual-write → `cache.invalidate` + Realtime CDC. The pickers MUST use static `custom_id`s rerouted after restart via `setup_panel` view registration. The permission gate MUST remain `greeting.manage`; no new matrix key SHALL be created.

#### Scenario: Welcome picker shows four template options

- GIVEN `WelcomeSetupModule.components(guild_id)` is called
- WHEN the returned items are inspected
- THEN a `StringSelect` with `custom_id="setup:welcome:select_template"` exists with four options `default`, `gaming_neon`, `sunset_wave`, `minimal_light` and all labels resolve via `t()`

#### Scenario: Goodbye picker shows four template options

- GIVEN `GoodbyeSetupModule.components(guild_id)` is called
- WHEN the returned items are inspected
- THEN a `StringSelect` with `custom_id="setup:goodbye:select_template"` exists with the same four options and all labels resolve via `t()`

#### Scenario: Selecting welcome template persists per-kind column

- GIVEN an admin with `greeting.manage` selects `sunset_wave` in the welcome picker
- WHEN the interaction is handled
- THEN `welcome_template_id="sunset_wave"` is persisted via `save_config` dual-write (`welcomeTemplateId` and `themeId` set), `goodbye_template_id` unchanged, and `render_async` reflects the new label

#### Scenario: Selecting goodbye template persists independently

- GIVEN the same guild with `welcome_template_id="sunset_wave"`
- WHEN the admin selects `minimal_light` in the goodbye picker
- THEN `goodbye_template_id="minimal_light"` is persisted, `welcome_template_id` remains `"sunset_wave"` (kind-scoped, may differ)

#### Scenario: Missing greeting.manage is denied ephemerally

- GIVEN a user without `greeting.manage` triggers `setup:welcome:select_template` or `setup:goodbye:select_template`
- WHEN the handler checks permissions
- THEN an ephemeral denial is sent via `t(guild_id, "setup.module.*.error_*")` and no config is mutated

#### Scenario: render_async shows template label for both modules

- GIVEN a guild with `welcome_template_id="gaming_neon"` and `goodbye_template_id="minimal_light"`
- WHEN `WelcomeSetupModule.render_async` and `GoodbyeSetupModule.render_async` re-render after save/refresh
- THEN each embed description includes the resolved template label via `t()` (e.g. `setup.module.welcome.template_label` + `templates.greeting.<id>.label`) and refresh re-reads from service/cache

### Requirement: Preview forwards resolved per-kind template via existing channel-delivery flow

The system MUST forward the resolved per-kind template from `select_template(config, kind)` into the existing `_handle_test` preview path for both welcome and goodbye. Preview MUST resolve the renderer via `GreetingService.resolve_renderer()`, render the REAL card via `asyncio.to_thread(render_fn, ..., template_id=resolved, theme_id=resolved)` (so `card-image-only` scope and non-blocking guarantee hold), and deliver the PNG + message content to the configured `welcome_channel_id`/`goodbye_channel_id` via `guild.get_channel`. When the channel is null or inaccessible, the flow MUST reply with an ephemeral `preview_no_channel` / `preview_error` embed via `t()` and MUST NOT mutate config. The flow MUST remain `greetings.py` untouched.

#### Scenario: Welcome preview delivers real card with resolved template

- GIVEN `welcome_template_id="sunset_wave"` and a configured welcome channel
- WHEN the admin presses `setup:welcome:test`
- THEN a real PNG rendered with `template_id="sunset_wave"` (via `asyncio.to_thread`) is sent to the welcome channel and an ephemeral `preview_success` is returned

#### Scenario: Goodbye preview delivers real card with resolved template

- GIVEN `goodbye_template_id="minimal_light"` and a configured goodbye channel
- WHEN the admin presses `setup:goodbye:test`
- THEN a real PNG rendered with `template_id="minimal_light"` is sent to the goodbye channel via the same `_handle_test` channel-delivery path

#### Scenario: Unknown template preview falls back to default

- GIVEN `welcome_template_id="unknown_xyz"` (unknown value stored)
- WHEN welcome preview is triggered
- THEN `select_template` resolves `"default"` and the `default` card renders with no raise

#### Scenario: Missing channel preview is ephemeral and safe

- GIVEN no welcome channel is configured
- WHEN `setup:welcome:test` is pressed
- THEN an ephemeral `setup.module.welcome.preview_no_channel_*` embed is sent and no channel message is delivered

## Scope boundary

Dashboard template catalogue and ephemeral preview remain out of scope this cycle (bot-only). `bot/cogs/greetings.py` dispatch is reused unchanged via `_handle_test` channel-delivery; no new cog is introduced. `rank_renderer.py` untouched.
