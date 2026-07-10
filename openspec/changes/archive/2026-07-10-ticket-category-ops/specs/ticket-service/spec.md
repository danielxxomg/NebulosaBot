# Delta for Ticket Service

## ADDED Requirements

### Requirement: Ticket creation per-user-per-category guard

`create_ticket()` SHALL enforce a one-open-ticket-per-user-per-category limit before inserting a new ticket. An open ticket is one with status `open` or `claimed`. The guard MUST be skipped when `parentId` is not None (subticket carve-out) or when `categoryId` is null (unlimited uncategorized tickets). On limit violation, `ValueError` MUST be raised.

#### Scenario: Second ticket in same category blocked

- GIVEN userA has an open ticket in category "Support" (status=open)
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support")` is called
- THEN `ValueError` is raised (one open ticket per user per category)

#### Scenario: Ticket in different category allowed

- GIVEN userA has an open ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Billing")` is called
- THEN a new ticket is created successfully

#### Scenario: Closed ticket frees the slot

- GIVEN userA has a closed ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support")` is called
- THEN a new ticket is created successfully

#### Scenario: Subticket bypasses limit

- GIVEN userA has an open ticket in category "Support"
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId="Support", parentId=abc)` is called
- THEN a subticket is created successfully (limit skipped)

#### Scenario: Null categoryId bypasses limit

- GIVEN userA has an open ticket with categoryId=null
- WHEN `create_ticket(guildId=G, authorId=userA, categoryId=null)` is called
- THEN a new ticket is created successfully (limit skipped)

### Requirement: Edit ticket category

`TicketService.edit_ticket_category(ticket_id, new_category_id, *, channel, actor_id, is_mod=False)` MUST update `categoryId` in the database and rename the ticket channel via `sanitize_channel_name()`. The method is the security boundary: it MUST call `check_can_edit_category(actor_id, ticket, is_mod=is_mod)` BEFORE any DB mutation (the view re-validates UX but the service is authoritative; remote callers without the view must still be gated). The method MUST reject edit on a closed ticket (`edit_category` is valid only for `open`/`claimed`; closed tickets must be reopened first) by raising `ValueError`. The method MUST call `check_one_ticket_per_user_per_category(author_id, new_category_id, None, count_fn)` for the ticket's author against the NEW category BEFORE the DB update, counting the author's other `open`/`claimed` tickets in that category and excluding the ticket being edited from the count by passing `exclude_ticket_id=ticket_id` to `count_user_open_tickets_in_category(guild_id, author_id, new_category_id, exclude_ticket_id=ticket_id)` (`new_category_id` is non-null in this path); on violation it MUST raise `ValueError`. If the channel rename raises `discord.HTTPException` (rate limit), the system SHALL log a warning and proceed — the DB update MUST still succeed. The method MUST write an `audit_log` row on success.

#### Scenario: Edit category updates DB and renames channel

- GIVEN ticket #5 with categoryId="Support" and channel name "support-daniel-5"
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called
- THEN categoryId is "Billing" in DB and channel is renamed to "billing-daniel-5"

#### Scenario: Channel rename failure does not block DB update

- GIVEN ticket #5 and Discord rate limit active
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called and channel rename raises `HTTPException`
- THEN categoryId is updated to "Billing" in DB and a warning is logged

#### Scenario: Audit row written on success

- GIVEN a valid category edit
- WHEN `edit_ticket_category` succeeds
- THEN an audit row (action=edit_category, outcome=success) is written

#### Scenario: Service enforces mod permission

- GIVEN a ticket and an actor that lacks mod/admin
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=userA, is_mod=False)` is called
- THEN the operation is rejected before any DB mutation and an audit row (outcome=denied) is written

#### Scenario: Edit on closed ticket rejected

- GIVEN ticket #5 with status="closed"
- WHEN `edit_ticket_category(5, "Billing", channel=..., actor_id=modUser)` is called
- THEN `ValueError` is raised and no DB mutation happens

#### Scenario: Edit into category where author has open ticket rejected

- GIVEN ticket #7 (author=userA, category="Support") and userA already has another open ticket in "Billing"
- WHEN `edit_ticket_category(7, "Billing", channel=..., actor_id=modUser)` is called
- THEN `ValueError` is raised (one open ticket per user per category) and no DB mutation happens

#### Scenario: Edit into empty category allowed

- GIVEN ticket #7 (author=userA) and userA has no open/claimed tickets in "Billing"
- WHEN `edit_ticket_category(7, "Billing", channel=..., actor_id=modUser)` is called
- THEN categoryId is updated to "Billing" and the channel is renamed

#### Scenario: Edit excludes the edited ticket from the count

- GIVEN ticket #7 (author=userA, category="Billing") is the author's only open ticket in "Billing" and is being edited to a new category
- WHEN `edit_ticket_category(7, "Support", channel=..., actor_id=modUser)` is called
- THEN the count for "Billing" excludes ticket #7 and no false violation is raised

#### Scenario: Same-category no-op edit does not self-block

- GIVEN ticket #7 (author=userA, category="Support") is the author's only open ticket in "Support"
- WHEN `edit_ticket_category(7, "Support", channel=..., actor_id=modUser)` is called (no-op same category)
- THEN `count_user_open_tickets_in_category(G, userA, "Support", exclude_ticket_id=7)` is called, ticket #7 is excluded, the count is 0, and no `ValueError` is raised; `categoryId` remains "Support"
