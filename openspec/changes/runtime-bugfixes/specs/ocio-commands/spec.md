# Delta for Ocio Commands

## MODIFIED Requirements

### Requirement: Banana command

The `/banana` command MUST reply with a banana image and a random measurement between 2 and 30 centimeters. The image asset MUST be loaded from `assets/images/banana.webp`.

#### Scenario: Normal banana

- GIVEN a member invokes `/banana` in a guild or DM
- WHEN the command executes
- THEN the bot SHALL reply with an embed containing a banana image attachment and a measurement in the range [2, 30] cm
- AND the image is loaded from `assets/images/banana.webp`

#### Scenario: Missing image asset

- GIVEN the banana image asset is missing at `assets/images/banana.webp`
- WHEN a member invokes `/banana`
- THEN the bot SHALL reply with an error embed indicating the image is unavailable

(Previously: Asset path was `banana.png` (root) or `assets/images/banana.png`)
