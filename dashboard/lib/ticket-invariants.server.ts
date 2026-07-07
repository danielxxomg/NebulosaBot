import "server-only";
import { createHash } from "node:crypto";

import { NOTE_DEDUP_WINDOW_SECONDS } from "./ticket-invariants";

/**
 * Server-only note-dedup helpers — the normalized-content SHA256 hash that the
 * dashboard service-role actions use to detect duplicate notes from the same
 * author within the 2s window (decision #9 / engram #669).
 *
 * Split out of {@link TicketInvariants} (`ticket-invariants.ts`) because it
 * uses `node:crypto`, which MUST NOT enter the browser bundle. The base module
 * stays client-safe so {@link NotesPanel} can import `NOTE_CAP` for the capped
 * add-form UX without pulling Node here.
 *
 * Mirrors `compute_note_hash` / `is_duplicate_note` in
 * `bot/services/ticket_invariants.py` exactly.
 */

/**
 * Return the SHA256 hex digest of normalized note `content`.
 *
 * Normalization = `content.trim().toLowerCase().split(/\s+/).join(" ")` —
 * trim, lowercase, collapse all internal whitespace runs to a single space.
 * This mirrors `" ".join(content.strip().lower().split())` from the Python
 * helper and makes `"  Hello   World  "` hash identically to `"hello world"`.
 */
export function computeNoteHash(content: string): string {
  const normalized = content.trim().toLowerCase().split(/\s+/).join(" ");
  return createHash("sha256").update(normalized, "utf8").digest("hex");
}

/**
 * Return `true` if `newHash` matches a recent same-author note.
 *
 * The caller is expected to fetch recent same-author notes within the window
 * (author + time filtering are enforced upstream by the dashboard action's
 * query) and pass their precomputed hashes here. This function performs only
 * the hash membership comparison — keeping it pure and trivially testable,
 * mirroring `is_duplicate_note` in Python.
 */
export function isDuplicateNote(
  newHash: string,
  _authorId: string,
  existingNoteHashes: string[],
  _windowSeconds: number = NOTE_DEDUP_WINDOW_SECONDS
): boolean {
  return existingNoteHashes.includes(newHash);
}