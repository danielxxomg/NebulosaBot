# Tasks: hygiene-and-qa-standardization

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 0 authored (~10 ref ops) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Delivery strategy | auto-chain |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | PR | Test | Harness | Rollback |
|------|------|----|------|---------|----------|
| 1 | Pre-flight+baseline aff623d | PR1 | `gh pr list`; `rev-parse` | N/A | `tag -d; push --delete` |
| 2 | Delete refs+verify | PR1 | `branch -a`; `ruff/mypy/pytest` | N/A | `branch <n> <SHA>` |

Low→single PR; one commit/phase; no source edits.

## Phase 1: Pre-flight

- [x] 1.1 `gh pr list` pr2a/pr2b — W: delete breaks open PR — A: both `gh pr list --head feat/ticket-integrity-recovery-pr2a|pr2b` empty else abort — E: gh output in sdd-attempt
- [x] 1.2 Confirm master aff623d clean — W: baseline tip — A: `rev-parse HEAD`==aff623d, `status` clean, stash empty — E: logged

## Phase 2: Baseline

- [x] 2.1 Create `archive/2026-08-20-hygiene-and-qa-standardization` at aff623d — W: recovery anchor — A: `git tag <name> aff623d && rev-parse <name>`==aff623d — E: SHA logged
- [x] 2.2 Push baseline tag — W: remote recovery — A: `push origin tag <name>` ok — E: push output

## Phase 3: Locals

- [x] 3.1 Delete `ticket-physical-split-s3d4b-views` (6c4c4dc==a80f129) — W: patch-id twin on master — A: `branch -D` ok, `cherry master` empty — E: cherry+branch before/after
- [x] 3.2 Delete `ticket-physical-split-s3d3a` (961123b) — W: ahead0 behind32 contained — A: `branch -D` ok — E: branch list
- [x] 3.3 Delete `cleanup-stability-pr3` (639ca5b) — W: ahead0 behind57 contained — A: `branch -D` ok, only master — E: branch output

## Phase 4: Remotes

- [x] 4.1 Delete `origin/feat/ticket-integrity-recovery-pr2a|pr2b` (8cb5674 dup) — W: SHA dup superseded pr2 0232a0a+S3 — A: `push origin --delete <both>`+`fetch --prune` — E: push+ls-remote clean
- [x] 4.2 Verify no PR broken — W: guard Phase1 — A: `gh pr list` clean — E: gh output

## Phase 5: Tags

- [x] 5.1 Delete 4 local tags — W: dups/superseded pr2a/pr2b→8cb5674, welcome fb8da77→644b163, wip f197fbc stash — A: `tag -d <4>`; `tag --list 'archive/*'` excludes — E: list before/after
- [x] 5.2 Push tag deletions — W: remote hygiene — A: `push origin --delete tag <each>` ok — E: push output
- [x] 5.3 Record opencode.json decision — W: only fb8da77/f197fbc, never on master — A: sdd-attempt notes exploration — E: note

## Phase 6: Verification

- [x] 6.1 Verify `git branch -a` clean — W: prove hygiene — A: `branch`==`* master`, no pr2a/pr2b, deleted tags absent, baseline at aff623d — E: branch-a+tag-list+rev-parse
- [x] 6.2 Re-verify gates — W: no drift — A: `ruff 0.15.20`, `mypy bot/` strict, `pytest --cov-fail-under=75` ≥75% — E: gate outputs
- [x] 6.3 Record rollback — W: recovery — A: sdd-attempt lists `branch <n> <SHA>`/`push <SHA>:refs/heads/<b>`/`tag <n> <SHA>` for 6c4c4dc 961123b 639ca5b 8cb5674 fb8da77 f197fbc aff623d — E: log
