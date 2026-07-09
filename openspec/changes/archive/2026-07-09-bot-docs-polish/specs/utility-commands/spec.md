# Delta for Utility Commands

## MODIFIED Requirements

### Requirement: Avatar command

The `/avatar` command MUST display the target user's avatar as a full-size embed image using `set_image`, not a thumbnail. The avatar URL SHOULD include `?size=1024` for guaranteed high resolution.

(Previously: used `set_thumbnail` which rendered at ~80px)

#### Scenario: Self avatar

- GIVEN a member invokes `/avatar` without a target
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose image is the invoking member's avatar URL

#### Scenario: Mentioned member avatar

- GIVEN a member invokes `/avatar @member`
- WHEN the command executes
- THEN the bot SHALL reply with an embed whose image is the mentioned member's avatar URL

#### Scenario: Large display size

- GIVEN the avatar URL is constructed
- WHEN the embed is built
- THEN the URL SHALL include `?size=1024` and `set_image` SHALL be used (not `set_thumbnail`)
