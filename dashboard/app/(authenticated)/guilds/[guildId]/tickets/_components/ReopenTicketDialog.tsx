"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { ReopenGuidance } from "@/lib/actions/ticket-actions";

/**
 * "Reopen in Discord" guidance modal (PR3 decision #2a / TI-029 / TI-030).
 *
 * The dashboard CANNOT reopen a ticket itself — the original ticket channel
 * is deleted on close, so a DB-only status flip would create a zombie ticket
 * with no channel. Instead, this modal hands the admin a copyable command to
 * run the bot's `/reopen` (which creates the new channel).
 *
 * Two states:
 * - **guidance** (`guidance` set, `error` null): shows the ticket number
 *   (zero-padded to 4 digits) and the literal command `/reopen ticket:#<n>`.
 * - **error** (`error` set, `guidance` null): shows the error and NO command.
 *   Per TI-030 a missing `ticketCategoryId` returns "Ticket category is not
 *   configured" and the modal MUST NOT render any command line.
 *
 * Uses the native `<dialog>` element to escape any parent `overflow: hidden` /
 * `overflow: auto` stacking context (per impeccable) and to get focus + ESC
 * semantics for free. A custom backdrop handles the click-outside affordance.
 */

interface ReopenTicketDialogProps {
  /** Whether the modal should be open. */
  open: boolean;
  /** Guidance to display on success (null when error / loading). */
  guidance: ReopenGuidance | null;
  /** Error message to display instead of the guidance (null on success). */
  error: string | null;
  /** Called when the user requests to close the modal (button or ESC). */
  onClose: () => void;
}

export function ReopenTicketDialog({
  open,
  guidance,
  error,
  onClose,
}: ReopenTicketDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  // Close on Escape. Using the React `open` attribute (not `showModal()`) keeps
  // the dialog usable under jsdom and renders it as a non-modal popup in the
  // browser — ESC then isn't handled by the UA, so we do it here.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <dialog
      ref={ref}
      open={open}
      aria-labelledby="reopen-dialog-title"
      onClick={(event) => {
        // The backdrop is the dialog element; clicking it (not the panel)
        // closes the modal.
        if (event.target === ref.current) onClose();
      }}
      className="m-auto w-[min(92vw,28rem)] rounded-lg border border-border bg-background p-0 text-foreground shadow-lg backdrop:bg-foreground/50 backdrop:backdrop-blur-[2px]"
    >
      {open && (
        <div className="space-y-4 p-5">
          <div className="space-y-1">
            <h2
              id="reopen-dialog-title"
              className="text-base font-semibold text-foreground"
            >
              Reopen in Discord
            </h2>
            <p className="text-sm text-muted-foreground">
              Reopening recreates the ticket channel on the Discord side. Run
              the command below in any channel of your server.
            </p>
          </div>

          {error ? (
            <div
              role="alert"
              className="space-y-1 rounded-md bg-destructive/10 p-3 ring-1 ring-destructive/30"
            >
              <p className="text-sm font-medium text-destructive">{error}</p>
              <p className="text-xs text-muted-foreground">
                Configure a ticket category in the guild settings before
                reopening.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">Ticket</dt>
                <dd className="font-mono font-medium text-foreground">
                  #{String(guidance?.ticketNumber ?? 0).padStart(4, "0")}
                </dd>
                <dt className="text-muted-foreground">Command</dt>
                <dd>
                  <code className="block w-full break-all rounded bg-muted px-2 py-1.5 font-mono text-xs text-foreground">
                    {guidance?.command ?? ""}
                  </code>
                </dd>
              </dl>
              <p className="text-xs text-muted-foreground">
                Right-click the command to copy it.
              </p>
            </div>
          )}

          <div className="flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      )}
    </dialog>
  );
}