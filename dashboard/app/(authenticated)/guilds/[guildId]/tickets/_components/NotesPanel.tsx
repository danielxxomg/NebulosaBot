"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  getTicketNotes,
  addTicketNote,
  deleteTicketNote,
  getCurrentUserId,
} from "@/lib/actions/ticket-actions";
import type { TicketNote } from "@/lib/types";
import { NOTE_CAP } from "@/lib/ticket-invariants";

/**
 * Collapsible staff-notes panel for a single ticket.
 *
 * Mounted on demand by {@link TicketRowActions} when a staff member toggles
 * the Notes button. Fetches notes on mount, lists them newest-first
 * (author / content / timestamp), supports add + delete, and renders a real
 * empty state ("No staff notes yet.") rather than a blank panel.
 *
 * Defense-in-depth (PR3 invariants):
 * - **Note cap (TI-031)**: the add-note form is disabled and replaced by a
 *   "Note limit reached (50)" message once the panel sees `NOTE_CAP` notes.
 *   The server action {@link addTicketNote} enforces the cap too; this is the
 *   UX affordance.
 * - **Author-only delete (TI-032 / TI-035)**: the Delete button only renders
 *   for the note's author (the session user's Discord id is loaded via
 *   {@link getCurrentUserId}). The server action {@link deleteTicketNote}
 *   STILL enforces ownership — the hidden button is UX, not a security
 *   boundary (an attempt to bypass it via the network is rejected server-side).
 *
 * Staff-only by construction: the page only renders rows for administrators
 * (the data action auth-gates).
 */
export function NotesPanel({ ticketId }: { ticketId: string }) {
  const [notes, setNotes] = useState<TicketNote[] | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const atCap = notes !== null && notes.length >= NOTE_CAP;

  async function loadNotes() {
    setIsLoading(true);
    setLoadError(null);
    const [notesResult, userResult] = await Promise.all([
      getTicketNotes(ticketId),
      getCurrentUserId(),
    ]);
    if (notesResult.error) {
      setLoadError(notesResult.error);
      setNotes([]);
    } else {
      setNotes(notesResult.data);
    }
    setCurrentUserId(userResult);
    setIsLoading(false);
  }

  // Fetch on mount (and whenever the target ticket changes). The panel is
  // only mounted when open, so this is effectively "load on open".
  useEffect(() => {
    loadNotes();
    // loadNotes is stable per ticketId; deps intentionally minimal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || atCap) return;
    setIsAdding(true);
    const result = await addTicketNote(ticketId, content);
    setIsAdding(false);
    if (result.error) {
      setLoadError(result.error);
      return;
    }
    setDraft("");
    await loadNotes();
  }

  async function handleDelete(noteId: string) {
    setDeletingId(noteId);
    const result = await deleteTicketNote(noteId);
    setDeletingId(null);
    if (result.error) {
      setLoadError(result.error);
      return;
    }
    await loadNotes();
  }

  const showEmpty = !isLoading && notes !== null && notes.length === 0;

  return (
    <div
      id={`ticket-notes-${ticketId}`}
      role="region"
      aria-label="Staff notes"
      className="mt-1 w-64 space-y-2 rounded-md p-2 ring-1 ring-border"
    >
      {isLoading && (
        <p className="text-xs text-muted-foreground">Loading notes…</p>
      )}
      {loadError && (
        <p className="text-xs text-destructive" role="alert">
          {loadError}
        </p>
      )}
      {showEmpty && (
        <p className="text-xs text-muted-foreground">No staff notes yet.</p>
      )}
      {notes !== null && notes.length > 0 && (
        <ul className="space-y-1.5">
          {notes.map((note) => {
            const isOwn = currentUserId !== null && note.authorId === currentUserId;
            return (
              <li key={note.id} className="space-y-0.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-muted-foreground">
                    {note.authorId}
                  </span>
                  {isOwn && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => handleDelete(note.id)}
                      disabled={deletingId === note.id}
                      aria-label={`Delete your note`}
                    >
                      Delete
                    </Button>
                  )}
                </div>
                <p className="text-foreground">{note.content}</p>
                <p className="text-muted-foreground">
                  {new Date(note.createdAt).toLocaleString()}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {atCap ? (
        <p className="text-xs font-medium text-muted-foreground" role="status">
          Note limit reached ({NOTE_CAP}). Delete an existing note to add a new
          one.
        </p>
      ) : (
        <form onSubmit={handleAdd} className="flex flex-col gap-1.5">
          <label
            htmlFor={`note-input-${ticketId}`}
            className="text-xs text-muted-foreground"
          >
            Note content
          </label>
          <input
            id={`note-input-${ticketId}`}
            name="content"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Add an internal note…"
            autoComplete="off"
            disabled={isAdding}
            className="h-7 w-full rounded-md border border-input bg-background px-2 text-xs"
          />
          <Button
            type="submit"
            size="xs"
            disabled={isAdding || draft.trim() === ""}
          >
            {isAdding ? "Adding…" : "Add note"}
          </Button>
        </form>
      )}
      {notes !== null && notes.length > 0 && (
        <p className="text-[0.65rem] text-muted-foreground">
          Showing {notes.length} of {NOTE_CAP}.
        </p>
      )}
    </div>
  );
}