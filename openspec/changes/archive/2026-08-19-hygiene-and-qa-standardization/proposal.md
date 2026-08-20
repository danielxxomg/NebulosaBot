# Proposal: hygiene-and-qa-standardization

## Intent

Remove stale git refs and confirm QA gates at `aff623d`. Master at target (ruff 0.15.20, 14 rules, mccabe 15, cov 75, mypy strict, CI 3.11-3.14); dead S3/pr2 refs linger. Ref-only hygiene — no source changes.

## Scope

### In Scope
- Delete 3 local branches: `s3d4b-views` (`6c4c4dc` == `a80f129` on master), `s3d3a` (`961123b`), `cleanup-stability-pr3` (`639ca5b`) — all contained.
- Delete 2 duplicate remotes: `origin/feat/ticket-integrity-recovery-pr2a`/`pr2b` (both `8cb5674`, superseded by merged `pr2` `0232a0a` + S3 refactor).
- Delete 4 archive tags: `pr2a`/`pr2b` dups, `welcome-localization-ux` (`fb8da77` superseded by `644b163`), `wip-stash` (`f197fbc` 3-parent stash).
- Tag baseline `archive/2026-07-hygiene-sweep` → `aff623d`; verify gates unchanged.

### Out of Scope
- S7 ticket-repair, S2 cache, any domain logic.
- Edits to `pyproject.toml`/`Makefile`/`ci.yml`/`.pre-commit-config.yaml`/`.gga`.
- `verify.coverage_threshold` 0.70 vs 75 — flag only.
- Rescuing `ad41f3f`/`07c0853`; never merge `f197fbc`. Landing `opencode.json` toggle (only on `fb8da77`).

## Capabilities

### New Capabilities
- None — ref hygiene only.

### Modified Capabilities
- None — gates at target, no spec deltas.

## Approach

Approach 2 — archived-tag-then-delete. Pre-flight `gh pr list` for `pr2a`/`pr2b`; if clean, tag `aff623d`, push baseline, then `branch -D` locals and `push origin --delete` remotes/tags. Dangling commits to GC (`ad41f3f`==`a306384`, `07c0853`==`0fce4ab`; `f197fbc` is 3-parent stash, must not merge).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| git refs (local) | Removed | 3 branches deleted |
| git refs (remote) | Removed | 2 duplicate refs |
| git tags | Removed/New | 4 archive tags removed, 1 baseline added |
| `pyproject.toml` / `ci.yml` / `.pre-commit-config.yaml` / `.gga` | Verified | Standardized — no edits |
| `openspec/config.yaml` | Flagged | `coverage_threshold: 0.70` drift out-of-scope |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Open PR on `pr2a`/`pr2b` | Low | `gh pr list --head` before delete; abort if found |
| Loss of `opencode.json` (fb8da77) | Low | 11-line content in exploration; recreate on demand |
| Tag irreversible | Low | SHAs recorded; baseline preserves state |
| No code risk | None | Refs only — 1812 tests / 88.6% cov untouched |

## Rollback Plan

Branches: `git branch <name> <SHA>`. Remotes: `git push origin <SHA>:refs/heads/<branch>`. Tags: `git tag <name> <SHA> && git push origin tag <name>`. Baseline tag + 90-day `reflog` retain recovery.

## Dependencies

- `gh` CLI authenticated for PR pre-flight.
- Push access to `origin` for remote/tag deletes.

## Success Criteria

- [ ] `git branch` only `master`; no `pr2a`/`pr2b`; deleted archive tags absent, baseline at `aff623d`.
- [ ] Former branches verified contained via `git cherry` / patch-id.
- [ ] Gates re-verified unchanged (ruff 0.15.20, cov 75, mypy strict).
- [ ] No PR broken by pre-flight check.
