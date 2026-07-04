"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  getTicketNotes,
  addTicketNote,
  deleteTicketNote,
} from "@/lib/actions/ticket-actions";
import type { TicketNote } from "@/lib/types";

/**
 * v1 hard cap. The server action already caps the result at 50; this constant
 * is surfaced only so the footer can tell staff how close they are to it.
 */
const NOTES_CAP = 50;

/**
 * Collapsible staff-notes panel for a single ticket.
 *
 * Mounted on demand by {@link TicketRowActions} when a staff member toggles
 * the Notes button. Fetches notes on mount, lists them newest-first
 * (author / content / timestamp), supports add + delete, and renders a real
 * empty state ("No staff notes yet.") rather than a blank panel.
 *
 * Staff-only by construction: the page only renders rows for administrators
 * (the data action auth-gates), so this panel is never reachable by a
 * non-admin.
 */
export function NotesPanel({ ticketId }: { ticketId: string }) {
  const [notes, setNotes] = useState<TicketNote[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function loadNotes() {
    setIsLoading(true);
    setLoadError(null);
    const result = await getTicketNotes(ticketId);
    if (result.error) {
      setLoadError(result.error);
      setNotes([]);
    } else {
      setNotes(result.data);
    }
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
    if (!content) return;
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
          {notes.map((note) => (
            <li key={note.id} className="space-y-0.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-muted-foreground">
                  {note.authorId}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => handleDelete(note.id)}
                  disabled={deletingId === note.id}
                  aria-label={`Delete note by ${note.authorId}`}
                >
                  Delete
                </Button>
              </div>
              <p className="text-foreground">{note.content}</p>
              <p className="text-muted-foreground">
                {new Date(note.createdAt).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
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
      {notes !== null && notes.length > 0 && (
        <p className="text-[0.65rem] text-muted-foreground">
          Showing {notes.length} of {NOTES_CAP}.
        </p>
      )}
    </div>
  );
}
