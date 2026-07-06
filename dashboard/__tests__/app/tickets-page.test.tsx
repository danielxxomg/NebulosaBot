import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  within,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import type { Ticket, TicketNote, TicketStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetTicketsForGuild = vi.fn();
const mockGetReopenGuidance = vi.fn();
const mockTransferTicket = vi.fn();
const mockGetTicketNotes = vi.fn();
const mockAddTicketNote = vi.fn();
const mockDeleteTicketNote = vi.fn();
const mockGetCurrentUserId = vi.fn();
const mockGetTicketAudit = vi.fn();
const mockRouterRefresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRouterRefresh }),
}));

vi.mock("@/lib/actions/ticket-actions", () => ({
  getTicketsForGuild: (...args: unknown[]) => mockGetTicketsForGuild(...args),
  getReopenGuidance: (...args: unknown[]) => mockGetReopenGuidance(...args),
  transferTicket: (...args: unknown[]) => mockTransferTicket(...args),
  getTicketNotes: (...args: unknown[]) => mockGetTicketNotes(...args),
  addTicketNote: (...args: unknown[]) => mockAddTicketNote(...args),
  deleteTicketNote: (...args: unknown[]) => mockDeleteTicketNote(...args),
  getCurrentUserId: (...args: unknown[]) => mockGetCurrentUserId(...args),
  getTicketAudit: (...args: unknown[]) => mockGetTicketAudit(...args),
}));

import TicketsPage from "@/app/(authenticated)/guilds/[guildId]/tickets/page";
import { buildTicketTree } from "@/app/(authenticated)/guilds/[guildId]/tickets/_lib/build-ticket-tree";
import { TicketRowActions } from "@/app/(authenticated)/guilds/[guildId]/tickets/_components/TicketRowActions";
import { NotesPanel } from "@/app/(authenticated)/guilds/[guildId]/tickets/_components/NotesPanel";

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
    parentId: null,
    ...overrides,
  };
}

