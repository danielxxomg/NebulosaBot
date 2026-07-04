import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  buildMockServiceClient,
  buildAuthSession,
} from "./_test-helpers";
import type { Ticket, TicketNote, TicketStatus } from "@/lib/types";

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
    const ADMINISTRATOR = BigInt(0x8);
    return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
  },
}));

import {
  getTicketsForGuild,
  reopenTicket,
  transferTicket,
  getTicketNotes,
  addTicketNote,
  deleteTicketNote,
} from "@/lib/actions/ticket-actions";
import { createServiceClient } from "@/lib/supabase";

const GUILD_ID = "123456789012345678";
const OTHER_GUILD_ID = "999999999999999999";
const TICKET_ID = "ticket-uuid-0001";
const NOTE_ID = "note-uuid-0001";
const CLAIMED_BY = "777777777777777777";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildTicket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    ticketNumber: 1,
    guildId: GUILD_ID,
    authorId: "999999999999999999",
    channelId: "888888888888888888",
    status: "open" satisfies TicketStatus,
    createdAt: new Date().toISOString(),
    lastActivity: new Date().toISOString(),
    categoryId: null,
    claimedBy: null,
    transcriptUrl: null,
    closedAt: null,
    parentId: null,
    ...overrides,
  };
}

function buildTicketNote(overrides: Partial<TicketNote> = {}): TicketNote {
  return {
    id: crypto.randomUUID(),
    ticketId: TICKET_ID,
    authorId: "555555555555555555",
    content: "Internal note text.",
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

function setupAuth({
  hasSession = true,
  hasProviderToken = true,
  guildActive = true,
  isAdmin = true,
  adminGuildId = GUILD_ID,
  ticketData = [] as Ticket[],
  ticketError = null as Error | null,
  ticketSingle = null as Ticket | null,
  ticketSingleError = null as Error | null,
  ticketUpdateError = null as Error | null,
  ticketNoteData = [] as TicketNote[],
  ticketNoteError = null as Error | null,
  ticketNoteSingle = null as { ticketId: string } | null,
  ticketNoteSingleError = null as Error | null,
  ticketNoteInsertError = null as Error | null,
  ticketNoteDeleteError = null as Error | null,
  discordUserId = "111222333444555666",
} = {}) {
  mockGetSession.mockResolvedValue(
    buildAuthSession({ hasSession, hasProviderToken, discordUserId })
  );

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? { data: { active: true }, error: null }
      : { data: null, error: null },
    ticketSelectResult: ticketError
      ? { data: null, error: ticketError }
      : { data: ticketData, error: null },
    ticketSingleResult: ticketSingleError
      ? { data: null, error: ticketSingleError }
      : ticketSingle
        ? { data: ticketSingle, error: null }
        : { data: null, error: null },
    ticketUpdateResult: ticketUpdateError
      ? { data: null, error: ticketUpdateError }
      : { data: null, error: null },
    ticketNoteSelectResult: ticketNoteError
      ? { data: null, error: ticketNoteError }
      : { data: ticketNoteData, error: null },
    ticketNoteSingleResult: ticketNoteSingleError
      ? { data: null, error: ticketNoteSingleError }
      : ticketNoteSingle
        ? { data: ticketNoteSingle, error: null }
        : { data: null, error: null },
    ticketNoteInsertResult: ticketNoteInsertError
      ? { data: null, error: ticketNoteInsertError }
      : { data: null, error: null },
    ticketNoteDeleteResult: ticketNoteDeleteError
      ? { data: null, error: ticketNoteDeleteError }
      : { data: null, error: null },
  });

  vi.mocked(createServiceClient).mockResolvedValue(
    svc as unknown as Awaited<ReturnType<typeof createServiceClient>>
  );

  // The mock user is an administrator of `adminGuildId` only; querying any
  // other guild id must be rejected by verifyGuildAdmin (guild isolation).
  mockFetchUserGuilds.mockResolvedValue([
    { id: adminGuildId, permissions: isAdmin ? "8" : "1024" },
  ]);

  return svc;
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Auth gating
// ---------------------------------------------------------------------------

describe("getTicketsForGuild — auth gating", () => {
  it("returns an auth error and no data when there is no session", async () => {
    setupAuth({ hasSession: false });
    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/authenticated/i);
  });

  it("returns an auth error when the Discord provider token is missing", async () => {
    setupAuth({ hasProviderToken: false });
    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/discord token|re-login/i);
  });

  it("returns an auth error and no data when the caller is not a guild admin", async () => {
    setupAuth({ isAdmin: false });
    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
  });

  it("returns an auth error when the guild is inactive", async () => {
    setupAuth({ guildActive: false });
    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/guild not found|inactive/i);
  });
});

// ---------------------------------------------------------------------------
// Guild isolation + query shape
// ---------------------------------------------------------------------------

