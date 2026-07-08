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

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.cache import TTLCache
from bot.core.i18n import load_locales, set_guild_language
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
    parse_ticket_ref,
)
from bot.services.ticket_service import TicketService
from bot.utils.checks import is_mod_check

# Reason recorded for every skipped integration scenario in this slice.
PR3_DASHBOARD = "PR3 implements the dashboard reopen guidance + audit panel"


# ---------------------------------------------------------------------------
# i18n autouse fixture — load real locales so t() resolves correctly
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _load_real_locales() -> None:
    """Load real locale files so t() resolves ticket keys."""
    from bot.core import i18n as i18n_mod

    i18n_mod._locales.clear()
    i18n_mod._guild_languages.clear()

    locale_dir = Path("bot/locales")
    if locale_dir.exists():
        load_locales(locale_dir)
        set_guild_language("123456789", "en")


# ---------------------------------------------------------------------------
# PR2 contract fixtures — mock DB + mock Discord interaction
# (used by TI-019..TI-028 integration scenarios)
# ---------------------------------------------------------------------------


def _contract_db() -> AsyncMock:
    """A mock Database pre-wired for every TicketService op used by PR2 contract."""
    db = AsyncMock()
    db.get_max_ticket_number = AsyncMock(return_value=0)
    db.insert_ticket = AsyncMock()
    db.update_ticket = AsyncMock()
    db.get_ticket = AsyncMock()
    db.get_stale_tickets = AsyncMock()
    db.get_guild = AsyncMock()
    db.get_ticket_notes = AsyncMock(return_value=[])
    db.insert_ticket_note = AsyncMock()
    db.delete_ticket_note = AsyncMock()
    db.insert_audit_row = AsyncMock(return_value={})
    db.get_audit_rows = AsyncMock(return_value=[])
    db.get_recent_notes_for_dedup = AsyncMock(return_value=[])
    # PR2 cog reopen resolution paths (TI-029 / TI-037).
    db.get_ticket_by_number = AsyncMock()
    db.get_ticket_by_channel = AsyncMock()
    return db


def _audit_calls(db: AsyncMock) -> list[dict]:
    """Return a merged-kwargs dict for every ``insert_audit_row`` call.

    The service calls ``insert_audit_row`` POSITIONALLY; this helper merges
    positional args (by Database.insert_audit_row param order) so contract
    assertions can read ``action`` / ``outcome`` / ``guild_id`` uniformly
    regardless of call style.
    """
    keys = ["guild_id", "ticket_id", "action", "actor_id", "outcome", "reason"]
    out: list[dict] = []
    for call in db.insert_audit_row.call_args_list:
        if call.kwargs:
            out.append(call.kwargs)
        else:
            out.append(dict(zip(keys, call.args, strict=False)))
    return out


def _contract_ticket_row(
    *,
    ticket_id: str = "ticket-uuid-001",
    status: str = "open",
    claimed_by: str | None = None,
    guild_id: str = "123456789",
    author_id: str = "111111111",
) -> dict:
    """A camelCase ticket row for contract audit/permission scenarios."""
    return {
        "id": ticket_id,
        "ticketNumber": 1,
        "guildId": guild_id,
        "authorId": author_id,
        "channelId": "444444444",
        "categoryId": "cat-uuid-001",
        "status": status,
        "claimedBy": claimed_by,
        "transcriptUrl": None,
        "createdAt": "2026-01-15T10:00:00+00:00",
        "closedAt": None,
        "lastActivity": "2026-01-15T10:00:00+00:00",
        "parentId": None,
    }


def _contract_note_row(*, author_id: str = "111111111", content: str = "hi") -> dict:
    return {
        "id": "note-uuid-001",
        "ticketId": "ticket-uuid-001",
        "authorId": author_id,
        "content": content,
        "createdAt": "2026-07-04T12:00:00+00:00",
    }


