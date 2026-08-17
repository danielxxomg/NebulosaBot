"""Unit tests for bot.services.ticket_invariants — pure invariant helpers.

Covers the pure logic of the ticket invariant layer (B5 PR1). These
functions have NO Discord or DB side effects — they only validate state and
raise ``ValueError`` on invariant violations. They are wired into
``TicketService`` in PR2.
"""

from __future__ import annotations

import hashlib

import pytest

from bot.services.ticket_invariants import (
    check_can_add_note,
    check_can_claim,
    check_can_close,
    check_can_delete_note,
    check_can_edit_category,
    check_can_reopen,
    check_can_transfer,
    check_one_ticket_per_user_per_category,
    check_subticket_parent,
    compute_note_hash,
    is_duplicate_note,
)

# ===========================================================================
# compute_note_hash — SHA256 of normalized content
# ===========================================================================


class TestComputeNoteHash:
    """Verify compute_note_hash() normalizes then SHA256-hashes content."""

    def test_hashes_normalized_content(self) -> None:
        """compute_note_hash('Hello World') MUST equal sha256('hello world')."""
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert compute_note_hash("Hello World") == expected

    def test_strips_leading_trailing_whitespace(self) -> None:
        """Leading/trailing whitespace MUST be stripped before hashing."""
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert compute_note_hash("  hello world  ") == expected

    def test_lowercases_content(self) -> None:
        """Uppercase and lowercase of the same content MUST hash equally."""
        assert compute_note_hash("HELLO WORLD") == compute_note_hash("hello world")

    def test_collapses_internal_whitespace(self) -> None:
        """Runs of whitespace inside content MUST collapse to a single space."""
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert compute_note_hash("hello   world\t") == expected
        assert compute_note_hash("hello\nworld") == expected

    def test_different_content_yields_different_hash(self) -> None:
        """Distinct content MUST produce distinct hashes."""
        assert compute_note_hash("hello world") != compute_note_hash("goodbye world")

    def test_empty_string_hashes_to_sha256_of_empty(self) -> None:
        """Empty content MUST hash to sha256('')."""
        assert compute_note_hash("") == hashlib.sha256(b"").hexdigest()

    def test_returns_hex_string(self) -> None:
        """compute_note_hash() MUST return a hex digest string."""
        h = compute_note_hash("anything")
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# is_duplicate_note — hash membership within the dedup window
# ===========================================================================


class TestIsDuplicateNote:
    """Verify is_duplicate_note() detects a duplicate hash among recent notes."""

    def test_duplicate_hash_present_is_true(self) -> None:
        """A hash already in the recent set MUST be flagged duplicate."""
        h = compute_note_hash("hello world")
        assert is_duplicate_note(h, "authorA", [h], 2.0) is True

    def test_hash_not_in_set_is_false(self) -> None:
        """A hash absent from the recent set MUST NOT be flagged."""
        h = compute_note_hash("hello world")
        other = compute_note_hash("goodbye world")
        assert is_duplicate_note(h, "authorA", [other], 2.0) is False

    def test_empty_recent_set_is_false(self) -> None:
        """No recent notes in the window MUST mean no duplicate."""
        h = compute_note_hash("hello world")
        assert is_duplicate_note(h, "authorA", [], 2.0) is False

    def test_multiple_recent_hashes(self) -> None:
        """The check MUST scan a multi-hash recent set correctly."""
        target = compute_note_hash("note three")
        recent = [compute_note_hash("note one"), compute_note_hash("note two"), target]
        assert is_duplicate_note(target, "authorA", recent, 2.0) is True
        assert is_duplicate_note(compute_note_hash("note four"), "authorA", recent, 2.0) is False


# ===========================================================================
# check_can_claim — claim is valid only when open and unclaimed
# ===========================================================================


class TestCheckCanClaim:
    """Verify check_can_claim() allows open+unclaimed, rejects the rest."""

    def test_open_unclaimed_allowed(self) -> None:
        """Claim on an open ticket with no claimant MUST NOT raise."""
        check_can_claim("open", None)  # no exception

    def test_closed_rejected(self) -> None:
        """Claim on a closed ticket MUST raise ValueError."""
        with pytest.raises(ValueError, match="claim"):
            check_can_claim("closed", None)

    def test_already_claimed_rejected(self) -> None:
        """Claim on an already-claimed ticket MUST raise (no-overwrite)."""
        with pytest.raises(ValueError, match="claim"):
            check_can_claim("claimed", "userA")

    def test_open_but_claimant_set_rejected(self) -> None:
        """An open ticket with a stale claimant MUST ALSO be rejected."""
        with pytest.raises(ValueError, match="claim"):
            check_can_claim("open", "userA")