describe("getTicketsForGuild — guild isolation & query shape", () => {
  it("filters by the requested guild id (guild isolation)", async () => {
    const otherGuild = "999999999999999999";
    const svc = setupAuth({ adminGuildId: otherGuild });
    await getTicketsForGuild(otherGuild);

    expect(svc.from).toHaveBeenCalledWith("ticket");
    expect(svc.ticket.eq).toHaveBeenCalledWith("guildId", otherGuild);
  });

  it("queries ticket rows newest-first with a hard limit of 50", async () => {
    const svc = setupAuth();
    await getTicketsForGuild(GUILD_ID);

    expect(svc.ticket.select).toHaveBeenCalledWith("*");
    expect(svc.ticket.order).toHaveBeenCalledWith("createdAt", {
      ascending: false,
    });
    expect(svc.ticket.limit).toHaveBeenCalledWith(50);
  });

  it("queries exactly the requested guild id, not another guild", async () => {
    const svc = setupAuth();
    await getTicketsForGuild(GUILD_ID);

    expect(svc.ticket.eq).toHaveBeenCalledWith("guildId", GUILD_ID);
    // No call ever filters by a different guild id.
    for (const [column] of svc.ticket.eq.mock.calls) {
      expect(column).toBe("guildId");
    }
  });
});

// ---------------------------------------------------------------------------
// Return shape + empty / error states
// ---------------------------------------------------------------------------

describe("getTicketsForGuild — return shape", () => {
  it("returns the queried tickets with error: null on success", async () => {
    const tickets: Ticket[] = [
      buildTicket({ ticketNumber: 2, status: "open" }),
      buildTicket({ ticketNumber: 1, status: "closed", claimedBy: "777" }),
    ];
    setupAuth({ ticketData: tickets });

    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.error).toBeNull();
    expect(result.data).toEqual(tickets);
  });

  it("returns an empty array (not null) when the guild has no tickets", async () => {
    setupAuth({ ticketData: [] });

    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.error).toBeNull();
    expect(result.data).toEqual([]);
  });

  it("returns a database error and no data when the ticket query fails", async () => {
    setupAuth({ ticketError: new Error("relation does not exist") });

    const result = await getTicketsForGuild(GUILD_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});

// ===========================================================================
// reopenTicket
// ===========================================================================

describe("reopenTicket — auth gating", () => {
  it("rejects a non-admin caller with an auth error and never updates", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID, status: "closed" }),
    });
    const result = await reopenTicket(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("rejects cross-guild access: admin of another guild cannot reopen", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID, status: "closed" }),
    });
    const result = await reopenTicket(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });
});

describe("reopenTicket — query shape & return", () => {
  it("updates status to open and clears closedAt, scoped by ticket id", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID, status: "closed", closedAt: "2026-01-01T00:00:00.000Z" }),
    });
    const result = await reopenTicket(TICKET_ID);

    expect(svc.from).toHaveBeenCalledWith("ticket");
    expect(svc.ticket.update).toHaveBeenCalledWith({
      status: "open",
      closedAt: null,
    });
    expect(svc.ticket.updateEq).toHaveBeenCalledWith("id", TICKET_ID);
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("returns an error when the ticket does not exist", async () => {
    const svc = setupAuth({ ticketSingle: null });
    const result = await reopenTicket(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("returns a database error when the update fails", async () => {
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketUpdateError: new Error("update blew up"),
    });
    const result = await reopenTicket(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});

// ===========================================================================
// transferTicket
// ===========================================================================

describe("transferTicket — auth gating", () => {
  it("rejects a non-admin caller and never updates", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("rejects cross-guild access: admin of another guild cannot transfer", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });
});

describe("transferTicket — query shape & return", () => {
  it("updates claimedBy to the new staff id, scoped by ticket id", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID, claimedBy: null }),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(svc.from).toHaveBeenCalledWith("ticket");
    expect(svc.ticket.update).toHaveBeenCalledWith({ claimedBy: CLAIMED_BY });
    expect(svc.ticket.updateEq).toHaveBeenCalledWith("id", TICKET_ID);
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("returns an error when the ticket does not exist", async () => {
    const svc = setupAuth({ ticketSingle: null });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/i);
    expect(svc.ticket.update).not.toHaveBeenCalled();
  });

  it("returns a database error when the update fails", async () => {
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketUpdateError: new Error("nope"),
    });
    const result = await transferTicket(TICKET_ID, CLAIMED_BY);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});

// ===========================================================================
// getTicketNotes
// ===========================================================================

describe("getTicketNotes — auth gating & guild isolation", () => {
  it("rejects a non-admin caller and never queries notes", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.select).not.toHaveBeenCalled();
  });

  it("enforces guild isolation: notes of a ticket in a non-admin guild are hidden", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.select).not.toHaveBeenCalled();
  });
});

