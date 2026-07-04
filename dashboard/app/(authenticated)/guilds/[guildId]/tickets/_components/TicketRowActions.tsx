"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { reopenTicket, transferTicket } from "@/lib/actions/ticket-actions";
import type { Ticket } from "@/lib/types";
import { NotesPanel } from "./NotesPanel";

/**
 * Per-row action buttons for a ticket.
 *
 * Rendered server-side by the tickets page; the caller is already
 * admin-gated by `getTicketsForGuild`, so this leaf only handles the
 * interactive mutations:
 * - Reopen — visible only when the ticket is closed.
 * - Transfer — visible only when the ticket is open or claimed; opens an
 *   inline form to capture the new staff member's Discord ID.
 * - Notes — always visible; toggles the collapsible {@link NotesPanel}.
 *
 * Every button carries a visible text label so the action is never conveyed
 * by color or icon alone. Loading states disable the button and swap the
 * label to its progressive form ("Reopen" → "Reopening…").
 */
export function TicketRowActions({ ticket }: { ticket: Ticket }) {
  const router = useRouter();
  const [isReopening, startReopenTransition] = useTransition();
  const [isTransferring, startTransferTransition] = useTransition();
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferTarget, setTransferTarget] = useState("");
  const [notesOpen, setNotesOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const canReopen = ticket.status === "closed";
  const canTransfer = ticket.status === "open" || ticket.status === "claimed";

  function handleReopen() {
    setActionError(null);
    startReopenTransition(async () => {
      const result = await reopenTicket(ticket.id);
      if (result.error) {
        setActionError(result.error);
        return;
      }
      router.refresh();
    });
  }

  function handleTransfer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = transferTarget.trim();
    if (!target) return;
    setActionError(null);
    startTransferTransition(async () => {
      const result = await transferTicket(ticket.id, target);
      if (result.error) {
        setActionError(result.error);
        return;
      }
      setTransferOpen(false);
      setTransferTarget("");
      router.refresh();
    });
  }

  return (
    <div className="flex flex-col gap-2">
      {actionError && (
        <p role="alert" className="text-xs text-destructive">
          {actionError}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {canReopen && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleReopen}
            disabled={isReopening}
          >
            {isReopening ? "Reopening…" : "Reopen"}
          </Button>
        )}
        {canTransfer && !transferOpen && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setTransferOpen(true)}
          >
            Transfer
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={notesOpen}
          aria-controls={`ticket-notes-${ticket.id}`}
          onClick={() => setNotesOpen((open) => !open)}
        >
          Notes
        </Button>
      </div>

      {canTransfer && transferOpen && (
        <form onSubmit={handleTransfer} className="flex flex-col gap-1.5">
          <label
            htmlFor={`transfer-target-${ticket.id}`}
            className="text-xs text-muted-foreground"
          >
            New staff member ID
          </label>
          <input
            id={`transfer-target-${ticket.id}`}
            name="staffId"
            value={transferTarget}
            onChange={(event) => setTransferTarget(event.target.value)}
            placeholder="Discord user ID"
            autoComplete="off"
            disabled={isTransferring}
            className="h-7 w-44 rounded-md border border-input bg-background px-2 text-xs"
          />
          <div className="flex items-center gap-1.5">
            <Button
              type="submit"
              size="xs"
              disabled={isTransferring || transferTarget.trim() === ""}
            >
              {isTransferring ? "Transferring…" : "Confirm transfer"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={() => {
                setTransferOpen(false);
                setTransferTarget("");
              }}
              disabled={isTransferring}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {notesOpen && <NotesPanel ticketId={ticket.id} />}
    </div>
  );
}
