import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import type { TicketAudit } from "@/lib/types";
import { AuditPanel } from "@/app/(authenticated)/guilds/[guildId]/tickets/_components/AuditPanel";

/**
 * AuditPanel — paginated, guild-scoped view of `ticket_audit` rows (PR3
 * TI-038 / TI-021 / TI-028). Newest first, paginated, accessible outcome
 * badges (success=green, denied=amber, error=red) — the outcome is conveyed
 * by text, not color alone.
 */

const mockGetTicketAudit = vi.fn();

vi.mock("@/lib/actions/ticket-actions", () => ({
  getTicketAudit: (...args: unknown[]) => mockGetTicketAudit(...args),
}));

const GUILD_ID = "123456789012345678";

function buildAuditRow(overrides: Partial<TicketAudit> = {}): TicketAudit {
  return {
    id: crypto.randomUUID(),
    guildId: GUILD_ID,
    ticketId: "ticket-uuid-0001",
    action: "claim",
    actorId: "900000000000000001",
    outcome: "success",
    reason: null,
    createdAt: "2026-07-01T12:00:00.000Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AuditPanel — load + list (TI-038)", () => {
  it("fetches audit rows for the guild on mount, newest first", async () => {
    const rows: TicketAudit[] = [
      buildAuditRow({ id: "a2", action: "close", createdAt: "2026-07-02T00:00:00.000Z" }),
      buildAuditRow({ id: "a1", action: "claim", createdAt: "2026-07-01T00:00:00.000Z" }),
    ];
    mockGetTicketAudit.mockResolvedValue({ data: rows, error: null });

    render(<AuditPanel guildId={GUILD_ID} />);

    await waitFor(() => {
      expect(mockGetTicketAudit).toHaveBeenCalledWith(GUILD_ID, undefined, 1);
    });
    expect(await screen.findByText("close")).toBeTruthy();
    expect(screen.getByText("claim")).toBeTruthy();
  });

  it("passes the optional ticketId filter through to the action", async () => {
    mockGetTicketAudit.mockResolvedValue({ data: [], error: null });
    render(<AuditPanel guildId={GUILD_ID} ticketId="t-42" />);
    await waitFor(() => {
      expect(mockGetTicketAudit).toHaveBeenCalledWith(GUILD_ID, "t-42", 1);
    });
  });

  it("shows the empty state when there are no audit rows", async () => {
    mockGetTicketAudit.mockResolvedValue({ data: [], error: null });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/No audit events yet/i)).toBeTruthy();
  });

  it("shows the load error when the action errors", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: null,
      error: "Database error: permission denied",
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/permission denied/i)).toBeTruthy();
  });
});

describe("AuditPanel — outcome badges are accessible (TI-028 visual)", () => {
  it("renders a success badge with accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ outcome: "success" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/success/i)).toBeTruthy();
  });

  it("renders a denied badge with the reason and accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [
        buildAuditRow({
          outcome: "denied",
          action: "claim",
          reason: "Already claimed",
        }),
      ],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/denied/i)).toBeTruthy();
    expect(screen.getByText("Already claimed")).toBeTruthy();
  });

  it("renders an error badge with accessible text", async () => {
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ outcome: "error", reason: "boom" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    expect(await screen.findByText(/error/i)).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();
  });
});

describe("AuditPanel — pagination (TI-038)", () => {
  it("enables Next and fetches page 2 on click", async () => {
    // Page 1 returns a full page (AUDIT_PAGE_SIZE = 20) → Next enabled.
    const fullPage: TicketAudit[] = Array.from({ length: 20 }, (_, i) =>
      buildAuditRow({ id: `p1-${i}`, action: "claim" })
    );
    mockGetTicketAudit.mockResolvedValueOnce({ data: fullPage, error: null });
    mockGetTicketAudit.mockResolvedValueOnce({ data: [], error: null });

    render(<AuditPanel guildId={GUILD_ID} />);

    await screen.findByText(/Page 1/i);
    const next = screen.getByRole("button", { name: /Next/i });
    expect(next.hasAttribute("disabled")).toBe(false);

    fireEvent.click(next);
    await waitFor(() => {
      expect(mockGetTicketAudit).toHaveBeenNthCalledWith(2, GUILD_ID, undefined, 2);
    });
    expect(await screen.findByText(/Page 2/i)).toBeTruthy();
  });

  it("disables Next when the current page is not full", async () => {
    // A short page (fewer than PAGE_SIZE) means there is no next page.
    mockGetTicketAudit.mockResolvedValue({
      data: [buildAuditRow({ id: "only", action: "claim" })],
      error: null,
    });
    render(<AuditPanel guildId={GUILD_ID} />);
    await screen.findByText(/Page 1/i);
    expect(screen.getByRole("button", { name: /Next/i }).hasAttribute("disabled")).toBe(true);
  });

  it("disables Previous on page 1 and enables it on page 2", async () => {
    const fullPage: TicketAudit[] = Array.from({ length: 20 }, (_, i) =>
      buildAuditRow({ id: `p1-${i}`, action: "claim" })
    );
    mockGetTicketAudit.mockResolvedValueOnce({ data: fullPage, error: null });
    mockGetTicketAudit.mockResolvedValueOnce({ data: [], error: null });

    render(<AuditPanel guildId={GUILD_ID} />);
    await screen.findByText(/Page 1/i);
    expect(screen.getByRole("button", { name: /Previous/i }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await screen.findByText(/Page 2/i);
    expect(screen.getByRole("button", { name: /Previous/i }).hasAttribute("disabled")).toBe(false);
  });
});