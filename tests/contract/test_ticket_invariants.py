"""Contract tests for the ticket invariant layer (B5).

One pytest per ScenarioID TI-001..TI-038, mirroring the contract table in
``openspec/changes/ticket-invariant-layer/design.md`` and the TS mirror in
``dashboard/__tests__/contract/ticket-invariants.test.ts`` (PR3). The
ScenarioID is encoded in every test name so drift between the two suites is
reviewable and CI-catchable.

PR1 scope: the PURE-LOGIC scenarios call the invariant helpers in
``bot.services.ticket_invariants`` and pass now. Scenarios that require the
service/cog/dashboard integration layer (audit rows written by the service,
permission matrix wired into buttons, dashboard reopen guidance, paginated
audit panel) are marked ``pytest.skip`` and are unskipped by PR2/PR3 as that
wiring lands.
"""

from __future__ import annotations

import pytest

from bot.services.ticket_invariants import (
    check_can_add_note,
    check_can_claim,
    check_can_close,
    check_can_delete_note,
    check_can_reopen,
    check_can_transfer,
    check_subticket_parent,
    compute_note_hash,
    is_duplicate_note,
)

# Reason recorded for every skipped integration scenario in this slice.
PR2_SERVICE_WIRING = "PR2 wires ticket_service/cog audit + permission gates"
PR2_COG_WIRING = "PR2 wires /reopen ticket-ref + button gates into TicketsCog"
PR3_DASHBOARD = "PR3 implements the dashboard reopen guidance + audit panel"


# ---------------------------------------------------------------------------
# Fixture — a candidate parent ticket row
# ---------------------------------------------------------------------------


def _parent_row(parent_id: str = "parent-1", *, parent_of_parent: str | None = None) -> dict:
    """Return a camelCase parent ticket row for subticket invariant scenarios."""
    return {"id": parent_id, "guildId": "guildA", "parentId": parent_of_parent}


# ===========================================================================
# TI-001..TI-007 — status state machine + claim no-overwrite  (PURE, PASS)
# ===========================================================================


def test_ti001_open_to_claimed() -> None:
    """TI-001: GIVEN open WHEN claim THEN status claimed, claimedBy set, audit success.

    The pure invariant: claim is valid for open+unclaimed, so the service
    (PR2) will set status='claimed' and write an audit success row.
    """
    check_can_claim("open", None)  # claim allowed → service proceeds to claimed


def test_ti002_open_to_closed() -> None:
    """TI-002: GIVEN open WHEN close THEN status closed, audit success."""
    check_can_close("open")


def test_ti003_claimed_to_closed() -> None:
    """TI-003: GIVEN claimed WHEN close THEN status closed, audit success."""
    check_can_close("claimed")


def test_ti004_closed_to_open() -> None:
    """TI-004: GIVEN closed WHEN reopen THEN new channel, status open."""
    check_can_reopen("closed")


def test_ti005_closed_claim_denied() -> None:
    """TI-005: GIVEN closed WHEN claim THEN denied + audit."""
    with pytest.raises(ValueError, match=r"claim"):
        check_can_claim("closed", None)


@pytest.mark.parametrize("status", ["open", "claimed"])
def test_ti006_non_closed_reopen_denied(status: str) -> None:
    """TI-006: GIVEN open/claimed WHEN reopen THEN denied, no channel."""
    with pytest.raises(ValueError, match=r"reopen"):
        check_can_reopen(status)


@pytest.mark.parametrize("claimed_by", ["userA", "userB"])
def test_ti007_claim_no_overwrite(claimed_by: str) -> None:
    """TI-007: GIVEN claimed by A WHEN B or A claims THEN denied, A preserved."""
    with pytest.raises(ValueError, match=r"claim"):
        check_can_claim("claimed", claimed_by)


# ===========================================================================
# TI-008..TI-010 — transfer invariants  (PURE, PASS)
# ===========================================================================


def test_ti008_transfer_open_claims() -> None:
    """TI-008: GIVEN open null claim WHEN transfer B THEN claimedBy=B, status=claimed."""
    check_can_transfer("open", None, "userB")


def test_ti009_transfer_reassigns() -> None:
    """TI-009: GIVEN claimed A WHEN transfer B THEN claimedBy=B, status stays claimed."""
    check_can_transfer("claimed", "userA", "userB")


def test_ti010_transfer_same_user_denied() -> None:
    """TI-010: GIVEN claimed A WHEN transfer A THEN denied + audit."""
    with pytest.raises(ValueError, match=r"same"):
        check_can_transfer("claimed", "userA", "userA")


# ===========================================================================
# TI-011..TI-015 — parentId FK invariants  (PURE, PASS)
# ===========================================================================


