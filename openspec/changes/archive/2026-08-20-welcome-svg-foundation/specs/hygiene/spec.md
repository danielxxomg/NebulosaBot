# Hygiene Specification

## Purpose

Cycle 1 hygiene pass: keep versioning, config, tooling, environment docs, CI
pinning, migration identity, and timestamp tracking consistent with the actual
project state. Low-risk, no behavior change beyond the additive `updatedAt`.

## Requirements

### Requirement: Version tracks actual release

`pyproject.toml` `version` MUST reflect the current release state
(`0.8.0`), not the stale `0.1.0`. Drift between the declared version and the
git/release state MUST NOT persist after this change.

#### Scenario: pyproject version matches release

- GIVEN `pyproject.toml` line 2 and the git state `v0.8.0-qa-modernization`
- WHEN the version field is read
- THEN it is `0.8.0`

### Requirement: gitignore covers generated tool caches

`.gitignore` MUST ignore the generated caches the project actually produces:
`.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`, and `**/.next/` (in addition to
the existing `.pytest_cache/`).

#### Scenario: Four new patterns present

- GIVEN `.gitignore`
- WHEN scanned for the four patterns
- THEN `.ty_cache/`, `.hypothesis/`, `*.tsbuildinfo`, and `**/.next/` are all present

### Requirement: openspec config matches tooling and thresholds

`openspec/config.yaml` MUST declare `type_checker: ty` (not `mypy`),
`coverage_threshold: 0.75` (not `0.70`), `review_budget_lines: 800` (not
`400`), and a non-stale test count consistent with the actual suite size.

#### Scenario: ty is the declared type checker

- GIVEN `openspec/config.yaml`
- WHEN `quality.type_checker` is read
- THEN it is `ty`

#### Scenario: coverage threshold is 0.75

- GIVEN `openspec/config.yaml`
- WHEN `verify.coverage_threshold` is read
- THEN it is `0.75`

#### Scenario: review budget is 800

- GIVEN `openspec/config.yaml`
- WHEN `session.review_budget_lines` is read
- THEN it is `800`

### Requirement: README exists

A `README` MUST exist at the repo root documenting what NebulosaBot is, how to
run it, and the architecture in brief. It MUST NOT be absent.

#### Scenario: README file present

- GIVEN the repo root
- WHEN `README` (or `README.md`) is checked
- THEN it exists and is non-empty

### Requirement: env example documents all bot vars

`.env.example` MUST document the Discord, Supabase, and feature environment
variables the bot actually reads, not only the three legacy vars
(`DISCORD_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`).

#### Scenario: env example covers feature vars

- GIVEN `.env.example`
- WHEN inspected
- THEN it lists the Discord, Supabase, and feature variables the bot reads, with comments

### Requirement: CI actions are SHA-pinned

`.github/workflows/code-quality.yml` MUST pin every external action and
third-party tool (e.g. `jscpd`, `vulture`) by SHA, matching the existing
`actions/checkout@11bd71901` pinning. Unpinned `@vN` or `latest` references
MUST NOT remain.

#### Scenario: No unpinned action references

- GIVEN `.github/workflows/code-quality.yml`
- WHEN scanned for `uses:` and `npx`/`pip install` tool invocations
- THEN every external action and tool is pinned by SHA

### Requirement: Duplicate 003 migration identity resolved

The duplicate `003` prefix between `003_economy_config.sql` and
`003_subtitles_notes.sql` MUST be resolved. On a live/deployed Supabase
project the resolution MUST be validated against `schema_migrations` or
shipped as a no-op reconciliation migration, NEVER as a raw file rename that
desyncs `schema_migrations`.

#### Scenario: No duplicate 003 prefix

- GIVEN `supabase/migrations/`
- WHEN migration prefixes are listed
- THEN at most one file carries the `003` prefix

#### Scenario: Live schema_migrations checked before rename

- GIVEN the project is deployed and `schema_migrations` is live
- WHEN the duplicate is resolved
- THEN the resolution is validated against the live table or done as a no-op reconciliation migration

### Requirement: greeting_config updatedAt tracking

`greeting_config` MUST track the last update time via an additive `updatedAt`
column (see the `greeting-config` delta for the column and poll-fallback
contract). The hygiene aspect: the column MUST exist and the model/db layer
MUST round-trip it, closing the gap where the Realtime poll fallback could
not query `greeting_config` incrementally.

#### Scenario: Model round-trips updatedAt

- GIVEN `GreetingConfig` and an `updatedAt` value T
- WHEN the model is serialized and re-read
- THEN `updatedAt` is preserved

### Requirement: AGENTS.md gaps closed

`AGENTS.md` MUST document any rule gaps surfaced during Cycle 1 (e.g. the
cairosvg libcairo constraint, the cache-key guild-scoping rule, the
do-not-merge `time.py` vs `timeparse.py` rule) so reviewers enforce them.

#### Scenario: cairosvg constraint documented

- GIVEN `AGENTS.md`
- WHEN scanned
- THEN it documents the `python:3.11-slim` no-`libcairo` constraint and the Pillow-default + probe-fallback contract

#### Scenario: cache-key rule documented

- GIVEN `AGENTS.md`
- WHEN scanned
- THEN it documents that new caches MUST use `cache_key(guild_id, entity)`

### Requirement: Font missing fallback is non-breaking

The renderer MUST handle a missing font file (`Inter-Regular.ttf`) by falling
back to `ImageFont.load_default()` on `OSError`, logging at WARNING, and
still producing a card. The font file is present in Cycle 1
(`assets/fonts/Inter-Regular.ttf`); this requirement governs the degradation
path and any Cycle 2 SVG base64 font embed is OUT OF SCOPE.

#### Scenario: Font missing degrades gracefully

- GIVEN `Inter-Regular.ttf` cannot be opened
- WHEN a card is generated
- THEN `ImageFont.load_default()` is used, a WARNING is logged, and the card still renders
