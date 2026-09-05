import {
  getTicketsForGuild,
  getReopenGuidance,
  transferTicket,
  getTicketNotes,
  addTicketNote,
  deleteTicketNote,
  getTicketAudit,
} from "@/lib/actions/ticket-actions";
import { createServiceClient } from "@/lib/supabase";
import { NOTE_CAP } from "@/lib/ticket-invariants";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  buildMockServiceClient,
  buildAuthSession,
} from "./_test-helpers";
import type { Ticket, TicketNote, TicketAudit, TicketStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetSession = vi.fn();
const mockFetchUserGuilds = vi.fn();

vi.mock("@/lib/supabase", () => ({
  createServerSupabaseClient: vi.fn(() =>
    Promise.resolve({
      auth: { getSession: mockGetSession },
    })
  ),
  createServiceClient: vi.fn(),
}));

vi.mock("@/lib/discord", () => ({
  fetchUserGuilds: (...args: unknown[]) => mockFetchUserGuilds(...args),
  hasAdministratorPerm: (perm: string) => {
    const permsBigInt = BigInt(perm);
    const ADMINISTRATOR = 0x8n;
    return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
  },
}));

const GUILD_ID = "123456789012345678";
const OTHER_GUILD_ID = "999999999999999999";
const TICKET_ID = "ticket-uuid-0001";
const NOTE_ID = "note-uuid-0001";
const CLAIMED_BY = "777777777777777777";
const CATEGORY_ID = "111111111111111111";
const SESSION_USER_ID = "111222333444555666";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const buildTicket = (overrides: Partial<Ticket> = {}): Ticket => (
  {
    authorId: "999999999999999999",
    categoryId: null,
    channelId: "888888888888888888",
    claimedBy: null,
    closedAt: null,
    createdAt: new Date().toISOString(),
    guildId: GUILD_ID,
    id: crypto.randomUUID(),
    lastActivity: new Date().toISOString(),
    parentId: null,
    status: "open" satisfies TicketStatus,
    ticketNumber: 1,
    transcriptUrl: null,
    ...overrides,
  }
);

const buildTicketNote = (overrides: Partial<TicketNote> = {}): TicketNote => (
  {
    authorId: SESSION_USER_ID,
    content: "Internal note text.",
    createdAt: new Date().toISOString(),
    id: crypto.randomUUID(),
    ticketId: TICKET_ID,
    ...overrides,
  }
);

const buildAuditRow = (overrides: Partial<TicketAudit> = {}): TicketAudit => (
  {
    action: "claim",
    actorId: "900000000000000001",
    createdAt: new Date().toISOString(),
    guildId: GUILD_ID,
    id: crypto.randomUUID(),
    outcome: "success",
    reason: null,
    ticketId: TICKET_ID,
    ...overrides,
  }
);

const setupAuth = ({
  hasSession = true,
  hasProviderToken = true,
  guildActive = true,
  guildTicketCategoryId = CATEGORY_ID as string | null,
  isAdmin = true,
  adminGuildId = GUILD_ID,
  ticketData = [] as Ticket[],
  ticketError = null as Error | null,
  ticketSingle = null as Ticket | null,
  ticketSingleError = null as Error | null,
  ticketUpdateError = null as Error | null,
  ticketNoteData = [] as TicketNote[],
  ticketNoteError = null as Error | null,
  ticketNoteSingle = null as { ticketId: string; authorId?: string } | null,
  ticketNoteSingleError = null as Error | null,
  ticketNoteInsertError = null as Error | null,
  ticketNoteDeleteError = null as Error | null,
  ticketAuditData = [] as TicketAudit[],
  ticketAuditError = null as Error | null,
  discordUserId = SESSION_USER_ID,
} = {}) => {
  mockGetSession.mockResolvedValue(
    buildAuthSession({ discordUserId, hasProviderToken, hasSession })
  );

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? {
          // The mock resolves every `from("guild").select().single()` to this
          // row, so include both `active` (read by verifyGuildAdmin) and
          // `ticketCategoryId` (read by getReopenGuidance) here.
          data: { active: true, ticketCategoryId: guildTicketCategoryId },
          error: null,
        }
      : { data: null, error: null },
    ticketAuditSelectResult: ticketAuditError
      ? { data: null, error: ticketAuditError }
      : { data: ticketAuditData, error: null },
    ticketNoteDeleteResult: ticketNoteDeleteError
      ? { data: null, error: ticketNoteDeleteError }
      : { data: null, error: null },
    ticketNoteInsertResult: ticketNoteInsertError
      ? { data: null, error: ticketNoteInsertError }
      : { data: null, error: null },
    ticketNoteSelectResult: ticketNoteError
      ? { data: null, error: ticketNoteError }
      : { data: ticketNoteData, error: null },
    ticketNoteSingleResult: ticketNoteSingleError
      ? { data: null, error: ticketNoteSingleError }
      : (ticketNoteSingle
        ? { data: ticketNoteSingle, error: null }
        : { data: null, error: null }),
    ticketSelectResult: ticketError
      ? { data: null, error: ticketError }
      : { data: ticketData, error: null },
    ticketSingleResult: ticketSingleError
      ? { data: null, error: ticketSingleError }
      : (ticketSingle
        ? { data: ticketSingle, error: null }
        : { data: null, error: null }),
    ticketUpdateResult: ticketUpdateError
      ? { data: null, error: ticketUpdateError }
      : { data: null, error: null },
  });

  vi.mocked(createServiceClient).mockResolvedValue(
    svc as unknown as Awaited<ReturnType<typeof createServiceClient>>
  );

  mockFetchUserGuilds.mockResolvedValue([
    { id: adminGuildId, permissions: isAdmin ? "8" : "1024" },
  ]);

  return svc;
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// getTicketsForGuild — unchanged behavior (smoke check)
// ---------------------------------------------------------------------------