def test_ti011_subticket_valid() -> None:
    """TI-011: GIVEN parent exists same guild no parentId WHEN create child THEN success."""
    check_subticket_parent(_parent_row("parent-1"), "guildA", "guildA", current_id="child-1")


def test_ti012_parent_missing_denied() -> None:
    """TI-012: GIVEN no parent row WHEN create child THEN denied."""
    with pytest.raises(ValueError, match=r"parent"):
        check_subticket_parent(None, "guildA", "guildA", current_id="child-1")


def test_ti013_self_parent_denied() -> None:
    """TI-013: GIVEN parentId==id WHEN create child THEN denied."""
    with pytest.raises(ValueError, match=r"self"):
        check_subticket_parent(_parent_row("t-1"), "guildA", "guildA", current_id="t-1")


def test_ti014_depth_denied() -> None:
    """TI-014: GIVEN parent already a child WHEN create child THEN denied (depth max 2)."""
    deepest = _parent_row("parent-1", parent_of_parent="grandparent-1")
    with pytest.raises(ValueError, match=r"depth|nested|sub"):
        check_subticket_parent(deepest, "guildA", "guildA", current_id="child-1")


def test_ti015_cross_guild_parent_denied() -> None:
    """TI-015: GIVEN parent guild A WHEN child guild B THEN denied."""
    with pytest.raises(ValueError, match=r"guild"):
        check_subticket_parent(_parent_row("parent-1"), "guildA", "guildB", current_id="child-1")


# ===========================================================================
# TI-016..TI-018 — note dedup  (PURE, PASS)
# ===========================================================================


def test_ti016_note_dedup_denied() -> None:
    """TI-016: GIVEN same-author note 1s ago WHEN normalized duplicate THEN denied."""
    original = compute_note_hash("Hello World")
    incoming = compute_note_hash("  hello world  ")  # cosmetic variant → same hash
    assert original == incoming
    assert is_duplicate_note(incoming, "authorA", [original], 2.0) is True


def test_ti017_note_outside_window_allowed() -> None:
    """TI-017: GIVEN same-author note 5s ago WHEN same content THEN allowed.

    The 5s-ago note falls outside the 2s window, so the upstream
    get_recent_notes_for_dedup query returns [] and is_duplicate_note is False.
    """
    h = compute_note_hash("hello")
    assert is_duplicate_note(h, "authorA", [], 2.0) is False


def test_ti018_note_different_author_allowed() -> None:
    """TI-018: GIVEN author A note 1s ago WHEN author B same content THEN allowed.

    Dedup is per-author: the author-scoped recent set for author B is empty,
    so the duplicate check is False.
    """
    existing = compute_note_hash("hello")
    incoming = compute_note_hash("hello")
    # author B sees only their own notes (none) → no duplicate
    assert is_duplicate_note(incoming, "authorB", [], 2.0) is False
    assert is_duplicate_note(incoming, "authorA", [existing], 2.0) is True


# ===========================================================================
# TI-019..TI-021 — audit logging  (INTEGRATION: PR2 service wiring)
# ===========================================================================


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti019_audit_every_success() -> None:
    """TI-019: GIVEN every op succeeds THEN one success audit row each."""
    raise AssertionError("Unskipped by PR2: claim/close/reopen/transfer/subticket/note CRUD → audit success")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti020_audit_every_denied() -> None:
    """TI-020: GIVEN permission/invariant fail THEN denied audit row with reason."""
    raise AssertionError("Unskipped by PR2: denied path inserts audit row with reason")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti021_audit_guild_scope() -> None:
    """TI-021: GIVEN audit rows guild A+B WHEN query A THEN only A rows."""
    raise AssertionError("Unskipped by PR2: get_audit_rows guild-scoped via .eq(guildId)")