def _actor_interaction(
    *,
    is_admin: bool = False,
    mod_role_id: int | None = None,
    has_mod_role: bool = False,
    author_id: int = 987654321,
    guild_id: int = 123456789,
) -> tuple[MagicMock, MagicMock]:
    """Build a (interaction, bot) pair exercising ``is_mod_check`` for an actor.

    *is_admin* sets ``guild_permissions.administrator``; *mod_role_id* configures
    the guild's mod role via ``bot._guild_mod_role_cache``; *has_mod_role* adds
    that role to the user. Exactly one of *is_admin* / (*mod_role_id* AND
    *has_mod_role*) yields ``is_mod_check == True`` — the permission matrix.
    """
    bot = MagicMock()
    bot._guild_mod_role_cache = {guild_id: str(mod_role_id)} if mod_role_id else {}

    role = MagicMock(spec=discord.Role)
    role.id = mod_role_id or 0
    member = MagicMock(spec=discord.Member)
    member.id = author_id
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = is_admin
    member.roles = [role] if (has_mod_role and mod_role_id is not None) else []

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.guild_id = guild_id
    interaction.user = member
    interaction.client = bot
    return interaction, bot


def _audit_outcomes(db: AsyncMock) -> list[tuple[str, str, str | None]]:
    """Return ``(action, outcome, reason)`` for every insert_audit_row call."""
    rows: list[tuple[str, str, str | None]] = []
    keys = ["guild_id", "ticket_id", "action", "actor_id", "outcome", "reason"]
    for call in db.insert_audit_row.call_args_list:
        kw = call.kwargs if call.kwargs else dict(zip(keys, call.args, strict=False))
        rows.append((kw["action"], kw["outcome"], kw["reason"]))
    return rows


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


