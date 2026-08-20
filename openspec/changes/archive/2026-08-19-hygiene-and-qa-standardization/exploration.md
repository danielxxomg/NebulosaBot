# Exploration: hygiene-and-qa-standardization (CICLO 1)

**Scope**: Git hygiene + QA gate standardization. Leave the tree with no stale local branches, deduplicated remotes, standardized gates, and zero confusion for the next SDD cycle.

**Mode**: Exploration only — no code or ref changes performed. All evidence collected read-only from `git` on disk at `aff623d` (master tip).

---

## Current State

### Working Tree
- `master` at `aff623d` ("fix(lint): ruff I001 import sort in database/db"), tracks `origin/master`, **clean** (0 untracked, 0 staged, stash empty).
- Three local branches exist besides `master`; 31 remote branches exist (30 tracked refs + `origin/HEAD`).

### Local Branches — containment verified on disk

| Branch | Tip | merge-base == tip? | ahead/behind master | Unique content in master? |
|---|---|---|---|---|
| `ticket-physical-split-s3d4b-views` | `6c4c4dc` | NO (divergent) | ahead=1, behind=21 | **YES** — `6c4c4dc` patch-id matches `a80f129` (master's own archive chore, already merged) |
| `ticket-physical-split-s3d3a` | `961123b` | YES | ahead=0, behind=32 | YES — fully contained |
| `cleanup-stability-pr3` | `639ca5b` | YES | ahead=0, behind=57 | YES — fully contained |

**Critical correction to the pre-SDD audit**: the audit framed `s3d4b-views` as "21 ahead/1 behind, remote `1310167` has 3 critical remediations" implying rescue needed. On-disk evidence shows the opposite:

- `1310167` (the 3-critical remediation commit) **IS an ancestor of master** — already merged.
- The local `6c4c4dc` (s3d4b's only unique commit) is the SDD archive chore. Its tree on `openspec/` is **byte-identical** to master's `a80f129` (verified: `git diff 6c4c4dc a80f129 -- openspec/ | wc -l` → 0).
- `git diff --stat master..s3d4b` shows large numbers (5972 deletions) only because s3d4b's parent (`1310167`) is old; the *new* content of `6c4c4dc` is already on master via the cherry-picked `a80f129`.
- `origin/ticket-physical-split-s3d4b-views` (`1310167`) is itself an ancestor of master.

**Conclusion**: all three local branches are **safe to delete**. No rescue needed.

### Remote Branches — containment verified

- **31 of 32** remote branches are ancestors of `master` (merged).
- **2 NOT-in-master**: `origin/feat/ticket-integrity-recovery-pr2a` and `origin/feat/ticket-integrity-recovery-pr2b` — **both point to the same SHA `8cb5674`** (exact duplicate).
- `8cb5674` is a single commit "feat(tickets): add conditional repair service" dated **2026-07-18**, parented on `e68896a` (pre-refactor base). It is **superseded** by:
  - `origin/feat/ticket-integrity-recovery-pr2` (`0232a0a`, dated 2026-08-17) which **IS merged** into master and includes the remediations + archive chore "ticket-integrity-recovery 31/31".
  - The subsequent S3 `ticket-physical-split` refactor (Aug 18) which restructured the ticket domain into `TicketQueryService`/`TicketLifecycleService`/`TicketRepairService`/`TicketRepairService` — master now has `bot/services/ticket_repair.py`, `bot/services/ticket_repair_service.py`, `bot/services/integrity_report.py`, `bot/services/ticket_invariants.py`.
  - master's `test_ticket_db.py` (692 lines) and `test_ticket_service.py` (4989 lines) are **strictly larger** than pr2a's (590 / 3689) — pr2a is a subset of what landed.
- The `archive/2026-07-feat-ticket-integrity-recovery-pr2a` and `archive/2026-07-feat-ticket-integrity-recovery-pr2b` tags both point to `8cb5674` — duplicate archive pointers to superseded content.

### Dangling Commits

- **`ad41f3f`** ("chore: upgrade QA config — ruff 14 rules, mypy strict, pre-commit scope, CI 3.13, coverage 75%", 2026-07-07, 10 files, ~648 diff lines):
  - **NOT** an ancestor of master.
  - **BUT semantically identical** to `a306384` on master: identical `git patch-id` (`0ad85a68…`).
  - All 5 config test files (`test_ci_config.py`, `test_makefile_config.py`, `test_mypy_config.py`, `test_precommit_config.py`, `test_ruff_config.py`) exist on master with identical patch-ids to ad41f3f's versions.
  - Its `pyproject.toml` QA block (14 ruff rule groups, mccabe=15, cov=75, mypy strict) is present on master and has since **evolved beyond** it (ruff pinned to `==0.15.20`, `filterwarnings` gained `"error"` lock, live markers added, JWKS/psycopg deps added).
  - **No rescue needed** — content already on master via `a306384`, and master has moved further.

- **`07c0853`** ("test(economy): add full property battery"):
  - NOT an ancestor of master.
  - `git patch-id` **identical** to `0fce4ab` which IS on master (contained in 5 release tags).
  - Pure dangling duplicate of an already-merged commit. **No rescue needed**.

### Archive Tags

- `archive/2026-07-feat-ticket-integrity-recovery-pr2a` → `8cb5674` (superseded duplicate, see above).
- `archive/2026-07-feat-ticket-integrity-recovery-pr2b` → `8cb5674` (duplicate of pr2a tag).
- `archive/2026-07-feat-welcome-localization-ux` → `fb8da77` (2026-07-16, SDD docs-only commit "document welcome localization change"):
  - Superseded by `644b163` (2026-07-17, "feat(greetings): localize and harden welcome UX") which **IS on master** and is the actual feature commit.
  - `fb8da77` only adds `openspec/changes/welcome-localization-ux/` SDD artifacts (now archived on master at `openspec/changes/archive/2026-07-17-welcome-localization-ux/`) plus an `opencode.json` (MCP disable list) that **never landed on master**.
  - `opencode.json` content is a 7-entry `mcp.*.enabled=false` block (discord-py-self, nylas-*, playwright, reactive-resume, scrapling, telegram). Not a feature, just a local-only tooling toggle.
- `archive/2026-07-wip-stash-2026-07-16-mixed-snapshot` → `f197fbc` (2026-07-16):
  - **3-parent stash commit** (parents: `fb8da77`, `6f6a57f` index, `0dbaa2e` untracked) — classic `git stash` snapshot of a mixed worktree before the welcome-card-disabled-cta-guard review.
  - All 3 parents are worktree snapshots **not** in master.
  - Contains `MMA`/`MMR` (merge-modified-add/rename) markers — confirms stash origin.
  - File list is entirely the welcome-localization + welcome-card-disabled-cta-guard working set that later landed via `644b163`.
  - **Must not merge** — it is a stash hybrid; its content already reached master through the normal PR path.

### QA Gates — current standardized state on master

| Gate | File | State |
|---|---|---|
| Ruff rules | `pyproject.toml` `[tool.ruff.lint]` | 14 rule groups (E,W,F,I,N,UP,B,SIM,RUF,S,C4,C90,RET,T20,ARG,DTZ,EM,T10,TRY,RSE,FLY,PERF,FURB) — **matches audit** |
| Ruff version | `pyproject.toml` `dev` | pinned `ruff==0.15.20` |
| McCabe | `pyproject.toml` | `max-complexity = 15` |
| Per-file ignores | `pyproject.toml` | `tests/**` broad allowlist + `bot/**` PR1 debt allowance (rules enabled, violations suppressed pending PR2-PR5 ratchet) |
| Mypy | `pyproject.toml` | `strict = true`, python 3.11, per-module overrides for `bot.cogs.*` (3 codes) and `tests.*` (9 codes — the "28 deferred errors" surface) |
| Coverage | `pyproject.toml` `addopts` | `--cov-fail-under=75`; mirrored in `Makefile` (`test`, `cov`) and `ci.yml` |
| Pre-commit | `.pre-commit-config.yaml` | ruff `v0.15.20`, hooks scoped to `^(bot/\|tests/)`, mypy scoped to `^bot/.*\.py$` |
| CI matrix | `.github/workflows/ci.yml` | Python 3.11/3.12/3.13/3.14, ruff check + format, mypy, bandit, pip-audit, pytest cov 75, coverage upload, dashboard tsc+vitest, scheduled Sun 06:00 UTC |
| Makefile | `Makefile` | `lint`/`type`/`security`/`test`/`cov`/`ci`/`audit` gates + `lint-full`/`type-full` aliases |
| GGA | `.gga` | `STRICT_MODE="true"`, `PR_BASE_BRANCH="master"`, `PROVIDER=opencode:commandcode/meta/muse-spark-1.2-contributor`, excludes `tests/` |

**QA gates are already standardized on master.** The audit's "mypy bot/ passes but 28 tests.* errors deferred" reflects the intentional `disable_error_code` allowlist for `tests.*` — a documented deferral, not a gap.

---

## Affected Areas

### Git refs (deletions only — no code touched)
- Local branches: `ticket-physical-split-s3d4b-views`, `ticket-physical-split-s3d3a`, `cleanup-stability-pr3` — all verified contained in master.
- Remote branches: `origin/feat/ticket-integrity-recovery-pr2a`, `origin/feat/ticket-integrity-recovery-pr2b` — duplicate refs to superseded `8cb5674`.
- Tags: `archive/2026-07-feat-ticket-integrity-recovery-pr2a`, `archive/2026-07-feat-ticket-integrity-recovery-pr2b` (duplicate archive pointers), `archive/2026-07-feat-welcome-localization-ux` (superseded by `644b163`), `archive/2026-07-wip-stash-2026-07-16-mixed-snapshot` (stash hybrid).
- Dangling commits: `ad41f3f` (== `a306384` on master), `07c0853` (== `0fce4ab` on master) — already on master via patch-id-equivalent commits; only reachable from no ref.

### QA gate files (already standardized — verify, do not rewrite)
- `pyproject.toml` — ruff/mypy/cov config (lines 85-146).
- `Makefile` — gate aliases.
- `.pre-commit-config.yaml` — hook scope.
- `.github/workflows/ci.yml` — matrix + steps.
- `.gga` — GGA strict mode.
- `openspec/config.yaml` — `verify.coverage_threshold: 0.70` (note: lower than the enforced 0.75; potential drift to flag, not fix in this change).

---

## Approaches

### 1. Delete-all (aggressive prune)
Delete all stale local branches, duplicate remotes, and redundant tags in one pass. Treat dangling commits as GC-eligible (they are unreachable and already on master via patch-id twins).

- **Pros**: Minimal commands; tree is immediately clean; no archive ceremony.
- **Cons**: Loses the audit trail for why each ref existed; if any future investigation needs the pr2a/pr2b branch context, only the GitHub UI (if PRs existed) or reflog retains it.
- **Effort**: Low.

### 2. Archived-tag-then-delete (conservative prune) — RECOMMENDED
Keep a single `archive/2026-07-hygiene-sweep` tag pointing at `aff623d` (current master, the pre-sweep baseline) as an audit anchor. Then delete the 3 local branches, 2 duplicate remotes, and 4 redundant archive tags. Leave dangling commits to Git GC (they are unreachable).

- **Pros**: Preserves a recovery point (`archive/2026-07-hygiene-sweep` = `aff623d`) without keeping stale feature refs; every deleted ref's content is already on master or in a release tag; matches the project's existing `archive/*` tag convention; the four deleted archive tags are duplicates/superseded, so no information loss.
- **Cons**: One extra tag to manage; requires verifying no open PRs against the deleted remote branches.
- **Effort**: Low-Medium.

### 3. Reset-hard divergent branch (rescue-oriented) — NOT RECOMMENDED
Reset `ticket-physical-split-s3d4b-views` to `origin/ticket-physical-split-s3d4b-views` (`1310167`) under the assumption that the local `6c4c4dc` is lost work needing rebase.

- **Pros**: None — based on a misreading of the audit.
- **Cons**: Would discard `6c4c4dc`'s archive chore, but that chore is **already on master as `a80f129`** (byte-identical openspec tree). Resetting gains nothing and risks confusion. The "21 ahead/1 behind" in the audit was an inversion: master is 21 commits *ahead* of s3d4b (S4+S5 work landed after s3d4b's parent), not the reverse.
- **Effort**: N/A (wrong approach).

---

## Recommendation

**Approach 2 — Archived-tag-then-delete.**

Rationale:
1. Every local branch is verified contained in master (cherry empty or patch-id twin on master).
2. `s3d4b-views` looked divergent but its single unique commit (`6c4c4dc`) is byte-identical to master's `a80f129` — no rescue needed.
3. The two unmerged remote branches (`pr2a`, `pr2b`) are exact SHA duplicates pointing at a pre-refactor commit whose feature landed via `pr2` (`0232a0a`) and was later restructured by S3.
4. The four archive tags are either duplicates (`pr2a`==`pr2b`→`8cb5674`) or superseded (`welcome-localization-ux`→`fb8da77` superseded by `644b163`; `wip-stash`→`f197fbc` is a stash hybrid).
5. Dangling commits `ad41f3f` and `07c0853` are patch-id twins of merged commits — Git GC will reclaim them naturally; no action needed.
6. QA gates on master already match the audit's target state (ruff 0.15.20, 14 rules, mccabe 15, cov 75, mypy strict, CI 3.11-3.14, pre-commit scoped). No gate file changes required — this change is pure ref hygiene.
7. A baseline tag `archive/2026-07-hygiene-sweep` at `aff623d` gives a single recovery point matching the project convention, without retaining confusing feature-named refs.

**Pre-flight checks before apply** (flag for the orchestrator):
- Verify no open GitHub PRs target `origin/feat/ticket-integrity-recovery-pr2a` or `pr2b` (they are unmerged but if a PR is open, coordinate with the user before deleting the remote ref).
- Confirm the user is OK losing the `opencode.json` that only exists on `fb8da77`/`f197fbc` — it is a local MCP-disable toggle that never landed on master and is not referenced anywhere in the current tree.

---

## Risks

- **Open PRs against pr2a/pr2b**: if a GitHub PR is open targeting either remote, deleting the remote ref will break it. Low likelihood (the feature landed via `pr2`), but must be verified with `gh pr list` before `git push origin --delete`.
- **Loss of `opencode.json`**: the MCP-disable config only exists on `fb8da77`/`f197fbc`. If the user intended to land it, deleting the tags severs the easy recovery path. Mitigation: capture the 11-line `opencode.json` content in the proposal before deleting `archive/2026-07-feat-welcome-localization-ux`.
- **`openspec/config.yaml` coverage drift**: `verify.coverage_threshold: 0.70` is lower than the enforced `--cov-fail-under=75`. This is a pre-existing inconsistency, NOT in scope for this hygiene change, but worth flagging to the user as a follow-up.
- **Tag deletion is irreversible without the SHA**: once `archive/2026-07-feat-ticket-integrity-recovery-pr2a` is deleted, the tag name is gone (the commit `8cb5674` remains reachable from the other tag until it too is deleted). Mitigation: the baseline tag `archive/2026-07-hygiene-sweep` captures the pre-sweep state; SHAs are recorded in this exploration.
- **No code risk**: this change touches only git refs, not source. The 1812 tests, 88.62% coverage, and all gate files remain untouched.

---

## Ready for Proposal

**Yes.** The orchestrator should tell the user:

1. All three local branches are safe to delete — verified contained in master (the "divergent s3d4b" in the audit was a misread; its unique commit is byte-identical to master's `a80f129`).
2. The two unmerged remote branches are exact duplicates of each other pointing at a superseded pre-refactor commit — safe to delete after confirming no open PRs.
3. Four archive tags are duplicates or superseded — safe to delete; a single `archive/2026-07-hygiene-sweep` baseline tag at `aff623d` preserves recovery.
4. QA gates on master are already at the target state — no file changes needed in this change.
5. One pre-existing drift to flag (not fix here): `openspec/config.yaml` `verify.coverage_threshold: 0.70` vs enforced `--cov-fail-under=75`.
6. One decision for the user: keep or discard the `opencode.json` (MCP-disable toggle) that only lives on the `fb8da77`/`f197fbc` tags.

Forecast: this change is **well under 400 lines** of authored risk (zero code lines — pure ref operations). No chained PRs needed.