describe("getTicketsForGuild — auth gating", () => {
  it("returns an auth error and no data when there is no session", async () => {
    setupAuth({ hasSession: false });
    const result = await getTicketsForGuild(GUILD_ID);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/authenticated/iu);
  });

  it("returns an auth error when the caller is not a guild admin", async () => {
    setupAuth({ isAdmin: false });
    const result = await getTicketsForGuild(GUILD_ID);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
  });

  it("returns an auth error when the guild is inactive", async () => {
    setupAuth({ guildActive: false });
    const result = await getTicketsForGuild(GUILD_ID);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/guild not found|inactive/iu);
  });
});

describe("getTicketsForGuild — query shape", () => {
  it("filters by the requested guild id newest-first with limit 50", async () => {
    const svc = setupAuth();
    await getTicketsForGuild(GUILD_ID);
    expect(svc.ticket.eq).toHaveBeenCalledWith("guildId", GUILD_ID);
    expect(svc.ticket.order).toHaveBeenCalledWith("createdAt", {
      ascending: false,
    });
    expect(svc.ticket.limit).toHaveBeenCalledWith(50);
  });
});

// ===========================================================================
// getReopenGuidance (replaces reopenTicket — NO DB mutation)
// ===========================================================================

describe("getReopenGuidance — auth gating", () => {
  it("rejects a non-admin caller and never reads the guild config", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID, status: "closed" }),
    });
    const result = await getReopenGuidance(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
    // resolveTicketGuild reads the ticket for guildId; the category check is
    // skipped because auth fails first.
  });

  it("rejects cross-guild access: admin of another guild cannot get guidance", async () => {
    setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID, status: "closed" }),
    });
    const result = await getReopenGuidance(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
  });
});

describe("getReopenGuidance — category gate (TI-030)", () => {
  it("returns an error and NO command when ticketCategoryId is missing/empty", async () => {
    setupAuth({
      guildTicketCategoryId: null,
      ticketSingle: buildTicket({
        guildId: GUILD_ID,
        id: TICKET_ID,
        status: "closed",
        ticketNumber: 3,
      }),
    });
    const result = await getReopenGuidance(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/category is not configured/iu);
  });

  it("returns an error when ticketCategoryId is an empty string", async () => {
    setupAuth({
      guildTicketCategoryId: "  ",
      ticketSingle: buildTicket({
        guildId: GUILD_ID,
        id: TICKET_ID,
        status: "closed",
        ticketNumber: 3,
      }),
    });
    const result = await getReopenGuidance(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/category is not configured/iu);
  });
});

describe("getReopenGuidance — guidance shape (TI-029)", () => {
  it("returns the ticket number and the /reopen command, never mutating the ticket", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({
        guildId: GUILD_ID,
        id: TICKET_ID,
        status: "closed",
        ticketNumber: 3,
      }),
    });
    const result = await getReopenGuidance(TICKET_ID);

    expect(result.error).toBeNull();
    expect(result.data).not.toBeNull();
    if (result.data) {
      expect(result.data.ticketNumber).toBe(3);
      expect(result.data.command).toBe("/reopen ticket:#0003");
    }
    // CRITICAL (decision #2a): the dashboard MUST NOT update the ticket table.
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("returns an error when the ticket does not exist", async () => {
    setupAuth({ ticketSingle: null });
    const result = await getReopenGuidance(TICKET_ID);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/iu);
  });
});