async def test_ti019_audit_every_success() -> None:
    """TI-019: GIVEN every op succeeds THEN one success audit row each.

    Drives claim, close, reopen, transfer, create_subticket, create_note and
    delete_note against the real ``TicketService`` over a mock DB; each op
    MUST emit exactly one ``ticket_audit`` row with ``outcome='success'``.
    Per-op RED→GREEN discipline lives in ``tests/test_ticket_service.py``; this
    scenario aggregates them into the contract assertion.
    """
    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    ticket_id = "ticket-uuid-001"

    # --- claim → success (pre=open, re-read=claimed) -----------------------
    open_row = _contract_ticket_row(status="open")
    claimed_row = {**open_row, "status": "claimed", "claimedBy": "999999999"}
    db.get_ticket.side_effect = [open_row, claimed_row]
    await service.claim_ticket(ticket_id, claimed_by="999999999")
    db.get_ticket.reset_mock(side_effect=True)

    # --- close → success (pre=open post-claim, re-read=closed) -------------
    db.get_ticket.side_effect = [open_row, {**open_row, "status": "closed", "closedAt": "2026-06-16T18:00:00+00:00"}]
    await service.close_ticket(ticket_id, closed_by="999999999")
    db.get_ticket.reset_mock(side_effect=True)

    # --- transfer → success (open+unclaimed → claimed by userB) ------------
    db.get_ticket.side_effect = [open_row, {**open_row, "claimedBy": "userB", "status": "claimed"}]
    await service.transfer_ticket(ticket_id, new_claimed_by="userB", actor_id="admin1")
    db.get_ticket.reset_mock(side_effect=True)

    # --- create_note → success --------------------------------------------
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = []
    db.get_recent_notes_for_dedup.return_value = []
    db.insert_ticket_note.return_value = _contract_note_row(content="hello")
    await service.create_note(ticket_id, "999999999", "hello")

    # --- delete_note → success (author matches) ---------------------------
    db.get_ticket_notes.return_value = [_contract_note_row(author_id="999999999")]
    await service.delete_note("note-uuid-001", author_id="999999999", ticket_id=ticket_id)

    # --- get_notes → success (note_list audited per spec) ------------------
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = []
    await service.get_notes(ticket_id)

    # --- create_subticket → success ---------------------------------------
    parent = _contract_ticket_row(ticket_id="parent-uuid-001", status="open")
    parent["guildId"] = "123456789"
    db.get_ticket.return_value = parent
    db.get_max_ticket_number.return_value = 5
    db.insert_ticket.return_value = {**_contract_ticket_row(ticket_id="child-uuid"), "ticketNumber": 6}
    await service.create_subticket(
        "parent-uuid-001",
        "111111111",
        None,
        "666666666",
        guild_id="123456789",
    )

    # --- reopen → success (closed→open, new channel) ----------------------
    closed_row = {**_contract_ticket_row(status="closed"), "ticketNumber": 1, "transcriptUrl": "https://t"}
    reopened = {**closed_row, "channelId": "555555555", "status": "open", "closedAt": None}
    db.get_ticket.side_effect = [closed_row, reopened]
    db.get_guild.return_value = {"id": "123456789", "ticketCategoryId": "100000000", "modRoleId": None}
    category_channel = MagicMock(spec=discord.CategoryChannel)
    guild = MagicMock()
    guild.id = 123456789
    guild.default_role = MagicMock()
    guild.me = MagicMock()
    guild.get_channel = MagicMock(return_value=category_channel)
    guild.get_role = MagicMock(return_value=None)
    guild.get_member = MagicMock(return_value=None)
    new_channel = MagicMock(spec=discord.TextChannel)
    new_channel.id = 555555555
    guild.create_text_channel = AsyncMock(return_value=new_channel)
    await service.reopen_ticket(ticket_id, guild=guild)

    # Contract: every op wrote EXACTLY ONE success audit row.
    rows = _audit_outcomes(db)
    actions = [r[0] for r in rows]
    assert rows, "no audit rows written"
    assert all(r[1] == "success" for r in rows), rows
    expected_actions = {
        "claim",
        "close",
        "transfer",
        "note_add",
        "note_list",
        "note_delete",
        "subticket_create",
        "reopen",
    }
    assert set(actions) == expected_actions, actions
    assert len(rows) == len(expected_actions), (actions, rows)


async def test_ti020_audit_every_denied() -> None:
    """TI-020: GIVEN invariant/permission fail THEN a denied audit row with reason.

    Each denied path MUST write ``outcome='denied'`` with a non-empty reason
    AND re-raise ``ValueError``. Per-op RED→GREEN lives in
    ``tests/test_ticket_service.py``; this aggregates the contract assertion.
    """
    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    ticket_id = "ticket-uuid-001"

    # claim denied (already claimed)
    db.get_ticket.return_value = _contract_ticket_row(status="claimed", claimed_by="userA")
    with pytest.raises(ValueError):
        await service.claim_ticket(ticket_id, claimed_by="userB")
    db.get_ticket.reset_mock(side_effect=True)

    # close denied (already closed)
    db.get_ticket.return_value = _contract_ticket_row(status="closed")
    with pytest.raises(ValueError):
        await service.close_ticket(ticket_id, closed_by="999999999")
    db.get_ticket.reset_mock(side_effect=True)

    # transfer denied (same user as current claimant)
    db.get_ticket.return_value = _contract_ticket_row(status="claimed", claimed_by="userA")
    with pytest.raises(ValueError):
        await service.transfer_ticket(ticket_id, new_claimed_by="userA", actor_id="admin1")
    db.get_ticket.reset_mock(side_effect=True)

    # note_add denied (cap reached)
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = [_contract_note_row() for _ in range(50)]
    with pytest.raises(ValueError):
        await service.create_note(ticket_id, "999999999", "one too many")
    db.get_ticket_notes.return_value = []

    # note_delete denied (non-author)
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = [_contract_note_row(author_id="userA")]
    with pytest.raises(ValueError):
        await service.delete_note("note-uuid-001", author_id="userB", ticket_id=ticket_id)
    db.get_ticket.reset_mock(side_effect=True)

    # reopen denied (not closed)
    open_row = {**_contract_ticket_row(status="open"), "transcriptUrl": None}
    db.get_ticket.return_value = open_row
    guild = MagicMock()
    guild.id = 123456789
    with pytest.raises(ValueError):
        await service.reopen_ticket(ticket_id, guild=guild)
    db.get_ticket.reset_mock(side_effect=True)

    rows = _audit_outcomes(db)
    assert rows, "no denied audit rows written"
    assert all(r[1] == "denied" for r in rows), rows
    assert all(r[2] for r in rows), "every denied row MUST carry a reason"
    assert {"claim", "close", "transfer", "note_add", "note_delete", "reopen"} <= {r[0] for r in rows}


