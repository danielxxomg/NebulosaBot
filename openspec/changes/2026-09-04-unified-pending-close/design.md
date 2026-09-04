# Design: Unified Pending Close

## Technical Approach

Stacked slices, cuts-fund-probes. S0 amends governance (docs-only, zero ledger delta); S1/S5/S2 bank ~1,485 lines of parametrization cuts until the Slice Headroom Gate (margin ≥100, i.e. lines ≤61,380) holds; only then S3a/S3b resurrect dc371d0 probe additions (+991 net vs its parent; gross-vs-HEAD re-measured per slice); S4 fixes all 321 oxlint findings and flips advisory→blocking; S6 re-measures. Maps to proposal approach and delta-spec gates (ledger, headroom, assert-strength, staging discipline).

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Cut composition: conservative-only (~435 fat-file + ~565 extended = ~1,000) | Zero aggressive risk; lands at ~61,469 — gate met, aim ≤61,300 missed by ~169 | Floor: land first |
| Full cut: + vetted aggressive to fat-file ~920 (proposal math → 60,984) | Needs same-polarity aggressive groups; each needs falsification harness per #5119 | Recommended target AFTER floor holds; aggressive groups individually gated |
| Resurrection via `git show dc371d0:<path>` + manual reconcile | Exact probe semantics preserved; conflicts where files evolved (#97 pickers, migration-pin syncs) | Chosen over fresh authoring |
| S5 runs as S1.5 (before S2) | Banks extended-cut headroom early; S2 then carries only cog-cut + a diff-check | Resolves proposal S1.5 question: order S0→S1→S5→S2→gate→S3a→S3b→S4→S6 |
| S4 single vs split | ~321 findings; func-style(107)+regexp(92) ≈ 200 mechanical edits, likely 400–700 diff lines | Measure-first: single S4 if diff ≤800 else S4a (mechanical 199) / S4b (rest); CI flip rides last oxlint slice |

## Data Flow

```
S0 amend ──→ S1 cut-A ──→ S5 cut-C ──→ S2 cut-B ──→ [GATE margin≥100?]
  (docs)      (service)     (14 files)    (cog)        no→more cuts / yes→probes
                                                        ──→ S3a ──→ S3b ──→ S4 ──→ S6
                                                          welcome/  pickers/  oxlint  re-measure
                                                          goodbye   live_cat
Ledger re-measured every slice: find tests -name '*.py' -exec wc -l + ; --collect-only -q; --cov (seed 42)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `openspec/specs/test-suite-governance/spec.md` | Modify (S0) | Headroom, 1500-vs-800 coexistence, aim-as-buffer, GGA note (delta spec already defines text) |
| `tests/test_ticket_service.py` | Modify (S1) | Parametrize service-side groups (~350: countdown trio ~60, transfer/rename/sanitized/subject/configure pairs ~22–24 each, guard/channel-cf/delete-category/close_reason/unclaim/reopen/sweep-load/create-cf/get_notes/list ~8–21 each) |
| 14 files per #5125 | Modify (S5) | Conservative groups (~565: database guards 80/filters 28/onwrite 30, ticket_db 25+21, invariants 50, greeting_service 43, helpers 39, infraction trio 36, realtime 35+20, logging 28, audit_listener 30, economy 27, greeting_config 30, migrations 20, views 15, sentinel 10) |
| `tests/test_tickets_cog.py` | Modify (S2) | Cog groups (no_guild quads ~31+13, mod-gated ~5, + cog pairs); then diff-check `git diff dc371d0 HEAD -- test_i18n.py test_pr2_expired_scans_red.py` — empty (confirmed at design time) means dc371d0 dedups already landed, skip re-apply |
| `tests/test_setup_module_welcome.py`, `test_setup_module_goodbye.py` | Modify (S3a) | Re-apply dc371d0 probe hunks (+260/+137 gross) + harden `test_i18n.py:537` to exact-equality mirroring `:525` |
| `tests/test_setup_panel_pickers.py`, `tests/test_live_catalog.py` | Modify (S3b) | Re-apply probe hunks (+577/+194 gross) + harden `test_live_catalog.py:87` (`assert mod is not None` → importable-identity exact pattern per `:525` model) |
| `dashboard/**`, `.github/workflows/code-quality.yml` | Modify (S4) | Per-rule fix-all (table below); remove `continue-on-error:80`, re-stamp baseline comment `:76`, flip steps `:103`/`:108` to blocking; node stays 24 |

Per-group line ranges are NOT pinned here (would be invented): tasks phase re-derives each range by named-test grep before editing. Do-not-merge (per #5122, binding): success-vs-error paths, opposite-polarity asserts, distinct assertion depth, already-parametrized matrices. Cut procedure per group: extract shared params into existing fixtures/helpers, keep per-case `match=` strings and assertion messages, readable `ids=`, bilingual es/en strings per case, embed-type fidelity (ephemeral-vs-plain).

## Interfaces / Contracts

No product-code contracts change. Slice contract (per delta spec): commit body carries `files: A→B, lines: X→Y, collected: N→M, cov: P%→Z%`, seed 42. S4 contract: `npx oxlint` → 0 findings. S6 contract: post-merge ledger re-measure before declaring done (#5106 drift lesson: merge added +5 over ceiling silently).

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Cuts (S1/S2/S5) | Same-assertion semantics | Collected-count parity documented (N→1 drop expected, "same assertions"); falsification harness (mock return-vs-raise probe) per #5119; KEEP 7 files green |
| Probes (S3a/S3b) | Coverage ≥80% per file | FULL-suite `--cov` only — scoped runs under-measure (setup_panel 38% scoped vs 62% full, #5121 trap); revert-on-dip below 80.50% total |
| Oxlint (S4) | 0 findings, blocking green | `npm run lint:ox` local (node ≥22.6 for TS config; CI node 24); CI workflow run must pass with `continue-on-error` removed |
| Governance (S0/S6) | Spec text gates | Headroom scenario pair + ledger-present scenario from delta spec |

S4 per-rule mechanics: func-style 107 → function declarations; require-unicode-regexp 92 → `u` flags; import/first 16 → hoist; sort-keys 12 → key order; no-non-null-assertion 11 → narrowing; array-sort 8 → `toSorted`/comparator; no-unused-vars 8 → remove; require-await 10 → async cleanup; rest ~59 individually.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary in product code. Git/CI steps are procedural (done by the operator), not shipped behavior; GGA item closed by decision (repro exit 0, no upstream report).

## Migration / Rollout

No migration. Rollout = stacked-to-master slices (≤800 diff lines/PR; S4 split by measure-first rule). Rollback in reverse stack order; probes revert before cuts re-land; re-measure ledger after any revert. Squash-merge breaks stacked ancestry (#5106): use merge commits or consolidate into one integration PR after first squash.

## Open Questions

- [ ] Exact S1-vs-S2 split of the ~920 fat-file yield (tasks phase pins per-group ranges first)
- [ ] Net-vs-HEAD of S3a/S3b will differ from dc371d0's +991 (parent 98c1847 ≠ HEAD) — re-baselined at apply time, ceiling is the gate
- [ ] Aggressive-group shortlist for the 435→920 climb (needs falsification harness each)
