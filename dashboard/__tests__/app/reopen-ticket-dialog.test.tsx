import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
} from "@testing-library/react";
import { ReopenTicketDialog } from "@/app/(authenticated)/guilds/[guildId]/tickets/_components/ReopenTicketDialog";
import type { ReopenGuidance } from "@/lib/actions/ticket-actions";

/**
 * ReopenTicketDialog — copyable "Reopen in Discord" guidance modal (PR3
 * decision #2a). Renders a catchable {{command}} block and the zero-padded
 * ticket number; when the category is not configured it shows an error state
 * and NO command (TI-030).
 */

const GUIDANCE: ReopenGuidance = {
  ticketNumber: 3,
  command: "/reopen ticket:#0003",
};

describe("ReopenTicketDialog — guidance view (TI-029)", () => {
  it("renders the headline, the copyable command, and the ticket number", () => {
    render(
      <ReopenTicketDialog
        open
        guidance={GUIDANCE}
        error={null}
        onClose={() => {}}
      />
    );

    expect(screen.getByText(/Reopen in Discord/i)).toBeTruthy();
    expect(screen.getByText("/reopen ticket:#0003")).toBeTruthy();
    // The ticket number cell renders exactly "#0003" (exact match so the
    // command line "/reopen ticket:#0003" doesn't collide).
    expect(screen.getByText("#0003", { exact: true })).toBeTruthy();
  });

  it("calls onClose when the Close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <ReopenTicketDialog
        open
        guidance={GUIDANCE}
        error={null}
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders nothing actionable when open=false (modal hidden)", () => {
    render(
      <ReopenTicketDialog
        open={false}
        guidance={GUIDANCE}
        error={null}
        onClose={() => {}}
      />
    );
    expect(screen.queryByText(/Reopen in Discord/i)).toBeNull();
    expect(screen.queryByText(/\/reopen ticket:#0003/)).toBeNull();
  });
});

describe("ReopenTicketDialog — category-not-configured error (TI-030)", () => {
  it("shows the error message and renders NO command when error is set", () => {
    render(
      <ReopenTicketDialog
        open
        guidance={null}
        error="Ticket category is not configured."
        onClose={() => {}}
      />
    );

    expect(
      screen.getByText(/Ticket category is not configured/i)
    ).toBeTruthy();
    // CRITICAL (TI-030): no command must be shown when the category is missing.
    expect(screen.queryByText(/\/reopen ticket:/)).toBeNull();
    expect(screen.queryByText(/#0003/)).toBeNull();
  });

  it("still allows closing the error modal", () => {
    const onClose = vi.fn();
    render(
      <ReopenTicketDialog
        open
        guidance={null}
        error="Ticket category is not configured."
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});