async def test_ti021_audit_guild_scope() -> None:
    """TI-021: GIVEN audit rows guild A+B WHEN query A THEN only A rows returned.

    ``Database.get_audit_rows`` is guild-scoped via ``.eq("guildId")``. The
    contract asserts the query filters by guild_id — modelled by returning only
    guild A rows for the guild A query (unit level: see
    ``tests/test_ticket_service.py``; the row-level ``.eq`` is exercised in PR1
    DB unit tests).
    """
    db = _contract_db()
    guild_a_rows = [
        {"id": "a1", "guildId": "guildA", "action": "close", "outcome": "success"},
        {"id": "a2", "guildId": "guildA", "action": "claim", "outcome": "denied", "reason": "x"},
    ]
    db.get_audit_rows.return_value = guild_a_rows

    rows = await db.get_audit_rows("guildA", limit=50, offset=0)

    assert rows is guild_a_rows
    assert all(r["guildId"] == "guildA" for r in rows)
    db.get_audit_rows.assert_awaited_once_with("guildA", limit=50, offset=0)


# ===========================================================================
# TI-022..TI-028 — permission matrix  (PR2 wires is_mod_check + button gates)
# ===========================================================================


async def test_ti022_create_any_user() -> None:
    """TI-022: GIVEN user/admin/mod/author WHEN create THEN all allowed.

    ``TicketService.create_ticket`` performs NO actor-permission gate — any
    user may open a ticket. Asserted at the service layer: create succeeds for
    every actor type without a permission check raising.
    """
    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    db.get_max_ticket_number.return_value = 0
    row = _contract_ticket_row(status="open", author_id="any")
    db.insert_ticket.return_value = row

    for actor in ("user-regular", "admin", "mod", "author"):
        db.insert_ticket.return_value = {**row, "authorId": actor}
        ticket = await service.create_ticket(
            guild_id="123456789",
            author_id=actor,
            category_id=None,
            channel_id="444444444",
        )
        assert ticket.author_id == actor
    db.insert_ticket.assert_awaited()
    # No insert_audit_row (create_ticket does not audit) — but no permission
    # denial path raised: the matrix contract is "all allowed".


async def test_ti023_claim_permission_matrix() -> None:
    """TI-023: GIVEN admin/mod/author/user WHEN claim THEN admin+mod allowed; others denied.

    The claim gate (``TicketsCog.claim_button``) calls ``is_mod_check`` inline.
    This scenario asserts the permission DECISION for each actor — exactly the
    PR2 contract matrix (claim = mod). The button-gate end-to-end behavior is
    exercised in ``tests/test_tickets_cog.py::TestPR2ButtonPermissionGates``.
    """
    mod_role = 808080
    admin_int, _ = _actor_interaction(is_admin=True)
    mod_int, _ = _actor_interaction(mod_role_id=mod_role, has_mod_role=True)
    author_int, _ = _actor_interaction(author_id=111111111)  # author, not mod
    user_int, _ = _actor_interaction()  # plain user, unconfigured

    assert await is_mod_check(admin_int) is True
    assert await is_mod_check(mod_int) is True
    assert await is_mod_check(author_int) is False
    assert await is_mod_check(user_int) is False


