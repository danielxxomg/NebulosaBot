# FOLLOW_UP — Dedicated `/setup` + Permission Audit (non-goal for this recovery)

## Purpose

`product-artifact-audit` (PR1–PR4b) completed the bounded ticket-integrity
recovery cluster: evidence-gated repair, a single coordinator, channel-delete
routing (PR4a), and the sweep/manual adapters + logging records (PR4b). This
cluster deliberately did **not** audit the broader `/setup` command, guild
configuration, or the complete permission/capability matrix. This file records
that dedicated audit as an explicit follow-up so the work is not lost when the
recovery cluster is verified and archived.

## Canonical permission model (already in place, from PR3)

The `ticket-integrity` authority model (`bot/services/ticket_invariants.py`)
enforces:

- **One mandatory canonical moderator role** — the single core role for
  guild-scoped operational authority.
- **Optional specialist roles** — refinements only; never mandatory parallel
  permission sources.
- **Owner / Administrator local bypass** — the guild owner and Discord
  Administrators may bypass the configured-role check ONLY inside their own
  guild.
- **Bot owner = global diagnosis, not silent mutation** — the bot/application
  owner receives read-only cross-guild diagnosis. Any global mutation requires
  an explicit, targeted, confirmed, audited `GlobalMutationGrant`. There is
  never a silent mutation bypass.

## What the dedicated audit must cover (non-goals here)

- `/setup` command surface (`bot/cogs/setup.py`): which fields are
  configurable, who may run it, and whether `mod_role_id` is truly optional
  versus required by the permission model.
- The complete capability matrix: every command/button/permission check across
  cogs, views, and the dashboard mirror (`dashboard/lib/...`), reconciled
  against the canonical one-role + owner/admin model.
- Reconciliation of `GuildConfig.mod_role_id` optionality with the invariant's
  "one mandatory canonical mod role" requirement — verify no silent fallback
  grants authority when the role is unset.
- Whether `is_mod`/`is_admin` checks (`bot/utils/checks.py`) and the invariant
  helpers share one source of truth, or drift.

## Explicit non-goals carried forward

- Close-UX localization keys (`tickets.close.result_*`) — tracked as
  reconciliation close-UX debt, out of scope for this recovery cluster.
- Backup/restore revalidation (G.4) — separate work, never activated here.
- Security Advisor WARN (leaked-password protection) + INFO
  (`rls_enabled_no_policy`) — tech debt for a later pass; never authorize
  repair.

## Guard

This recovery cluster stays unarchived until `verify-report.md` exists (see
`governance_guard.py` + `tests/test_product_artifact_audit_governance.py`).
The dedicated `/setup`/permission audit is a SEPARATE SDD change and must not
be folded into the recovery archive.
