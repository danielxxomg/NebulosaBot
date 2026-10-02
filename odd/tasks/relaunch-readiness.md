# NebulosaBot relaunch readiness

## Objective and problem

Prepare a verified, consistently versioned `1.1.0` candidate without rewriting
the product or adding new features. Scheduled backups have no observed successful
run, dependency advisories prevent Python CI tests from running, some local tests
mutate the checkout, and source metadata/documentation are inconsistent.

The existing setup tab bar is included. Production cleanup and publication are
separate, explicitly authorized operations, not side effects of this feature.

## Authorization and constraints

- Authorized: local source, test and documentation changes; a dedicated branch;
  checks and Conventional Commit work-unit commits; anonymous public PyPI/npm
  dependency metadata and package downloads when needed.
- Not authorized: secret access, production connections, real backups or restores,
  actual data/resource deletion, remote infrastructure changes, push, PR creation,
  merge, tags or release publication. Existing authorized GitHub access is read-only.
- Reset intent: discard application activity/configuration; preserve the current
  Supabase project and Discord application. Obsolete bot-owned ticket channels and
  panels require inventory, unambiguous ownership and approval of the concrete list.
- Preserve the historical SDD archive; compact active guides and valid contracts
  by domain. Historical instructions do not govern the new ODD workflow.
- Total Python test lines are informational. Do not weaken coverage, functional,
  lint, typing or architecture requirements, or cut useful tests cosmetically.
- Strict TDD is configured in `openspec/config.yaml:12`; runner: `uv run pytest`.
  Observe RED -> GREEN -> REFACTOR for meaningful deterministic behavior changes.
  Passive documentation receives structural/link checks, not invented RED evidence.
- Keep generated artifacts and credentials out of commits. No AI attribution.

## Repository and delivery boundaries

- Branch: `feature/relaunch-readiness`, created from `master`.
- Branch point / initial review boundary: `ba8a5dac6a1e118fe0647a0d18695ff7b076a41a`.
- Original branch `feature/setup-tab-bar` is preserved at `c12bcc4`.
  Integrate its existing `a83b37f` and `c12bcc4` work during T3, not silently in the base.
- Delivery strategy: `ask-on-risk`; cached chain strategy: `feature-branch-chain`.
  Future child PRs integrate through a dedicated relaunch branch; publication is
  not authorized yet. Keep tests/docs with each work unit and rollback boundary.
- Initial authored-change forecast: approximately 2,000-5,000 additions plus
  deletions, excluding generated lockfile churn; T4 needs a measured inventory.
  Running authored count: 0. No slice/PR boundaries have been published.
- About 400 authored changed lines per task is advisory, not a reason to omit
  tests, compress code or remove comments. Make one honest cohesive PR-slicing pass;
  report any unavoidable oversized unit for a maintainer exception.
- RDD: ON, decided by global, observed with `gentle-ai review mode status`.
  Do not change this preference. Normalize before functional verification/freeze.
  Assess each work-unit commit against the last reviewed boundary and follow exact
  provider transitions and candidate-specific human consent when review is due.
  Review does not authorize delivery. Failed assessment never implies low risk.

## Tasks and acceptance criteria

- [ ] **T1 — Safe deterministic QA**
  - Isolate hook execution and fault-injection tests from the real checkout/index;
    do not invoke real GGA/model review from the ordinary pytest suite.
  - Prevent Vitest from automatically reading the real `.env.local`.
  - Preserve meaningful behavior tests and add observed regression evidence.
  - Document the verification boundary and run safe Python/dashboard checks.
  - Route: delegated direct; preparation/research and multiple non-trivial files.
  - Commit: pending. Native risk/review outcome: pending.
- [ ] **T2 — Dependency and CI stabilization**
  - Resolve the logged anyio/GitPython advisories through compatible constraints
    and lockfile updates, without blanket advisory suppression.
  - Run security audit and Python functional tests independently in CI, retaining
    both as required checks. Confirm supported Python matrix behavior where available.
  - Route: delegated direct; resolver/CI research and multiple non-trivial files.
  - Commit: pending. Native risk/review outcome: pending.
- [ ] **T3 — Existing setup navigation closure**
  - Integrate the preserved tab-bar and embed-context work, without new features.
  - Verify permissions, component limits, persistent routing, refresh, localization
    and preserved author/footer context, with complete applicable QA.
  - Route: delegated direct for source integration/research; parent owns Git actions.
  - Commit: pending. Native risk/review outcome: pending.
- [ ] **T4 — Current documentation, governance and memory**
  - Consolidate active operational/development/product guides and valid contracts;
    retain and index historical SDD evidence rather than rewriting it.
  - Reconcile informational total-test-line policy and conflicting coverage claims
    against the existing stricter contract (at least 80.50%). Update affected guards.
  - Fix obsolete tooling/path/prefix guidance; make missing-document checks meaningful.
  - Consolidate current memory pointers and inspect project-local sync repairs with
    preservation/dry-run evidence. No unrelated-project changes or cloud enrollment.
  - Route: delegated direct; broad mapping and multiple non-trivial files.
  - Commit: pending. Native risk/review outcome: pending.