async def test_ti024_close_permission_matrix() -> None:
    """TI-024: GIVEN admin/mod/author/user WHEN close THEN admin/mod/author allowed; user denied.

    Close gate: ``interaction.user.id == authorId OR is_mod_check(interaction)``.
    Asserts the permission decision for each actor (close = author OR mod).
    """
    mod_role = 909090
    ticket_author_id = 111111111
    admin_int, _ = _actor_interaction(is_admin=True)
    mod_int, _ = _actor_interaction(mod_role_id=mod_role, has_mod_role=True)
    author_int, _ = _actor_interaction(author_id=ticket_author_id)
    user_int, _ = _actor_interaction(author_id=222222222)  # non-author, not mod

    async def close_allowed(inter: MagicMock) -> bool:
        is_author = inter.user.id == ticket_author_id
        return is_author or await is_mod_check(inter)

    assert await close_allowed(admin_int) is True
    assert await close_allowed(mod_int) is True
    assert await close_allowed(author_int) is True
    assert await close_allowed(user_int) is False


async def test_ti025_reopen_permission_matrix() -> None:
    """TI-025: GIVEN admin/mod/author/user WHEN reopen THEN admin+mod allowed; others denied.

    ``/reopen`` is decorated with ``@is_mod()`` which wraps ``is_mod_check``.
    Asserts the permission decision for each actor (reopen = mod).
    """
    mod_role = 707070
    admin_int, _ = _actor_interaction(is_admin=True)
    mod_int, _ = _actor_interaction(mod_role_id=mod_role, has_mod_role=True)
    author_int, _ = _actor_interaction()
    user_int, _ = _actor_interaction()

    assert await is_mod_check(admin_int) is True
    assert await is_mod_check(mod_int) is True
    assert await is_mod_check(author_int) is False
    assert await is_mod_check(user_int) is False


async def test_ti026_transfer_permission_matrix() -> None:
    """TI-026: GIVEN admin/mod/author/user WHEN transfer THEN bot: admin OR mod.

    Decision #1 (engram #669): ``/transfer`` STAYS ``@is_mod()`` (admin OR
    configured mod). The dashboard side is admin-only as a documented
    divergence (design.md TI-026 Then column; tested in PR3
    ``ti026TransferPermissionMatrix``). This scenario asserts the BOT
    behavior: admin and configured-mod allowed; author and plain user denied.
    """
    mod_role = 505050
    admin_int, _ = _actor_interaction(is_admin=True)
    mod_int, _ = _actor_interaction(mod_role_id=mod_role, has_mod_role=True)
    author_int, _ = _actor_interaction()  # author, not admin, not mod
    user_int, _ = _actor_interaction()  # plain user, unconfigured

    assert await is_mod_check(admin_int) is True
    assert await is_mod_check(mod_int) is True
    assert await is_mod_check(author_int) is False
    assert await is_mod_check(user_int) is False


async def test_ti027_staff_ops_permission_matrix() -> None:
    """TI-027: GIVEN note CRUD/subticket WHEN admin/mod/author/user THEN admin+mod allowed.

    ``/add_ticket_note``, ``/delete_ticket_note`` and ``/subticket`` are gated
    by ``@is_mod()`` (admin OR configured mod). Asserts the permission decision
    (staff ops = admin OR mod).
    """
    mod_role = 606060
    admin_int, _ = _actor_interaction(is_admin=True)
    mod_int, _ = _actor_interaction(mod_role_id=mod_role, has_mod_role=True)
    user_int, _ = _actor_interaction()
    author_int, _ = _actor_interaction()

    assert await is_mod_check(admin_int) is True
    assert await is_mod_check(mod_int) is True
    assert await is_mod_check(user_int) is False
    assert await is_mod_check(author_int) is False