function buildNote(overrides: Partial<TicketNote> = {}): TicketNote {
  return {
    id: crypto.randomUUID(),
    ticketId: "t1",
    authorId: "111",
    content: "Sample note",
    createdAt: "2025-03-01T12:00:00.000Z",
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
  // Defaults: mutation/read actions succeed; notes start empty. Tests that
  // need different shapes override these after clearAllMocks.
  mockGetReopenGuidance.mockResolvedValue({
    data: { ticketNumber: 3, command: "/reopen ticket:#0003" },
    error: null,
  });
  mockTransferTicket.mockResolvedValue({ data: null, error: null });
  mockGetTicketNotes.mockResolvedValue({ data: [], error: null });
  mockAddTicketNote.mockResolvedValue({ data: null, error: null });
  mockDeleteTicketNote.mockResolvedValue({ data: null, error: null });
  mockGetCurrentUserId.mockResolvedValue("111");
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

  it("renders the Unknown fallback badge for an unrecognized status without crashing", async () => {
    // page.tsx:49 — `STATUS_BADGES[status] ?? NEUTRAL_BADGE`. A runtime value
    // outside the typed union (e.g. a future "deleted" status) must fall back
    // to the neutral "Unknown" pill, not crash. Spec: Unknown status fallback.
    const ticket = buildTicket({
      ticketNumber: 42,
      status: "deleted" as Ticket["status"],
    });

    mockGetTicketsForGuild.mockResolvedValue({ data: [ticket], error: null });

    await renderPage();

    const table = screen.getByRole("table");
    expect(within(table).getByText("Unknown")).toBeTruthy();
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

// ---------------------------------------------------------------------------
// Sub-ticket tree — pure builder
// ---------------------------------------------------------------------------

describe("buildTicketTree — parent/child grouping", () => {
  it("groups children under their parent and keeps the parent as the only root", () => {
    const parent = buildTicket({ id: "p1", ticketNumber: 5 });
    const childA = buildTicket({ id: "c1", ticketNumber: 6, parentId: "p1" });
    const childB = buildTicket({ id: "c2", ticketNumber: 7, parentId: "p1" });

    const tree = buildTicketTree([parent, childA, childB]);

    expect(tree).toHaveLength(1);
    expect(tree[0].ticket.id).toBe("p1");
    expect(tree[0].children.map((c) => c.id)).toEqual(["c1", "c2"]);
  });

  it("degrades an orphan child (parent not in the set) to a top-level root", () => {
    const orphan = buildTicket({
      id: "o1",
      ticketNumber: 9,
      parentId: "missing-parent",
    });

    const tree = buildTicketTree([orphan]);

    expect(tree).toHaveLength(1);
    expect(tree[0].ticket.id).toBe("o1");
    expect(tree[0].children).toEqual([]);
  });

  it("treats flat tickets (no parentId) as independent top-level roots", () => {
    const a = buildTicket({ id: "a", ticketNumber: 1 });
    const b = buildTicket({ id: "b", ticketNumber: 2 });

    const tree = buildTicketTree([a, b]);

    expect(tree).toHaveLength(2);
    expect(tree[0].children).toEqual([]);
    expect(tree[1].children).toEqual([]);
  });

  it("still attaches a child to its parent when the child appears first in the input", () => {
    const parent = buildTicket({ id: "p1", ticketNumber: 5 });
    const child = buildTicket({ id: "c1", ticketNumber: 6, parentId: "p1" });

    const tree = buildTicketTree([child, parent]);

    expect(tree).toHaveLength(1);
    expect(tree[0].ticket.id).toBe("p1");
    expect(tree[0].children.map((c) => c.id)).toEqual(["c1"]);
  });
});

// ---------------------------------------------------------------------------
// Sub-ticket tree — page rendering
// ---------------------------------------------------------------------------

describe("TicketsPage — sub-ticket tree rendering", () => {
  it("renders children indented under their parent with a sub-ticket label", async () => {
    const parent = buildTicket({ id: "p1", ticketNumber: 5, status: "open" });
    const childA = buildTicket({
      id: "c1",
      ticketNumber: 6,
      parentId: "p1",
      status: "open",
    });
    const childB = buildTicket({
      id: "c2",
      ticketNumber: 7,
      parentId: "p1",
      status: "open",
    });

    mockGetTicketsForGuild.mockResolvedValue({
      data: [parent, childA, childB],
      error: null,
    });

    await renderPage();

    // Parent + both children render their ticket numbers.
    expect(screen.getByText("#5")).toBeTruthy();
    expect(screen.getByText("#6")).toBeTruthy();
    expect(screen.getByText("#7")).toBeTruthy();

    // Each child carries an accessible label naming its parent (two children
    // → two labels). This is the semantic signal that the row is a sub-ticket;
    // the visual indentation/connector is a non-asserted enhancement.
    expect(screen.getAllByText("Sub-ticket of #5")).toHaveLength(2);
  });

  it("renders an orphan child as a top-level row with no sub-ticket label", async () => {
    const orphan = buildTicket({
      id: "o1",
      ticketNumber: 9,
      parentId: "missing",
      status: "open",
    });

    mockGetTicketsForGuild.mockResolvedValue({
      data: [orphan],
      error: null,
    });

    await renderPage();

    expect(screen.getByText("#9")).toBeTruthy();
    expect(screen.queryAllByText(/Sub-ticket of/)).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Non-admin / error branch — no action buttons leak
// ---------------------------------------------------------------------------

describe("TicketsPage — action buttons gated by auth", () => {
  it("renders no Reopen/Transfer/Notes buttons when the action rejects the caller", async () => {
    // A non-admin or unauthenticated caller gets an error and no data, so the
    // table never renders and no action UI is reachable.
    mockGetTicketsForGuild.mockResolvedValue({
      data: null,
      error: "You must be a server administrator to view tickets.",
    });

    await renderPage();

    expect(screen.queryByRole("button", { name: "Reopen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Transfer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Notes" })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// TicketRowActions — visibility + action calls
// ---------------------------------------------------------------------------

describe("TicketRowActions — visibility and action calls", () => {
  it("shows Reopen only for a closed ticket and hides it for an open one", () => {
    const closed = buildTicket({
      id: "t1",
      ticketNumber: 3,
      status: "closed",
      closedAt: "2025-02-01T00:00:00.000Z",
    });
    const { rerender } = render(<TicketRowActions ticket={closed} />);
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeNull();

    const open = buildTicket({ id: "t2", ticketNumber: 4, status: "open" });
    rerender(<TicketRowActions ticket={open} />);
    expect(screen.queryByRole("button", { name: "Reopen" })).toBeNull();
  });

  it("shows a Transfer button for a claimed ticket", () => {
    const claimed = buildTicket({
      id: "t1",
      ticketNumber: 5,
      status: "claimed",
      claimedBy: "777",
    });
    render(<TicketRowActions ticket={claimed} />);
    expect(
      screen.queryByRole("button", { name: "Transfer" })
    ).not.toBeNull();
  });

  it("calls getReopenGuidance with the ticket id and shows the command when Reopen is clicked (TI-029)", async () => {
    mockGetReopenGuidance.mockResolvedValue({
      data: { ticketNumber: 3, command: "/reopen ticket:#0003" },
      error: null,
    });
    const ticket = buildTicket({
      id: "t1",
      ticketNumber: 3,
      status: "closed",
      closedAt: "2025-02-01T00:00:00.000Z",
    });

    render(<TicketRowActions ticket={ticket} />);
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));

    await waitFor(() => {
      expect(mockGetReopenGuidance).toHaveBeenCalledWith("t1");
    });
    expect(await screen.findByText("/reopen ticket:#0003")).toBeTruthy();
  });

  it("shows the category-not-configured error and no command when getReopenGuidance errors (TI-030)", async () => {
    mockGetReopenGuidance.mockResolvedValue({
      data: null,
      error: "Ticket category is not configured.",
    });
    const ticket = buildTicket({
      id: "t1",
      ticketNumber: 3,
      status: "closed",
      closedAt: "2025-02-01T00:00:00.000Z",
    });

    render(<TicketRowActions ticket={ticket} />);
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));

    await waitFor(() => {
      expect(mockGetReopenGuidance).toHaveBeenCalledWith("t1");
    });
    expect(
      await screen.findByText(/Ticket category is not configured/i)
    ).toBeTruthy();
    expect(screen.queryByText(/\/reopen ticket:/)).toBeNull();
  });

  it("calls transferTicket with the ticket id and entered staff id", async () => {
    mockTransferTicket.mockResolvedValue({ data: null, error: null });
    const ticket = buildTicket({
      id: "t1",
      ticketNumber: 5,
      status: "claimed",
      claimedBy: "777",
    });

    render(<TicketRowActions ticket={ticket} />);
    fireEvent.click(screen.getByRole("button", { name: "Transfer" }));

    const input = await screen.findByLabelText("New staff member ID");
    fireEvent.change(input, { target: { value: "999" } });

    // Wait for the confirm button to be enabled (it is disabled while the
    // staff-id field is empty) before submitting the form.
    await waitFor(() => {
      const confirm = screen.getByRole("button", {
        name: "Confirm transfer",
      });
      expect(confirm.hasAttribute("disabled")).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm transfer" }));

    await waitFor(() => {
      expect(mockTransferTicket).toHaveBeenCalledWith("t1", "999");
    });
  });

  it("always renders a Notes button that toggles the notes panel open", async () => {
    mockGetTicketNotes.mockResolvedValue({ data: [], error: null });
    const ticket = buildTicket({ id: "t1", ticketNumber: 1, status: "open" });

    render(<TicketRowActions ticket={ticket} />);

    // Panel is not mounted before the toggle.
    expect(screen.queryByText(/No staff notes yet/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Notes" }));

    // Panel mounts → notes are fetched → empty state renders.
    expect(await screen.findByText(/No staff notes yet/)).toBeTruthy();
    expect(mockGetTicketNotes).toHaveBeenCalledWith("t1");
  });
});

// ---------------------------------------------------------------------------
// NotesPanel — empty / list / add / delete
// ---------------------------------------------------------------------------

describe("NotesPanel — empty / list / add / delete", () => {
  it("shows the empty state and fetches notes on mount", async () => {
    mockGetTicketNotes.mockResolvedValue({ data: [], error: null });

    render(<NotesPanel ticketId="t1" />);

    expect(await screen.findByText(/No staff notes yet/)).toBeTruthy();
    expect(mockGetTicketNotes).toHaveBeenCalledWith("t1");
  });

  it("lists existing notes with author, content, and timestamp", async () => {
    const note = buildNote({
      id: "n1",
      ticketId: "t1",
      authorId: "111",
      content: "Escalating to the dev team",
      createdAt: "2025-03-01T12:00:00.000Z",
    });
    mockGetTicketNotes.mockResolvedValue({ data: [note], error: null });

    render(<NotesPanel ticketId="t1" />);

    expect(
      await screen.findByText("Escalating to the dev team")
    ).toBeTruthy();
    expect(screen.getByText("111")).toBeTruthy();
  });

  it("adds a note by calling addTicketNote and refreshing the list", async () => {
    const added = buildNote({
      id: "n1",
      ticketId: "t1",
      authorId: "111",
      content: "Looks stale",
      createdAt: "2025-03-02T12:00:00.000Z",
    });
    mockGetTicketNotes
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: [added], error: null });
    mockAddTicketNote.mockResolvedValue({ data: null, error: null });

    render(<NotesPanel ticketId="t1" />);

    await screen.findByText(/No staff notes yet/);

    fireEvent.change(screen.getByLabelText("Note content"), {
      target: { value: "Looks stale" },
    });
    // Confirm the submit button is enabled (empty draft disables it) before
    // clicking, then submit.
    await waitFor(() => {
      const addBtn = screen.getByRole("button", { name: "Add note" });
      expect(addBtn.hasAttribute("disabled")).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() => {
      expect(mockAddTicketNote).toHaveBeenCalledWith("t1", "Looks stale");
    });
    expect(await screen.findByText("Looks stale")).toBeTruthy();
  });

  it("deletes a note by calling deleteTicketNote and refreshing the list", async () => {
    const note = buildNote({
      id: "n1",
      ticketId: "t1",
      authorId: "111",
      content: "Old note",
      createdAt: "2025-03-01T12:00:00.000Z",
    });
    mockGetTicketNotes
      .mockResolvedValueOnce({ data: [note], error: null })
      .mockResolvedValueOnce({ data: [], error: null });
    mockDeleteTicketNote.mockResolvedValue({ data: null, error: null });

    render(<NotesPanel ticketId="t1" />);

    await screen.findByText("Old note");

    fireEvent.click(
      screen.getByRole("button", { name: /Delete your note/i })
    );

    await waitFor(() => {
      expect(mockDeleteTicketNote).toHaveBeenCalledWith("n1");
    });
    expect(await screen.findByText(/No staff notes yet/)).toBeTruthy();
  });
});