# ===========================================================================
# check_can_close — close is valid for open or claimed
# ===========================================================================


class TestCheckCanClose:
    """Verify check_can_close() allows open/claimed, rejects already-closed."""

    def test_open_allowed(self) -> None:
        check_can_close("open")  # no exception

    def test_claimed_allowed(self) -> None:
        check_can_close("claimed")  # no exception

    def test_closed_rejected(self) -> None:
        with pytest.raises(ValueError, match="close"):
            check_can_close("closed")


# ===========================================================================
# check_can_reopen — reopen is valid only for closed tickets
# ===========================================================================


class TestCheckCanReopen:
    """Verify check_can_reopen() allows closed, rejects open/claimed."""

    def test_closed_allowed(self) -> None:
        check_can_reopen("closed")  # no exception

    def test_open_rejected(self) -> None:
        with pytest.raises(ValueError, match="reopen"):
            check_can_reopen("open")

    def test_claimed_rejected(self) -> None:
        with pytest.raises(ValueError, match="reopen"):
            check_can_reopen("claimed")


# ===========================================================================
# check_can_transfer — transfer rejects same-user and missing target
# ===========================================================================


class TestCheckCanTransfer:
    """Verify check_can_transfer() allows reassign/claim-via-transfer, rejects same user."""

    def test_open_to_new_user_allowed(self) -> None:
        """Transfer of an open ticket to a new user MUST NOT raise (implicit claim)."""
        check_can_transfer("open", None, "userB")

    def test_claimed_reassign_allowed(self) -> None:
        """Transfer of a claimed ticket to a different user MUST NOT raise."""
        check_can_transfer("claimed", "userA", "userB")

    def test_same_user_rejected(self) -> None:
        """Transfer to the same already-claiming user MUST raise."""
        with pytest.raises(ValueError, match="same"):
            check_can_transfer("claimed", "userA", "userA")

    def test_missing_target_rejected(self) -> None:
        """Transfer with no target MUST raise."""
        with pytest.raises(ValueError, match="target"):
            check_can_transfer("claimed", "userA", None)

    def test_closed_rejected(self) -> None:
        """Transferring a closed ticket MUST raise (reopen first)."""
        with pytest.raises(ValueError, match="closed"):
            check_can_transfer("closed", None, "userB")


# ===========================================================================
# check_can_add_note — enforce the per-ticket note cap
# ===========================================================================


class TestCheckCanAddNote:
    """Verify check_can_add_note() enforces the 50-note cap."""

    def test_under_cap_allowed(self) -> None:
        check_can_add_note(30)  # no exception

    def test_just_under_cap_allowed(self) -> None:
        check_can_add_note(49)  # no exception

    def test_at_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="cap"):
            check_can_add_note(50)

    def test_over_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="cap"):
            check_can_add_note(51)

    def test_custom_cap(self) -> None:
        """A custom cap MUST be honored."""
        check_can_add_note(9, cap=10)  # ok
        with pytest.raises(ValueError, match="cap"):
            check_can_add_note(10, cap=10)


# ===========================================================================
# check_can_delete_note — author-only delete
# ===========================================================================


class TestCheckCanDeleteNote:
    """Verify check_can_delete_note() allows the author only."""

    def test_author_can_delete(self) -> None:
        check_can_delete_note("userA", "userA")  # no exception

    def test_non_author_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"owner|author"):
            check_can_delete_note("userA", "userB")


# ===========================================================================
# check_subticket_parent — parentId FK invariants
# ===========================================================================


def _parent_row(parent_id: str, *, parent_id_of_parent: str | None = None) -> dict:
    return {"id": parent_id, "guildId": "guildA", "parentId": parent_id_of_parent}