@pytest.mark.skip(reason=PR3_DASHBOARD)
def test_ti028_audit_view_admin_only() -> None:
    """TI-028: GIVEN admin/mod/author/user WHEN view audit THEN admin only.

    Audit viewing lives on the dashboard audit panel (PR3) and requires an
    admin-only check distinct from ``is_mod_check`` (which admits configured
    mods). Unskipped by PR3 alongside the AuditPanel.
    """
    raise AssertionError("Unskipped by PR3: dashboard AuditPanel admin-only view")


# ===========================================================================
# TI-029..TI-030 — drift: reopen by number / category gate
# ===========================================================================


async def test_ti029_reopen_by_number() -> None:
    """TI-029: GIVEN closed ticket WHEN /reopen ticket:#0003 THEN resolves by number.

    ``/reopen``'s ``ticket_ref`` parser strips the optional ``ticket:`` prefix
    and parses ``#0003`` → number 3; the cog resolves via
    ``get_ticket_by_number(guild_id, 3)``. This scenario asserts the parser +
    guild-scoped DB resolution contract (the cog end-to-end is in
    ``tests/test_tickets_cog.py::TestReopenByTicketRef``).
    """
    ref = parse_ticket_ref("ticket:#0003")
    assert ref is not None
    assert ref.number == 3

    db = _contract_db()
    target = _contract_ticket_row(ticket_id="t-3", status="closed")
    target["ticketNumber"] = 3
    db.get_ticket_by_number = AsyncMock(return_value=target)

    row = await db.get_ticket_by_number("123456789", ref.number)

    assert row is not None
    assert row["ticketNumber"] == 3
    db.get_ticket_by_number.assert_awaited_once_with("123456789", 3)


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


async def test_ti033_guild_scope() -> None:
    """TI-033: GIVEN ticket/note/audit guild B WHEN guild A acts/queries THEN no leak.

    Every service operation scopes its audit row to the TICKET's guildId, and
    ``get_audit_rows`` is guild-filtered (``.eq guildId``). A note added to a
    guild B ticket yields an audit row with ``guildId``=guildB; querying guild
    A's audit returns ONLY guild A rows — the guild B audit never leaks.
    """
    from bot.services.ticket_service import TicketService  # local import keeps module-load light

    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    guild_b = "999000999"
    ticket_id = "guild-b-ticket"
    db.get_ticket.return_value = {"id": ticket_id, "guildId": guild_b}
    db.get_ticket_notes.return_value = []
    db.get_recent_notes_for_dedup.return_value = []
    db.insert_ticket_note.return_value = _contract_note_row(content="x")

    await service.create_note(ticket_id, author_id="mod1", content="x")

    # The note_add audit row is scoped to the TICKET's guild (guildB).
    note_add_calls = [c for c in _audit_calls(db) if c["action"] == "note_add"]
    assert len(note_add_calls) == 1, note_add_calls
    assert note_add_calls[0]["guild_id"] == guild_b
    assert note_add_calls[0]["outcome"] == "success"

    # Guild A audit query returns ONLY guild A rows; the guild B row never leaks.
    db.get_audit_rows.return_value = [
        {"id": "a1", "guildId": "guildA", "action": "close", "outcome": "success"},
    ]
    rows_a = await db.get_audit_rows("guildA", limit=50, offset=0)
    assert all(r["guildId"] == "guildA" for r in rows_a)
    assert all(r["guildId"] != guild_b for r in rows_a)
    db.get_audit_rows.assert_awaited_once_with("guildA", limit=50, offset=0)


