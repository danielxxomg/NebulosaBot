# Delta for Brand Tokens

## ADDED Requirements

### Requirement: Brand token contract tests

The system MUST have contract tests proving all 6 brand tokens (PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO) are importable from `bot/utils/brand.py` with correct hex values. Tests MUST also prove no production module uses hardcoded hex color literals instead of brand tokens.

#### Scenario: all 6 tokens are importable

- GIVEN the `bot.utils.brand` module
- WHEN each of PRIMARY, ACCENT, SUCCESS, WARNING, ERROR, INFO is imported
- THEN no ImportError is raised

#### Scenario: token hex values match palette spec

- GIVEN the brand module constants
- WHEN their hex values are inspected
- THEN PRIMARY is `#9B5DE5`, ACCENT is `#A855F7`, SUCCESS is `#10B981`, WARNING is `#F59E0B`, ERROR is `#EF4444`, INFO is `#8B5CF6`

#### Scenario: no hardcoded hex in production code

- GIVEN all files under `bot/` (excluding `brand.py`)
- WHEN a regex scan for 6-digit hex literals (`#[0-9A-Fa-f]{6}`) is performed
- THEN zero matches are found in embed color assignments
