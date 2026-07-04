import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUsePathname = vi.fn();

// Wrap the ref in a closure so it is resolved lazily at call time, not when
// the (hoisted) mock factory is evaluated — matches the project's existing
// mock pattern in ticket-actions.test.ts.
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

import { Sidebar } from "@/components/sidebar";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const GUILD_ID = "123456789012345678";
const TICKETS_HREF = `/guilds/${GUILD_ID}/tickets`;

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tickets nav link
// ---------------------------------------------------------------------------

describe("Sidebar — Tickets nav link", () => {
  it("renders a Tickets link pointing to the guild tickets route", () => {
    mockUsePathname.mockReturnValue("/");

    render(<Sidebar guildId={GUILD_ID} />);

    // The label "Tickets" is a direct text child of the `<a>` (next/link),
    // so getByText returns the anchor itself.
    const link = screen.getByText("Tickets").closest("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe(TICKETS_HREF);
  });

  it("applies active styling when the pathname is the tickets route", () => {
    mockUsePathname.mockReturnValue(TICKETS_HREF);

    render(<Sidebar guildId={GUILD_ID} />);

    const link = screen.getByText("Tickets").closest("a");
    // Split into class tokens so the assertion is exact — the inactive
    // branch carries `hover:bg-sidebar-accent/50`, which would falsely
    // match a naive substring check for "bg-sidebar-accent".
    const classes = link?.className.split(/\s+/) ?? [];
    expect(classes).toContain("bg-sidebar-accent");
    expect(classes).toContain("font-medium");
  });

  it("does not apply active styling when the pathname is a different route", () => {
    // Overview route is active, not Tickets.
    mockUsePathname.mockReturnValue(`/guilds/${GUILD_ID}`);

    render(<Sidebar guildId={GUILD_ID} />);

    const link = screen.getByText("Tickets").closest("a");
    const classes = link?.className.split(/\s+/) ?? [];
    expect(classes).not.toContain("bg-sidebar-accent");
  });
});