class TestCheckSubticketParent:
    """Verify check_subticket_parent() enforces existence, depth, self, guild."""

    def test_valid_parent_allowed(self) -> None:
        """A real parent in the same guild with no parentId MUST be accepted."""
        check_subticket_parent(_parent_row("p1"), "guildA", "guildA", current_id="c1")

    def test_missing_parent_rejected(self) -> None:
        """A missing parent row MUST raise ValueError."""
        with pytest.raises(ValueError, match=r"missing|not found|parent"):
            check_subticket_parent(None, "guildA", "guildA", current_id="c1")

    def test_self_parent_rejected(self) -> None:
        """A ticket referencing itself as parent MUST raise."""
        with pytest.raises(ValueError, match="self"):
            check_subticket_parent(_parent_row("t1"), "guildA", "guildA", current_id="t1")

    def test_depth_max_two_rejected(self) -> None:
        """A parent that already has a parentId MUST raise (depth limit)."""
        with pytest.raises(ValueError, match=r"depth|nested|sub"):
            check_subticket_parent(
                _parent_row("p1", parent_id_of_parent="g1"),
                "guildA",
                "guildA",
                current_id="c1",
            )

    def test_cross_guild_rejected(self) -> None:
        """A parent in a different guild MUST raise."""
        with pytest.raises(ValueError, match="guild"):
            check_subticket_parent(_parent_row("p1"), "guildA", "guildB", current_id="c1")


# ===========================================================================
# check_one_ticket_per_user_per_category — per-user-per-category limit
# ===========================================================================


class TestCheckOneTicketPerUserPerCategory:
    """Verify check_one_ticket_per_user_per_category() enforces the limit."""

    def test_user_with_open_ticket_blocked(self) -> None:
        """User with 1 open ticket in category MUST be blocked."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 1

        with pytest.raises(ValueError, match="already has an open ticket"):
            check_one_ticket_per_user_per_category("userA", "Support", None, count_fn)

    def test_user_with_claimed_ticket_blocked(self) -> None:
        """User with 1 claimed ticket in category MUST be blocked (claimed counts as open)."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 1

        with pytest.raises(ValueError, match="already has an open ticket"):
            check_one_ticket_per_user_per_category("userA", "Support", None, count_fn)

    def test_user_with_no_open_tickets_allowed(self) -> None:
        """User with 0 open tickets in category MUST NOT raise."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 0

        check_one_ticket_per_user_per_category("userA", "Support", None, count_fn)

    def test_subticket_skips_check(self) -> None:
        """Subticket (parent_id is not None) MUST skip the limit check."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 99  # would block if called

        check_one_ticket_per_user_per_category("userA", "Support", "parent-abc", count_fn)

    def test_null_category_id_skips_check(self) -> None:
        """Null category_id MUST skip the limit check."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 99  # would block if called

        check_one_ticket_per_user_per_category("userA", None, None, count_fn)

    def test_closed_ticket_frees_slot(self) -> None:
        """User with only closed tickets (count=0) MUST NOT be blocked."""

        def count_fn(_uid: str, _cid: str) -> int:
            return 0

        check_one_ticket_per_user_per_category("userA", "Support", None, count_fn)

    def test_count_fn_receives_user_and_category(self) -> None:
        """count_fn MUST be called with user_id and category_id."""
        calls: list[tuple[str, str]] = []

        def count_fn(uid: str, cid: str) -> int:
            calls.append((uid, cid))
            return 0

        check_one_ticket_per_user_per_category("userA", "Support", None, count_fn)
        assert calls == [("userA", "Support")]


# ===========================================================================
# check_can_edit_category — mod/admin authorization
# ===========================================================================


class TestCheckCanEditCategory:
    """Verify check_can_edit_category() gates by mod/admin role."""

    def test_mod_can_edit_category(self) -> None:
        """An actor with is_mod=True MUST be allowed to edit category."""
        ticket = {"id": "t1", "authorId": "userA", "status": "open"}
        check_can_edit_category("modUser", ticket, is_mod=True)

    def test_non_mod_author_denied(self) -> None:
        """The ticket author without mod role MUST be denied."""
        ticket = {"id": "t1", "authorId": "userA", "status": "open"}
        with pytest.raises(ValueError, match="Only moderators"):
            check_can_edit_category("userA", ticket, is_mod=False)

    def test_non_mod_non_author_denied(self) -> None:
        """A non-author, non-mod actor MUST be denied."""
        ticket = {"id": "t1", "authorId": "userA", "status": "open"}
        with pytest.raises(ValueError, match="Only moderators"):
            check_can_edit_category("userB", ticket, is_mod=False)

    def test_mod_can_edit_others_ticket(self) -> None:
        """A mod MUST be able to edit any ticket's category."""
        ticket = {"id": "t1", "authorId": "userA", "status": "claimed"}
        check_can_edit_category("modUser", ticket, is_mod=True)


# ===========================================================================
# parse_ticket_ref — /reopen ticket reference parser (PR2, TI-029/TI-037)
# ===========================================================================


