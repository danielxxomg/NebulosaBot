# Proposal: Bot Docs Polish

## Intent

NebulosaBot has 28 commands across 7 cogs but zero user-facing docs. Command descriptions are inconsistent (missing periods, terse phrasing). The avatar renders at thumbnail size (~80px). This change ships a Spanish manual, normalizes descriptions, fixes avatar display, and adds missing `@app_commands.describe()` annotations.

## Scope

### In Scope
- `docs/MANUAL.md` in Spanish — quick start, config, bot state, commands by audience, ticket system, economy, greetings, known debt
- Normalize 28 command descriptions: consistent periods, improved phrasing
- Add `@app_commands.describe()` where parameters lack annotations
- Avatar: `set_thumbnail` → `set_image` for larger display

### Out of Scope
- Ticket custom fields (done), slash description localization (English by design), README/PRODUCT.md, `/help` behavior changes, i18n locale files

## Capabilities

### New Capabilities

_None — manual is a docs artifact, not a spec capability._

### Modified Capabilities

- `utility-commands`: Avatar requirement changes from thumbnail to image embed

## Approach

**Manual**: Single `docs/MANUAL.md`, Spanish, structured by audience (users → mods → admins). Concise — configs, use cases, command table, debt. References `/help` for live listing.

**Avatar**: One-line in `bot/cogs/utility.py` — `set_thumbnail` → `set_image`, optional `?size=1024`.

**Descriptions**: Edit `description=` across 7 cog files (~28 edits). Imperative mood, trailing period. Add `@app_commands.describe()` to unannotated params.

**Testing**: TDD. Avatar test assertion update. No tests for description strings (UI metadata).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `docs/MANUAL.md` | New | Spanish manual |
| `bot/cogs/utility.py` | Modified | Avatar display fix |
| `bot/cogs/*.py` (7 files) | Modified | Description polish + annotations |
| `tests/cogs/test_utility.py` | Modified | Avatar assertion update |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Manual staleness | Medium | Keep concise; reference `/help`; note in debt section |
| `set_image` "too large" | Low | Test in Discord; `?size` adjustable |
| Description edits need tree sync | Low | Restart or `/sync` after merge |

## Rollback Plan

All changes are additive/cosmetic. Delete `docs/MANUAL.md`, revert cog strings, revert `set_image` → `set_thumbnail`. Single `git revert` suffices. No schema/service/cache changes.

## Dependencies

- None

## Success Criteria

- [ ] `docs/MANUAL.md` exists in Spanish, covers all 28 commands by audience
- [ ] All descriptions end with period, use clear imperative phrasing
- [ ] `/avatar` renders at embed image size (~300-400px)
- [ ] Unannotated parameters have `@app_commands.describe()`
- [ ] Existing tests pass; avatar test updated