describe("getTicketNotes — query shape & return", () => {
  it("queries ticket_note by ticketId, newest-first, with a limit of 50", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    await getTicketNotes(TICKET_ID);

    expect(svc.from).toHaveBeenCalledWith("ticket_note");
    expect(svc.ticketNote.select).toHaveBeenCalledWith("*");
    expect(svc.ticketNote.eq).toHaveBeenCalledWith("ticketId", TICKET_ID);
    expect(svc.ticketNote.order).toHaveBeenCalledWith("createdAt", {
      ascending: false,
    });
    expect(svc.ticketNote.limit).toHaveBeenCalledWith(50);
  });

  it("returns the notes with error: null on success", async () => {
    const notes: TicketNote[] = [
      buildTicketNote({ id: "n2", content: "second", createdAt: "2026-01-02T00:00:00.000Z" }),
      buildTicketNote({ id: "n1", content: "first", createdAt: "2026-01-01T00:00:00.000Z" }),
    ];
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketNoteData: notes,
    });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.error).toBeNull();
    expect(result.data).toEqual(notes);
  });

  it("returns an empty array when there are no notes", async () => {
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketNoteData: [],
    });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.error).toBeNull();
    expect(result.data).toEqual([]);
  });

  it("returns an error when the ticket does not exist", async () => {
    const svc = setupAuth({ ticketSingle: null });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/i);
    expect(svc.ticketNote.select).not.toHaveBeenCalled();
  });

  it("returns a database error when the notes query fails", async () => {
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketNoteError: new Error("notes table missing"),
    });
    const result = await getTicketNotes(TICKET_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});

// ===========================================================================
// addTicketNote
// ===========================================================================

describe("addTicketNote — auth gating & guild isolation", () => {
  it("rejects a non-admin caller and never inserts", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "hello");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });

  it("rejects cross-guild access: cannot add a note to another guild's ticket", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await addTicketNote(TICKET_ID, "hello");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });
});

describe("addTicketNote — query shape & return", () => {
  it("inserts a note with ticketId, content, and the author's Discord id", async () => {
    const svc = setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      discordUserId: "111222333444555666",
    });
    const result = await addTicketNote(TICKET_ID, "Internal update.");

    expect(svc.from).toHaveBeenCalledWith("ticket_note");
    expect(svc.ticketNote.insert).toHaveBeenCalledWith({
      ticketId: TICKET_ID,
      content: "Internal update.",
      authorId: "111222333444555666",
    });
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("returns an error when the ticket does not exist", async () => {
    const svc = setupAuth({ ticketSingle: null });
    const result = await addTicketNote(TICKET_ID, "hello");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/i);
    expect(svc.ticketNote.insert).not.toHaveBeenCalled();
  });

  it("returns a database error when the insert fails", async () => {
    setupAuth({
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketNoteInsertError: new Error("constraint violation"),
    });
    const result = await addTicketNote(TICKET_ID, "hello");

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});

// ===========================================================================
// deleteTicketNote
// ===========================================================================

describe("deleteTicketNote — auth gating & guild isolation", () => {
  it("rejects a non-admin caller and never deletes", async () => {
    const svc = setupAuth({
      isAdmin: false,
      ticketNoteSingle: { ticketId: TICKET_ID },
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.delete).not.toHaveBeenCalled();
  });

  it("enforces guild isolation: cannot delete a note on another guild's ticket", async () => {
    const svc = setupAuth({
      adminGuildId: OTHER_GUILD_ID,
      ticketNoteSingle: { ticketId: TICKET_ID },
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/administrator/i);
    expect(svc.ticketNote.delete).not.toHaveBeenCalled();
  });
});

describe("deleteTicketNote — query shape & return", () => {
  it("deletes the note scoped by id", async () => {
    const svc = setupAuth({
      ticketNoteSingle: { ticketId: TICKET_ID },
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(svc.from).toHaveBeenCalledWith("ticket_note");
    expect(svc.ticketNote.delete).toHaveBeenCalledWith();
    expect(svc.ticketNote.deleteEq).toHaveBeenCalledWith("id", NOTE_ID);
    expect(result.data).toBeNull();
    expect(result.error).toBeNull();
  });

  it("returns an error when the note does not exist", async () => {
    const svc = setupAuth({
      ticketNoteSingle: null,
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/not found/i);
    expect(svc.ticketNote.delete).not.toHaveBeenCalled();
  });

  it("returns a database error when the delete fails", async () => {
    setupAuth({
      ticketNoteSingle: { ticketId: TICKET_ID },
      ticketSingle: buildTicket({ id: TICKET_ID, guildId: GUILD_ID }),
      ticketNoteDeleteError: new Error("delete failed"),
    });
    const result = await deleteTicketNote(NOTE_ID);

    expect(result.data).toBeNull();
    expect(result.error).toMatch(/database error/i);
  });
});