def test_parse_ticket_ref_strip_ticket_prefix_hash() -> None:
    """'ticket:#0003' parses to ticket number 3."""
    from bot.services.ticket_invariants import parse_ticket_ref

    ref = parse_ticket_ref("ticket:#0003")
    assert ref is not None
    assert ref.number == 3
    assert ref.uuid is None


def test_parse_ticket_ref_hash_number() -> None:
    """'#0003' parses to ticket number 3."""
    from bot.services.ticket_invariants import parse_ticket_ref

    ref = parse_ticket_ref("#0003")
    assert ref is not None
    assert ref.number == 3


def test_parse_ticket_ref_bare_number() -> None:
    """'0003' parses to ticket number 3."""
    from bot.services.ticket_invariants import parse_ticket_ref

    ref = parse_ticket_ref("0003")
    assert ref is not None
    assert ref.number == 3


def test_parse_ticket_ref_uuid() -> None:
    """A UUID parses to ref.uuid set, number None."""
    from bot.services.ticket_invariants import parse_ticket_ref

    uuid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ref = parse_ticket_ref(uuid_str)
    assert ref is not None
    assert ref.uuid == uuid_str
    assert ref.number is None


def test_parse_ticket_ref_uuid_with_ticket_prefix() -> None:
    """'ticket:<uuid>' strips prefix and parses as UUID."""
    from bot.services.ticket_invariants import parse_ticket_ref

    uuid_str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ref = parse_ticket_ref(f"ticket:{uuid_str}")
    assert ref is not None
    assert ref.uuid == uuid_str


def test_parse_ticket_ref_empty_returns_none() -> None:
    """Empty / whitespace string returns None (caller falls back to channel)."""
    from bot.services.ticket_invariants import parse_ticket_ref

    assert parse_ticket_ref("") is None
    assert parse_ticket_ref("   ") is None


def test_parse_ticket_ref_garbage_returns_none() -> None:
    """Non-number, non-UUID strings return None (caller surfaces bad-ref error)."""
    from bot.services.ticket_invariants import parse_ticket_ref

    assert parse_ticket_ref("not-a-ticket") is None
    assert parse_ticket_ref("ticket:hello") is None


# ===========================================================================
# Repair authority — one mod role; owner/Admin same-guild bypass; cross-guild
# denied; deletion actor informational only; operator read-only diagnosis;
# explicit targeted audited grant for global mutation (product-artifact-audit PR3)
# ===========================================================================


def _authority(**overrides: object) -> object:
    """Build a :class:`RepairAuthority` with sane same-guild defaults."""
    from bot.services.ticket_invariants import RepairAuthority

    defaults: dict[str, object] = {
        "actor_id": "actor-1",
        "guild_id": "guildA",
        "target_guild_id": "guildA",
        "is_guild_owner": False,
        "is_administrator": False,
        "has_mod_role": False,
        "is_bot_owner": False,
        "deletion_actor": False,
    }
    defaults.update(overrides)
    return RepairAuthority(**defaults)


def _grant(**overrides: object) -> object:
    """Build a :class:`GlobalMutationGrant` matching the default authority."""
    from bot.services.ticket_invariants import GlobalMutationGrant

    defaults: dict[str, object] = {
        "actor_id": "actor-1",
        "scope": "global",
        "target_guild_id": "guildA",
        "reason": "maintenance: channel delete sweep",
        "confirmed": True,
    }
    defaults.update(overrides)
    return GlobalMutationGrant(**defaults)


def _evaluate(authority: object, grant: object | None = None) -> object:
    from bot.services.ticket_invariants import evaluate_repair_authority

    return evaluate_repair_authority(authority, global_grant=grant)