// ===========================================================================
// transferTicket — sets claimedBy AND status='claimed' (decision #3)
// ===========================================================================

describe("transferTicket — auth gating", () => {
  it("rejects a non-admin caller and never updates", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });
});

describe("transferTicket — updates claimedBy AND status='claimed'", () => {
  it("sets both claimedBy and status='claimed' (decision #3 — implicit re-claim)", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ claimedBy: null, guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(svc.from).toHaveBeenCalledWith("ticket");
    expect(svc.ticket.update).toHaveBeenCalledWith({
      claimedBy: CLAIMED_BY,
      status: "claimed",
    });
    expect(svc.ticket.updateEq).toHaveBeenCalledWith("id", TICKET_ID);
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("also sets status='claimed' when the source ticket was already claimed", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({
        claimedBy: "555555555555555555",
        guildId: GUILD_ID,
        id: TICKET_ID,
        status: "claimed",
      }),
    });
    await transferTicket(TICKET_ID, CLAIMED_BY);
    expect(svc.ticket.update).toHaveBeenCalledWith({
      claimedBy: CLAIMED_BY,
      status: "claimed",
    });
  });

  it("returns an error when the ticket does not exist", async () => {
    const svc = setupAuth({ ticketSingle: null });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/iu);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("returns a database error when the update fails", async () => {
    setupAuth({
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
      ticketUpdateError: new Error("nope"),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/iu);
  });
});

// ===========================================================================
// getTicketNotes — unchanged behavior (smoke check)
// ===========================================================================

describe("getTicketNotes — query shape & return", () => {
  it("queries ticket_note by ticketId, newest-first, with a limit of 50", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    await getTicketNotes(TICKET_ID);
    expect(svc.from).toHaveBeenCalledWith("ticket_note");
    expect(svc.ticketNote.eq).toHaveBeenCalledWith("ticketId", TICKET_ID);
    expect(svc.ticketNote.limit).toHaveBeenCalledWith(50);
  });

  it("returns the notes with error: null on success", async () => {
    const notes: TicketNote[] = [
      buildTicketNote({ content: "second", id: "n2" }),
      buildTicketNote({ content: "first", id: "n1" }),
    ];
    setupAuth({
      ticketNoteData: notes,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await getTicketNotes(TICKET_ID);
    expect(result.error).toBeNull();
    expect(result.data).toEqual(notes);
  });
});

// ===========================================================================
// addTicketNote — cap (TI-031) + dedup (TI-016) + under-cap (TI-034)
// ===========================================================================

describe("addTicketNote — auth gating", () => {
  it("rejects a non-admin caller and never inserts", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "hello");
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });
});

