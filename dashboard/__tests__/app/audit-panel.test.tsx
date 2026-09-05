import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
} from "@testing-library/react";
import type { TicketAudit } from "@/lib/types";
import { AuditPanel } from "@/app/(authenticated)/guilds/[guildId]/tickets/_components/AuditPanel";

/**
 * AuditPanel — paginated, guild-scoped view of `ticket_audit` rows (PR3
 * TI-038 / TI-021 / TI-028). Newest first, paginated, accessible outcome
 * badges (success=green, denied=amber, error=red) — the outcome is conveyed
 * by text, not color alone.
 *
 * Wait discipline: await rendered output ("Page N", row text, disabled
 * buttons) before asserting on mock calls — "Page 1" is on the first paint,
 * so page-1 assertions must wait for the rows to land. Never assert mock
 * call counts before the UI shows the resulting state.
 */

const mockGetTicketAudit = vi.fn();

vi.mock("@/lib/actions/ticket-actions", () => ({
  getTicketAudit: (...args: unknown[]) => mockGetTicketAudit(...args),
}));

const GUILD_ID = "123456789012345678";

function buildAuditRow(overrides: Partial<TicketAudit> = {}): TicketAudit {
  return {
    action: "claim",
    actorId: "900000000000000001",
    createdAt: "2026-07-01T12:00:00.000Z",
    guildId: GUILD_ID,
    id: crypto.randomUUID(),
    outcome: "success",
    reason: null,
    ticketId: "ticket-uuid-0001",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AuditPanel — load + list (TI-038)", () => {
  it("fetches audit rows for the guild on mount, newest first", async () => {
    const rows: TicketAudit[] = [
      buildAuditRow({ action: "close", createdAt: "2026-07-02T00:00:00.000Z", id: "a2" }),
      buildAuditRow({ action: "claim", createdAt: "2026-07-01T00:00:00.000Z", id: "a1" }),
    ];
    mockGetTicketAudit.mockResolvedValue({ data: rows, error: null });

    render(<AuditPanel guildId={GUILD_ID} />);

    // UI-first: wait for the rendered rows, then assert the fetch contract.
    expect(await screen.findByText("close")).toBeTruthy();
    expect(screen.getByText("claim")).toBeTruthy();
    expect(mockGetTicketAudit).toHaveBeenCalledWith(GUILD_ID, undefined, 1);
  });

  it("passes the optional ticketId filter through to the action", async () => {
    mockGetTicketAudit.mockResolvedValue({ data: [], error: null });
    render(<AuditPanel guildId={GUILD_ID} ticketId="t-42" />);
    expect(await screen.findByText(/No audit events yet/iu)).toBeTruthy();
    expect(mockGetTicketAudit).toHaveBeenCalledWith(GUILD_ID, "t-42", 1);
  });

  it("shows the empty state when there are no audit rows", async () => {
    mockGetTicketAudit.mockResolvedValue({ data: [], error: null });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/No audit events yet/iu)).toBeTruthy();
  });

  it("shows the load error when the action errors", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: null,
      error: "Database error: permission denied",
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/permission denied/iu)).toBeTruthy();
  });
});

describe("AuditPanel — outcome badges are accessible (TI-028 visual)", () => {
  it("renders a success badge with accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ outcome: "success" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/success/iu)).toBeTruthy();
  });

  it("renders a denied badge with the reason and accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [
        buildAuditRow({
          action: "claim",
          outcome: "denied",
          reason: "Already claimed",
        }),
      ],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/denied/iu)).toBeTruthy();
    expect(screen.getByText("Already claimed")).toBeTruthy();
  });

  it("renders an error badge with accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ outcome: "error", reason: "boom" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/error/iu)).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();
  });
});

describe("AuditPanel — pagination (TI-038)", () => {
  it("enables Next and fetches page 2 on click", async () => {
    // Page 1 returns a full page (AUDIT_PAGE_SIZE = 20) → Next enabled.
    const fullPage: TicketAudit[] = Array.from({ length: 20 }, (_, i) =>
      buildAuditRow({ action: "claim", id: `p1-${i}` })
    );
    mockGetTicketAudit.mockResolvedValueOnce({ data: fullPage, error: null });
    mockGetTicketAudit.mockResolvedValueOnce({ data: [], error: null });

    render(<AuditPanel guildId={GUILD_ID} />);

    // UI-first: all 20 page-1 rows rendered proves the page fully landed
    // (and is full) before we read the Next button — "Page 1" text alone
    // is on the first paint.
    const page1Rows = await screen.findAllByText("claim");
    expect(page1Rows).toHaveLength(20);
    const next = screen.getByRole("button", { name: /Next/iu });
    expect(next.hasAttribute("disabled")).toBe(false);

    fireEvent.click(next);
    // Same asserts as before, reordered after the UI settles (design.md).
    expect(await screen.findByText(/Page 2/iu)).toBeTruthy();
    expect(mockGetTicketAudit).toHaveBeenNthCalledWith(2, GUILD_ID, undefined, 2);
  });

  it("disables Next when the current page is not full", async () => {
    // A short page (fewer than PAGE_SIZE) means there is no next page.
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ action: "claim", id: "only" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    // Short page renders exactly 1 row → the page landed and Next is off.
    const pageRows = await screen.findAllByText("claim");
    expect(pageRows).toHaveLength(1);
    expect(screen.getByRole("button", { name: /Next/iu }).hasAttribute("disabled")).toBe(true);
  });

  it("disables Previous on page 1 and enables it on page 2", async () => {
    const fullPage: TicketAudit[] = Array.from({ length: 20 }, (_, i) =>
      buildAuditRow({ action: "claim", id: `p1-${i}` })
    );
    mockGetTicketAudit.mockResolvedValueOnce({ data: fullPage, error: null });
    mockGetTicketAudit.mockResolvedValueOnce({ data: [], error: null });

    render(<AuditPanel guildId={GUILD_ID} />);
    // UI-first: all 20 page-1 rows rendered before reading the Previous button.
    const page1Rows = await screen.findAllByText("claim");
    expect(page1Rows).toHaveLength(20);
    expect(screen.getByRole("button", { name: /Previous/iu }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Next/iu }));
    expect(await screen.findByText(/Page 2/iu)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Previous/iu }).hasAttribute("disabled")).toBe(false);
  });
});