class TestRepairAuthorityGuildScope:
    """Verify guild-scoped authority: one mod role; owner/Admin same-guild bypass only."""

    def test_mod_role_same_guild_allowed(self) -> None:
        """The canonical configured mod role authorizes its own guild only."""
        decision = _evaluate(_authority(has_mod_role=True))
        assert decision.allowed is True
        assert decision.scope == "guild"

    def test_guild_owner_same_guild_bypass(self) -> None:
        """Guild owner bypasses the mod-role check inside their own guild."""
        decision = _evaluate(_authority(is_guild_owner=True))
        assert decision.allowed is True

    def test_administrator_same_guild_bypass(self) -> None:
        """Discord Administrator bypasses the mod-role check inside their own guild."""
        decision = _evaluate(_authority(is_administrator=True))
        assert decision.allowed is True

    def test_mod_role_cross_guild_denied(self) -> None:
        """A mod of guild A targeting guild B is denied."""
        decision = _evaluate(_authority(has_mod_role=True, target_guild_id="guildB"))
        assert decision.allowed is False
        assert decision.reason == "cross_guild_denied"

    def test_owner_cross_guild_denied(self) -> None:
        """A guild owner targeting another guild is denied (no silent global bypass)."""
        decision = _evaluate(_authority(is_guild_owner=True, target_guild_id="guildB"))
        assert decision.allowed is False
        assert decision.reason == "cross_guild_denied"

    def test_admin_cross_guild_denied(self) -> None:
        """An administrator targeting another guild is denied."""
        decision = _evaluate(_authority(is_administrator=True, target_guild_id="guildB"))
        assert decision.allowed is False
        assert decision.reason == "cross_guild_denied"

    def test_plain_user_denied(self) -> None:
        """An actor with no role, owner, admin, or operator authority is denied."""
        decision = _evaluate(_authority())
        assert decision.allowed is False
        assert decision.reason == "insufficient_authority"


class TestRepairAuthorityDeletionActor:
    """Verify the channel-deletion actor is informational only and never authorizes."""

    def test_deletion_actor_alone_denied(self) -> None:
        """A deletion actor with no other authority is denied."""
        decision = _evaluate(_authority(deletion_actor=True))
        assert decision.allowed is False

    def test_deletion_actor_does_not_upgrade_authority(self) -> None:
        """Being the deletion actor adds nothing to an otherwise plain user."""
        decision = _evaluate(_authority(deletion_actor=True, has_mod_role=False))
        assert decision.allowed is False
        assert decision.reason == "insufficient_authority"

    def test_deletion_actor_mod_still_guild_scoped(self) -> None:
        """A deletion actor who is also a mod is authorized only in their guild."""
        allowed = _evaluate(_authority(deletion_actor=True, has_mod_role=True))
        assert allowed.allowed is True
        denied = _evaluate(_authority(deletion_actor=True, has_mod_role=True, target_guild_id="guildB"))
        assert denied.allowed is False


class TestRepairAuthorityOperator:
    """Verify bot owner gets read-only diagnosis; global mutation needs an explicit grant."""

    def test_operator_diagnosis_read_only_without_grant(self) -> None:
        """A bot owner without an explicit grant is denied mutation (read-only diagnosis)."""
        decision = _evaluate(_authority(is_bot_owner=True, guild_id=None))
        assert decision.allowed is False
        assert decision.reason == "operator_mutation_requires_grant"

    def test_operator_with_grant_allowed(self) -> None:
        """An explicit, targeted, confirmed, audited grant authorizes global mutation."""
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None),
            _grant(),
        )
        assert decision.allowed is True
        assert decision.scope == "global"
        assert decision.reason  # the auditable reason is carried through

    def test_grant_requires_confirmation(self) -> None:
        """An unconfirmed grant never authorizes mutation."""
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None),
            _grant(confirmed=False),
        )
        assert decision.allowed is False

    def test_grant_requires_non_empty_reason(self) -> None:
        """A grant with an empty/blank reason never authorizes mutation."""
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None),
            _grant(reason=""),
        )
        assert decision.allowed is False

    def test_grant_requires_matching_actor(self) -> None:
        """A grant naming a different actor never authorizes this actor."""
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None, actor_id="actor-2"),
            _grant(actor_id="actor-1"),
        )
        assert decision.allowed is False

    def test_grant_requires_matching_target(self) -> None:
        """A grant targeting a different guild never authorizes this target."""
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None, target_guild_id="guildB"),
            _grant(target_guild_id="guildA"),
        )
        assert decision.allowed is False

    def test_grant_requires_global_scope(self) -> None:
        """A confirmed grant whose scope is 'guild' MUST NOT authorize global mutation.

        The mutation gate is the evaluator itself: a scope="guild" grant is a
        denial with a precise reason, never an implicit global bypass.
        """
        decision = _evaluate(
            _authority(is_bot_owner=True, guild_id=None),
            _grant(scope="guild"),
        )
        assert decision.allowed is False
        assert decision.reason == "grant_scope_mismatch"

    def test_grant_ignored_for_non_operator(self) -> None:
        """A grant cannot upgrade a plain non-operator actor."""
        decision = _evaluate(_authority(), _grant())
        assert decision.allowed is False