# ===========================================================================
# TI-022..TI-028 — permission matrix  (PR2 wires check_actor_permission + gates)
# ===========================================================================


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti022_create_any_user() -> None:
    """TI-022: GIVEN user/admin/mod/author WHEN create THEN all allowed."""
    raise AssertionError("Unskipped by PR2: permission matrix (create=any user)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti023_claim_permission_matrix() -> None:
    """TI-023: GIVEN admin/mod/author/user WHEN claim THEN admin+mod allowed; others denied."""
    raise AssertionError("Unskipped by PR2: permission matrix (claim=mod)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti024_close_permission_matrix() -> None:
    """TI-024: GIVEN admin/mod/author/user WHEN close THEN admin/mod/author allowed; user denied."""
    raise AssertionError("Unskipped by PR2: permission matrix (close=author or mod)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti025_reopen_permission_matrix() -> None:
    """TI-025: GIVEN admin/mod/author/user WHEN reopen THEN admin+mod allowed; others denied."""
    raise AssertionError("Unskipped by PR2: permission matrix (reopen=mod)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti026_transfer_permission_matrix() -> None:
    """TI-026: GIVEN admin/mod/author/user WHEN transfer THEN admin only."""
    raise AssertionError("Unskipped by PR2: permission matrix (transfer=admin)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti027_staff_ops_permission_matrix() -> None:
    """TI-027: GIVEN note CRUD/subticket WHEN admin/mod/author/user THEN admin+mod allowed."""
    raise AssertionError("Unskipped by PR2: permission matrix (subticket/notes=admin or mod)")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti028_audit_view_admin_only() -> None:
    """TI-028: GIVEN admin/mod/author/user WHEN view audit THEN admin only."""
    raise AssertionError("Unskipped by PR2: permission matrix (audit view=admin only)")


# ===========================================================================
# TI-029..TI-030 — drift: reopen by number / category gate
# ===========================================================================


@pytest.mark.skip(reason=PR2_COG_WIRING)
def test_ti029_reopen_by_number() -> None:
    """TI-029: GIVEN closed ticket WHEN /reopen ticket:#0003 THEN resolves by number."""
    raise AssertionError("Unskipped by PR2: /reopen ticket_ref parses #0003 → get_ticket_by_number")


@pytest.mark.skip(reason=PR3_DASHBOARD)
def test_ti030_reopen_no_category_error() -> None:
    """TI-030: GIVEN no ticketCategoryId WHEN dashboard reopen THEN error, no modal."""
    raise AssertionError("Unskipped by PR3: getReopenGuidance rejects missing ticketCategoryId")


# ===========================================================================
# TI-031..TI-032 — note cap + delete ownership  (PURE cap logic PASS; UI skip in PR3)
# ===========================================================================


def test_ti031_note_cap() -> None:
    """TI-031: GIVEN 50 notes WHEN add note THEN denied (cap reached). UI disabled in PR3.

    The pure rule: at/over the cap it is rejected, under the cap it is allowed
    (so the dashboard, PR3, can disable the form and the service, PR2, can rely
    on the same invariant).
    """
    with pytest.raises(ValueError, match=r"cap"):
        check_can_add_note(50)  # at cap → service rejects; dashboard disables the form (PR3)
    check_can_add_note(30)  # under cap → no exception (companion assertion, same scenario)


def test_ti032_note_delete_owner_only() -> None:
    """TI-032: GIVEN note by A WHEN B deletes THEN denied. UI author-only in PR3.

    The pure rule: only the note's author may delete it.
    """
    with pytest.raises(ValueError, match=r"owner|author"):
        check_can_delete_note("userA", "userB")
    check_can_delete_note("userA", "userA")  # author → no exception (companion assertion)


# ===========================================================================
# TI-033..TI-038 — drift: guild scope, action view, legacy reopen, audit panel
# ===========================================================================


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti033_guild_scope() -> None:
    """TI-033: GIVEN ticket/note/audit guild B WHEN guild A acts/queries THEN no leak."""
    raise AssertionError("Unskipped by PR2: every service query MUST filter by guildId")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti034_note_under_cap() -> None:
    """TI-034: GIVEN ticket #5 has 30 notes WHEN author adds note THEN persisted, audit success."""
    raise AssertionError("Unskipped by PR2: create_note under cap persists + audits")


@pytest.mark.skip(reason=PR2_SERVICE_WIRING)
def test_ti035_author_delete_own() -> None:
    """TI-035: GIVEN note by userA WHEN userA deletes THEN deleted, audit success."""
    raise AssertionError("Unskipped by PR2: delete note by author + audit success")


@pytest.mark.skip(reason=PR2_COG_WIRING)
def test_ti036_action_view_render() -> None:
    """TI-036: GIVEN new ticket channel WHEN ticket opened THEN embed + claim/close buttons."""
    raise AssertionError("Unskipped by PR2: action view embed with gated claim/close buttons")


@pytest.mark.skip(reason=PR2_COG_WIRING)
def test_ti037_reopen_noarg_legacy() -> None:
    """TI-037: GIVEN just-closed ticket, channel exists WHEN /reopen (no arg) THEN resolves by channel."""
    raise AssertionError("Unskipped by PR2: legacy channel-scoped reopen within 5s window")


@pytest.mark.skip(reason=PR3_DASHBOARD)
def test_ti038_audit_paginated() -> None:
    """TI-038: GIVEN 200 audit rows WHEN admin visits audit tab THEN paginated rows newest-first."""
    raise AssertionError("Unskipped by PR3: AuditPanel paginates get_audit_rows(limit, offset)")