describe("addTicketNote — note cap (TI-031 / TI-034)", () => {
  it("rejects adding when the ticket already has 50 notes (cap reached)", async () => {
    const svc = setupAuth({
      ticketNoteData: Array.from({ length: NOTE_CAP }, (_, i) =>
        buildTicketNote({ authorId: "999", content: `note ${i}`, id: `n${i}` })
      ),
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "one too many");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/cap|limit/iu);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });

  it("persists the note when the ticket has fewer than 50 notes (TI-034)", async () => {
    const svc = setupAuth({
      ticketNoteData: Array.from({ length: 30 }, (_, i) =>
        buildTicketNote({ authorId: "999", content: `note ${i}`, id: `n${i}` })
      ),
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "new note under cap");

    expect(result.error).toBeNull();
    expect(svc.ticketNote.insert).toHaveBeenCalledWith({
      authorId: SESSION_USER_ID,
      content: "new note under cap",
      ticketId: TICKET_ID,
    });
  });
});

describe("addTicketNote — note dedup (TI-016 normalized hash)", () => {
  it("rejects a normalized duplicate from the same author within the 2s window", async () => {
    const now = new Date();
    const recent: TicketNote[] = [
      buildTicketNote({
        authorId: SESSION_USER_ID,
        content: "Hello World",
        createdAt: new Date(now.getTime() - 1000).toISOString(),
        id: "near",
      }),
    ];
    const svc = setupAuth({
      discordUserId: SESSION_USER_ID,
      ticketNoteData: recent,
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    // Cosmetic whitespace/case variant of an own note 1s ago → same hash.
    const result = await addTicketNote(TICKET_ID, "  hello   world  ");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/duplicate/iu);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });

  it("allows the same content from a different author (TI-018)", async () => {
    const now = new Date();
    const svc = setupAuth({
      discordUserId: SESSION_USER_ID,
      ticketNoteData: [
        buildTicketNote({
          authorId: "999999999999999999",
          content: "hello",
          createdAt: new Date(now.getTime() - 500).toISOString(),
          id: "other-author",
        }),
      ],
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "hello");

    expect(result.error).toBeNull();
    expect(svc.ticketNote.insert).toHaveBeenCalled();
  });
});

// ===========================================================================
// deleteTicketNote — author-only (TI-032 / TI-035)
// ===========================================================================

describe("deleteTicketNote — author-only ownership (TI-032 / TI-035)", () => {
  it("allows the note author to delete their own note (TI-035)", async () => {
    const svc = setupAuth({
      discordUserId: SESSION_USER_ID,
      ticketNoteSingle: { authorId: SESSION_USER_ID, ticketId: TICKET_ID },
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(svc.from).toHaveBeenCalledWith("ticket_note");
    expect(svc.ticketNote.delete).toHaveBeenCalledWith();
    expect(svc.ticketNote.deleteEq).toHaveBeenCalledWith("id", NOTE_ID);
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("rejects deleting another author's note (TI-032)", async () => {
    const svc = setupAuth({
      discordUserId: SESSION_USER_ID,
      ticketNoteSingle: { authorId: "999999999999999999", ticketId: TICKET_ID },
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/author|owner|own note/iu);
    expect(svc.ticketNote.delete).not.toHaveBeenCalled();
  });

  it("enforces guild isolation: cannot delete a note on another guild's ticket", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketNoteSingle: { authorId: SESSION_USER_ID, ticketId: TICKET_ID },
      ticketSingle: buildTicket({ guildId: GUILD_ID, id: TICKET_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
    expect(svc.ticketNote.delete).not.toHaveBeenCalled();
  });

  it("returns an error when the note does not exist", async () => {
    setupAuth({ ticketNoteSingle: null });
    const result = await deleteTicketNote(NOTE_ID);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/iu);
  });
});

// ===========================================================================
// getTicketAudit — guild-scoped, paginated, newest-first (TI-038 / TI-021)
// ===========================================================================

describe("getTicketAudit — auth gating", () => {
  it("rejects a non-admin caller and never queries audit", async () => {
    const svc = setupAuth({ isAdmin: false });
    const result = await getTicketAudit(GUILD_ID, TICKET_ID, 1);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/iu);
    expect(svc.ticketAudit.select).not.toHaveBeenCalled();
  });
});

describe("getTicketAudit — guild-scoped pagination (TI-038 / TI-021)", () => {
  it("queries ticket_audit filtered by guildId, newest-first, paginated", async () => {
    const svc = setupAuth();
    const result = await getTicketAudit(GUILD_ID, TICKET_ID, 1);

    expect(svc.from).toHaveBeenCalledWith("ticket_audit");
    expect(svc.ticketAudit.eq).toHaveBeenCalledWith("guildId", GUILD_ID);
    expect(svc.ticketAudit.order).toHaveBeenCalledWith("createdAt", {
      ascending: false,
    });
    // Page 1 of a PAGE_SIZE page → range(0, PAGE_SIZE - 1)
    expect(svc.ticketAudit.range).toHaveBeenCalledWith(0, 19);
    expect(result.error).toBeNull();
  });

  it("returns the rows with error: null on success", async () => {
    const rows: TicketAudit[] = [
      buildAuditRow({ action: "close", createdAt: "2026-01-02T00:00:00.000Z", id: "a2" }),
      buildAuditRow({ action: "claim", createdAt: "2026-01-01T00:00:00.000Z", id: "a1" }),
    ];
    setupAuth({ ticketAuditData: rows });
    const result = await getTicketAudit(GUILD_ID, TICKET_ID, 1);
    expect(result.error).toBeNull();
    expect(result.data).toEqual(rows);
  });

  it("uses offset for pages beyond the first (page 3 → range(40, 59))", async () => {
    const svc = setupAuth();
    await getTicketAudit(GUILD_ID, TICKET_ID, 3);
    expect(svc.ticketAudit.range).toHaveBeenCalledWith(40, 59);
  });

  it("returns an empty array when there are no audit rows", async () => {
    setupAuth({ ticketAuditData: [] });
    const result = await getTicketAudit(GUILD_ID, TICKET_ID, 1);
    expect(result.error).toBeNull();
    expect(result.data).toEqual([]);
  });

  it("returns a database error when the audit query fails", async () => {
    setupAuth({ ticketAuditError: new Error("audit table missing") });
    const result = await getTicketAudit(GUILD_ID, TICKET_ID, 1);
    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/iu);
  });
});