- [ ] **T5 — Backup and reset preparation only**
  - Prepare weekly encrypted backups with 30-day retention, failure/age alerts and
    genuine isolated restore acceptance. Pause for a decision if material cost or
    compatibility constraints prevent that profile; do not silently weaken it.
    A failed weekly copy can exceed seven days of exposure.
  - Guard absent/invalid DB connection settings without printing secrets. Do not
    assume a PostgreSQL server version or pooler setting from the failed run.
  - Prepare a scoped, inventory-first reset/cleanup procedure and verify fresh guild
    identities/defaults before dashboard traffic. No real connection, deletion,
    backup, restore, schema change or bot reactivation in this authorization.
  - Route: delegated direct; operational/code research and multiple non-trivial files.
  - Commit: pending. Native risk/review outcome: pending.
- [ ] **T6 — Consistent local release candidate**
  - Reconcile package/runtime version and changelog for candidate `1.1.0`; preserve
    published `v1.0.0`. Reassess SemVer if later authorized work changes compatibility.
  - Record full functional, static, build, integration and recovery evidence or their
    explicit unavailable/pending status. Do not claim production readiness prematurely.
  - Prepare final release/rollback notes and future slice boundaries; no actual tag,
    PR, merge or release publication.
  - Route: delegated direct; multiple metadata/docs files and verification commands.
  - Commit: pending. Native risk/review outcome: pending.

## Verification record

- Historical audit at `c12bcc4`: offline lint, typing and architecture passed;
  161 focused Python tests passed at seed `20261001`; dashboard lint had one warning.
- These are not branch-point/full-suite proof. Unfiltered Python and dashboard
  tests were withheld because of checkout mutation and environment-file loading.
- Backup run `36835825347` attempted a local Unix socket. Secret provisioning,
  server version, the other failure causes and provider/manual backups are unknown.
- Startup can insert missing guild rows without re-invite, but its backfill summary
  counts attempts and ignores gathered exceptions. Verify persistence explicitly.
- No task is closed until its required checks and work-unit commit are complete.
  Native review remains separate and candidate-specific. No task is complete yet.

### T1 implementation checkpoint (not committed)

- Writer-reported final code checks: 56 focused Python tests; lint/type/tach exit 0;
  3,113 Python tests passed, 19 skipped, 19 warnings, coverage 83.27%, seed 42;
  249 dashboard tests passed; dashboard lint exit 0 with one existing image warning.
- Independent bounded spot check reran the exact focused command: 56 passed.
  Tach and builtin prek hook behavior were observed in disposable fixtures.
- Source-text/metadata guards are not independent proof of runtime isolation.
  The development guide has been qualified accordingly; offline package-manager
  flags do not sandbox application network access or prove ignored-file integrity.
- Safety incident: before `envDir: false` was applied, the initial dashboard test
  suite and a project-config resolver ran against the real dashboard configuration.
  Default Vite loading could consume the existing `.env.local`. No actual secret
  values appeared in the captured output; absence of file access, transmission or
  ignored-file changes cannot be proven without an appropriate trace. The initial
  sequence violated the explicit environment-file boundary. Do not conceal this
  by claiming that no direct file-read tool was used.
- Current Vitest config disables automatic env-file loading. Source changes remain
  uncommitted; no publication, deletion, production operation or native START ran.
- Preliminary native assessment was unassessable/high because new files lacked an
  explicit inventory declaration. This is not low-risk evidence or a review receipt.
- Parent documentation qualification occurred after the reported final checks;
  recheck the current candidate after resumption, before a work-unit commit.

## Progress and next step

Planning branch/document prepared. Recovery mirror: `odd/relaunch-readiness/tasks`.
The user selected "Continue locally" after disclosure. The incident remains part
of the evidence; this is not retroactive authorization or an expanded scope.
Next: recheck the current candidate, inspect commit hooks without secret access,
commit the coherent work unit, and follow native assessment and candidate consent.
T1 is not closed yet. T2-T6 remain pending. No remote permissions have expanded.

Fresh recheck passed all eight commands: 3,113 Python tests, 19 skips, 19 warnings,
83.27% coverage at seed 42; 249 dashboard tests and the existing lint warning.
The actual pre-commit hook invokes `gga run` directly. Authorized metadata-only
inspection found `.gga` declaring
`opencode:commandcode/meta/muse-spark-1.3-contributor`, `AGENTS.md`, strict mode;
no `.gga.local` was found. No hook was executed or bypassed, and no credential
values/auth stores were inspected. Commit closure awaits specific authorization
for this review route and ordinary use of the selected existing OpenCode provider
session. Metadata declarations do not prove availability or runtime overrides.