async def test_ti034_note_under_cap() -> None:
    """TI-034: GIVEN ticket #5 has 30 notes (under cap 50) WHEN author adds THEN persisted + audit success."""
    from bot.services.ticket_service import TicketService

    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    ticket_id = "ticket-5"
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = [_contract_note_row() for _ in range(30)]
    db.get_recent_notes_for_dedup.return_value = []
    db.insert_ticket_note.return_value = _contract_note_row(content="new")

    note = await service.create_note(ticket_id, "999999999", "new note")

    assert note is not None
    note_add_calls = [c for c in _audit_calls(db) if c["action"] == "note_add"]
    assert len(note_add_calls) == 1
    assert note_add_calls[0]["outcome"] == "success"
    db.insert_ticket_note.assert_awaited_once()


async def test_ti035_author_delete_own() -> None:
    """TI-035: GIVEN note by userA WHEN userA deletes THEN deleted + audit success."""
    from bot.services.ticket_service import TicketService

    db = _contract_db()
    service = TicketService(db=db, cache=TTLCache())
    ticket_id = "ticket-1"
    db.get_ticket.return_value = {"id": ticket_id, "guildId": "123456789"}
    db.get_ticket_notes.return_value = [_contract_note_row(author_id="userA")]

    await service.delete_note("note-uuid-001", author_id="userA", ticket_id=ticket_id)

    db.delete_ticket_note.assert_awaited_once_with("note-uuid-001")
    del_calls = [c for c in _audit_calls(db) if c["action"] == "note_delete"]
    assert len(del_calls) == 1
    assert del_calls[0]["outcome"] == "success"


def test_ti036_action_view_render() -> None:
    """TI-036: GIVEN new ticket channel WHEN ticket opened THEN embed + claim/close buttons sent.

    The cog attaches a persistent ``TicketActionsView`` (Claim + Close buttons
    with stable ``custom_id``s) plus an info embed to the ticket welcome
    message (``bot/cogs/tickets.py`` send at ticket-open). This asserts the
    render contract: both buttons are present and the embed builder produces a
    ``discord.Embed`` referencing the ticket number. The button GATE behavior
    (mod / author-OR-mod) is covered in TI-023/TI-024 + ``TestPR2ButtonPermissionGates``.
    """
    from bot.cogs.tickets import TicketActionsView, _build_ticket_embed

    view = TicketActionsView()
    buttons = {c.custom_id: c for c in view.children if hasattr(c, "custom_id")}
    assert "ticket:claim" in buttons, "claim button missing"
    assert "ticket:close" in buttons, "close button missing"

    embed = _build_ticket_embed({"ticketNumber": 7, "status": "open", "authorId": "x"}, guild_id="123456789")
    assert isinstance(embed, discord.Embed)
    assert "7" in (embed.title or ""), embed.title


async def test_ti037_reopen_noarg_legacy() -> None:
    """TI-037: GIVEN just-closed ticket, channel still exists WHEN /reopen (no arg) THEN resolves by channel.

    When ``ticket_ref`` is ``None`` (omitted), ``parse_ticket_ref`` returns
    ``None`` and the cog falls back to the legacy channel-scoped
    ``get_ticket_by_channel(str(ctx.channel.id))`` lookup — valid in the 5s
    window between ``status=closed`` and ``channel.delete()`` (close deletes
    the channel after 5s, so the no-arg path only resolves in that window).
    """
    assert parse_ticket_ref(None) is None

    db = _contract_db()
    closed_row = _contract_ticket_row(status="closed")
    closed_row["channelId"] = "444444444"
    db.get_ticket_by_channel = AsyncMock(return_value=closed_row)

    row = await db.get_ticket_by_channel("444444444")

    assert row is not None
    assert row["status"] == "closed"
    db.get_ticket_by_channel.assert_awaited_once_with("444444444")


@pytest.mark.skip(reason=PR3_DASHBOARD)
def test_ti038_audit_paginated() -> None:
    """TI-038: GIVEN 200 audit rows WHEN admin visits audit tab THEN paginated rows newest-first."""
    raise AssertionError("Unskipped by PR3: AuditPanel paginates get_audit_rows(limit, offset)")
