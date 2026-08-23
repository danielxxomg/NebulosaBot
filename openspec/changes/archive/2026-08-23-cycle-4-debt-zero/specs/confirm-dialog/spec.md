# Delta for Confirm Dialog

## ADDED Requirements

### Requirement: Ephemeral dialog, permanent outcome

`ConfirmCancelView` MUST always render ephemerally at every call site. When the wrapped action belongs to a category whose results are permanent (mod-action per the ephemeral-standard), the calling command MUST deliver the final outcome as a permanent channel message; the ephemeral dialog MUST NOT double as the permanent record. Cancel and timeout outcomes remain ephemeral in all cases.

#### Scenario: Moderation dialog outcome split

- GIVEN `/kick` shows the view and the moderator confirms
- WHEN execution finishes
- THEN a permanent channel embed carries the result and the ephemeral dialog does not serve as the permanent record

#### Scenario: Cancel and timeout stay ephemeral

- GIVEN the view is cancelled or times out
- WHEN feedback is delivered
- THEN it is ephemeral, visible only to the invoking user
