import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { Ticket, TicketStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetTicketsForGuild = vi.fn();

vi.mock("@/lib/actions/ticket-actions", () => ({
  getTicketsForGuild: (...args: unknown[]) => mockGetTicketsForGuild(...args),
}));

import TicketsPage from "@/app/(authenticated)/guilds/[guildId]/tickets/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const GUILD_ID = "123456789012345678";

function buildTicket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: crypto.randomUUID(),
    ticketNumber: 100,
    guildId: GUILD_ID,
    authorId: "999999999999999999",
    channelId: "888888888888888888",
    status: "open" satisfies TicketStatus,
    createdAt: "2025-01-15T10:30:00.000Z",
    lastActivity: "2025-01-15T10:30:00.000Z",
    categoryId: null,
    claimedBy: null,
    transcriptUrl: null,
    closedAt: null,
    ...overrides,
  };
}

/**
 * The page is an async server component: `await Page(...)` resolves to the
 * rendered React element, which we then hand to `render`.
 */
async function renderPage() {
  const ui = await TicketsPage({
    params: Promise.resolve({ guildId: GUILD_ID }),
  });
  return render(ui);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Stats cards
// ---------------------------------------------------------------------------

describe("TicketsPage — stats cards", () => {
  it("renders correct counts for a mix of open / claimed / closed tickets", async () => {
    // 5 open / 3 claimed / 7 closed. Ticket numbers are 100+ so the count
    // text ("5", "3", "7") never collides with a "#NNN" row cell.
    const tickets: Ticket[] = [
      ...Array.from({ length: 5 }, (_, i) =>
        buildTicket({ ticketNumber: 100 + i, status: "open" })
      ),
      ...Array.from({ length: 3 }, (_, i) =>
        buildTicket({
          ticketNumber: 200 + i,
          status: "claimed",
          claimedBy: "777",
        })
      ),
      ...Array.from({ length: 7 }, (_, i) =>
        buildTicket({
          ticketNumber: 300 + i,
          status: "closed",
          closedAt: "2025-02-01T00:00:00.000Z",
        })
      ),
    ];

    mockGetTicketsForGuild.mockResolvedValue({ data: tickets, error: null });

    await renderPage();

    // Count text lives in the stat-card count paragraphs. getByText does an
    // exact match, so "5" matches only `<p>5</p>`, not "Showing the 15...".
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
  });

  it("renders all stats as 0 and shows the empty state when there are no tickets", async () => {
    mockGetTicketsForGuild.mockResolvedValue({ data: [], error: null });

    await renderPage();

    // Three stat cards, each showing 0.
    expect(screen.getAllByText("0")).toHaveLength(3);

    // Empty-state copy (page.tsx:163).
    expect(screen.getByText("No tickets yet")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Ticket table
// ---------------------------------------------------------------------------

describe("TicketsPage — ticket table", () => {
  it("renders column headers and a row for a sample ticket", async () => {
    const ticket = buildTicket({
      ticketNumber: 42,
      status: "open",
      authorId: "111111111111111111",
      claimedBy: "222222222222222222",
    });

    mockGetTicketsForGuild.mockResolvedValue({ data: [ticket], error: null });

    await renderPage();

    // Column headers (page.tsx:175-188).
    expect(screen.getByText("Number")).toBeTruthy();
    expect(screen.getByText("Status")).toBeTruthy();
    expect(screen.getByText("Author")).toBeTruthy();
    expect(screen.getByText("Created")).toBeTruthy();
    expect(screen.getByText("Claimed By")).toBeTruthy();

    // Row data: ticket number is rendered as "#NNN".
    expect(screen.getByText("#42")).toBeTruthy();
    // Author snowflake renders in font-mono.
    expect(screen.getByText("111111111111111111")).toBeTruthy();
    // Claimed-by snowflake renders when non-null.
    expect(screen.getByText("222222222222222222")).toBeTruthy();
  });

  it("renders an em dash for claimedBy when it is null", async () => {
    // page.tsx:210 — `{ ticket.claimedBy ?? "—" }` (em dash, U+2014).
    const ticket = buildTicket({ ticketNumber: 9, claimedBy: null });

    mockGetTicketsForGuild.mockResolvedValue({ data: [ticket], error: null });

    await renderPage();

    expect(screen.getByText("\u2014")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Status badges — accessibility: text label, never color alone
// ---------------------------------------------------------------------------

describe("TicketsPage — status badges render text labels", () => {
  it("renders Open / Claimed / Closed text labels inside the table", async () => {
    // One of each status so every badge label is present.
    const tickets: Ticket[] = [
      buildTicket({ ticketNumber: 1, status: "open" }),
      buildTicket({
        ticketNumber: 2,
        status: "claimed",
        claimedBy: "777",
      }),
      buildTicket({
        ticketNumber: 3,
        status: "closed",
        closedAt: "2025-02-01T00:00:00.000Z",
      }),
    ];

    mockGetTicketsForGuild.mockResolvedValue({ data: tickets, error: null });

    await renderPage();

    // Scope to the table so we assert on the badge labels, not the stat-card
    // labels (which are also "Open" / "Claimed" / "Closed"). Status must be
    // conveyed by text, not by color alone (accessibility).
    const table = screen.getByRole("table");

    expect(within(table).getByText("Open")).toBeTruthy();
    expect(within(table).getByText("Claimed")).toBeTruthy();
    expect(within(table).getByText("Closed")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe("TicketsPage — error state", () => {
  it("renders the error card and no table when getTicketsForGuild returns an error", async () => {
    mockGetTicketsForGuild.mockResolvedValue({
      data: null,
      error: "Database error: relation does not exist",
    });

    await renderPage();

    // Title (page.tsx:115) — `Couldn&apos;t` renders as "Couldn't".
    expect(screen.getByText(/Couldn.t load tickets/)).toBeTruthy();
    // The action's error string surfaces in the description.
    expect(
      screen.getByText("Database error: relation does not exist")
    ).toBeTruthy();

    // The happy-path table must NOT render on the error branch.
    expect(screen.queryByRole("table")).toBeNull();
  });
});
