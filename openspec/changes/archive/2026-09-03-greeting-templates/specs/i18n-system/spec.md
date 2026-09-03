# Delta for i18n-system

## ADDED Requirements

### Requirement: Greeting template locale keys — 16 t() keys in both es.json and en.json

The system MUST add sixteen `t()` keys in both `bot/locales/es.json` and `bot/locales/en.json` covering picker chrome and the code-owned catalogue. Every template label/description visible in the `/setup` Welcome/Goodbye modules MUST resolve via `t(guild_id, "<key>")`; no hardcoded English/Spanish literals SHALL appear in `welcome.py`, `goodbye.py`, `greeting_renderer.py`, or `greeting_service.py` for template chrome. The renderer MUST remain `t()`-free; translated template labels are resolved in the view/service layer and the renderer receives only `template_id`. All sixteen keys MUST exist in both locales or `tests/test_i18n_key_coverage.py` MUST fail with a consolidated missing-key report. Existing keys and JSON structure MUST remain untouched.

The sixteen keys are exactly:

- `setup.module.welcome.template_label`
- `setup.module.welcome.template_placeholder`
- `setup.module.welcome.template_select_title`
- `setup.module.welcome.template_select_description`
- `setup.module.goodbye.template_label`
- `setup.module.goodbye.template_placeholder`
- `setup.module.goodbye.template_select_title`
- `setup.module.goodbye.template_select_description`
- `templates.greeting.default.label`
- `templates.greeting.default.description`
- `templates.greeting.gaming_neon.label`
- `templates.greeting.gaming_neon.description`
- `templates.greeting.sunset_wave.label`
- `templates.greeting.sunset_wave.description`
- `templates.greeting.minimal_light.label`
- `templates.greeting.minimal_light.description`

#### Scenario: All sixteen keys resolvable in both locales

- GIVEN `es.json` and `en.json` after the change
- WHEN `t(guild_id, "setup.module.welcome.template_label")`, `t(guild_id, "templates.greeting.sunset_wave.label")`, and the other fourteen keys are called for a guild in each language
- THEN non-empty localized strings are returned from both locales with no raw key leakage

#### Scenario: Missing key fails coverage with callsite

- GIVEN a literal `t(guild_id, "templates.greeting.sunset_wave.label")` call exists in `bot/` and the key is absent from `en.json`
- WHEN `tests/test_i18n_key_coverage.py` runs
- THEN it fails listing the missing key with its originating `file:line`

#### Scenario: Template picker labels resolve via t() not hardcoded

- GIVEN the Welcome/Goodbye `StringSelect` pickers after the change
- WHEN their option labels/descriptions are inspected and `bot/views/setup_modules/welcome.py` + `goodbye.py` are scanned for hardcoded template literals
- THEN every option label/description comes from `t(guild_id, "templates.greeting.<id>.label")` / `...description` and zero hardcoded literals are found

#### Scenario: Renderer stays t()-free

- GIVEN `bot/services/greeting_renderer.py` after the change
- WHEN its source is scanned for `t(`
- THEN zero matches are found; template names are supplied as `template_id` and only the view/service layer calls `t()`

#### Scenario: Both locales must agree

- GIVEN `templates.greeting.minimal_light.label` exists in `es.json` but not `en.json`
- WHEN the coverage test runs
- THEN it fails (both locales are required for every literal key)

#### Scenario: Fallback chain still applies to template keys

- GIVEN a guild configured with language `en` and `templates.greeting.sunset_wave.description` exists only in `es.json`
- WHEN `t(guild_id, "templates.greeting.sunset_wave.description")` is called
- THEN the Spanish value is returned before the raw key

## Scope boundary

No dashboard i18n catalogue, DB template table, or ephemeral preview chrome is introduced. `rank_renderer.py` keys untouched. Only the sixteen keys above are added; no existing translations are modified.
