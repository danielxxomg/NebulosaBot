# Design: hygiene-and-qa-standardization

## Context
Ref-only git hygiene at aff623d. No source or spec changes. Proposal covers all decisions.
Exploration verified: 3 locals contained (patch-id), 2 remotes duplicate 8cb5674 superseded, ad41f3f==a306384, f197fbc 3-parent stash.

## Decision
Approach 2 archived-tag-then-delete. Pre-flight gh pr list for pr2a/pr2b. Tag baseline aff623d, then delete refs.

## Consequences
- No architecture change.
- No spec delta — 63 active specs verified latest, 7 gates standardized.
