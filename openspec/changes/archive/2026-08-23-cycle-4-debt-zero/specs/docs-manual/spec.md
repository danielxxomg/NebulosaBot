# Delta for Docs Manual

## ADDED Requirements

### Requirement: AGENTS.md V3 rule slots

`AGENTS.md` MUST be updated to V3 with exactly these slot additions, each citing an enforceable pattern: Architecture gains the `cache_key(guild_id, entity)` mandate (all new cache keys MUST use it so keys are guild-scoped); Database gains the `IF NOT EXISTS` mandate for migration DDL; Discord.py gains two rules — `t()` localization is mandatory in cogs (no user-facing hardcoded strings) and `can_check("<perm>")` strict matrix gating is required on all matrix-gated commands; Anti-patterns gains matching ❌ rows for each new rule. The title/version marker MUST become `V3`. The "GGA Review Discipline" section MUST be preserved byte-identical. V3 MUST NOT land while the tree violates any of its new rules (docs follow code).

#### Scenario: V3 slots present

- GIVEN AGENTS.md at V3
- WHEN the Architecture, Database, and Discord.py sections are inspected
- THEN each contains its mandated rule (cache_key, IF NOT EXISTS, t(), can_check) and Anti-patterns contains the matching ❌ rows

#### Scenario: GGA block byte-identical

- GIVEN the pre-change GGA Review Discipline text is retained as reference
- WHEN the V3 file's GGA section is compared
- THEN it is byte-identical to the pre-change text (no edits, no reflow)

#### Scenario: Docs land only when true in tree

- GIVEN any V3 rule is still violated by the codebase
- WHEN the V3 docs change is proposed for merge
- THEN it is deferred until the tree conforms to every new rule
