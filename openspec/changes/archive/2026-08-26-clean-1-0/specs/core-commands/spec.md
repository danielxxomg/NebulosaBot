# Delta for Core Commands

## REMOVED Requirements

### Requirement: Sync command

(Reason: manual `/sync` is an orphaned operations surface. The command tree is synced in `setup_hook()` at boot; keeping a user-invocable global-sync command adds risk with no supported workflow. This removal is part of the S6 command-surface cleanup.)
(Migration: None — slash commands auto-register via `await tree.sync()` during startup. Operators needing a forced re-sync restart the process.)
