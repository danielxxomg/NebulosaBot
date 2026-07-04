import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  buildMockServiceClient,
  buildAuthSession,
} from "./_test-helpers";
import type { Ticket, TicketStatus } from "@/lib/types";

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

import { getTicketsForGuild } from "@/lib/actions/ticket-actions";
import { createServiceClient } from "@/lib/supabase";

const GUILD_ID = "123456789012345678";

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
} = {}) {
  mockGetSession.mockResolvedValue(
    buildAuthSession({ hasSession, hasProviderToken })
  );

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? { data: { active: true }, error: null }
      : { data: null, error: null },
    ticketSelectResult: ticketError
      ? { data: null, error: ticketError }
      : { data: ticketData, error: null },
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
