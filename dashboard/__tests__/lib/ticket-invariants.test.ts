import { describe, it, expect } from "vitest";
import {
  checkCanClaim,
  checkCanClose,
  checkCanReopen,
  checkCanTransfer,
  checkCanAddNote,
  checkCanDeleteNote,
  checkSubticketParent,
  NOTE_CAP,
  NOTE_DEDUP_WINDOW_SECONDS,
} from "@/lib/ticket-invariants";
import { computeNoteHash, isDuplicateNote } from "@/lib/ticket-invariants.server";

/**
 * Pure-logic mirrors of the Python invariant helpers in
 * `bot/services/ticket_invariants.py`. These tests assert the TS mirror
 * matches the contract 1:1 — normalized dedup hash formula, status state
 * machine, transfer rules, note cap, note-delete ownership, and parentId FK
 * invariants. The same ScenarioIDs are exercised end-to-end by the contract
 * suite in `dashboard/__tests__/contract/ticket-invariants.test.ts`.
 */

describe("computeNoteHash — normalization (decision #9)", () => {
  it("collapses whitespace, lowercases, and trims before hashing", () => {
    const a = computeNoteHash("  Hello   World  ");
    const b = computeNoteHash("hello world");
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{64}$/); // sha256 hex
  });

  it("produces a stable hex digest for identical normalized content", () => {
    expect(computeNoteHash("Note")).toBe(computeNoteHash("note"));
    expect(computeNoteHash("A\tB\nC")).toBe(computeNoteHash("a b c"));
  });
});

describe("isDuplicateNote — membership within author window", () => {
  it("returns true when the incoming hash matches a recent same-author hash", () => {
    const h = computeNoteHash("hello world");
    expect(isDuplicateNote(h, "authorA", [h], NOTE_DEDUP_WINDOW_SECONDS)).toBe(true);
  });

  it("returns false when no recent same-author hashes match", () => {
    const h = computeNoteHash("hello");
    expect(isDuplicateNote(h, "authorA", [], NOTE_DEDUP_WINDOW_SECONDS)).toBe(false);
  });

  it("is author-scoped: author B's recent set excludes author A's note", () => {
    const existing = computeNoteHash("hello");
    const incoming = computeNoteHash("hello");
    expect(isDuplicateNote(incoming, "authorB", [], NOTE_DEDUP_WINDOW_SECONDS)).toBe(false);
    expect(isDuplicateNote(incoming, "authorA", [existing], NOTE_DEDUP_WINDOW_SECONDS)).toBe(true);
  });
});

describe("checkCanClaim — status state machine", () => {
  it("allows claiming an open, unclaimed ticket", () => {
    expect(() => checkCanClaim("open", null)).not.toThrow();
  });

  it("rejects claiming a closed ticket", () => {
    expect(() => checkCanClaim("closed", null)).toThrow(/claim/i);
  });

  it("rejects claiming an already-claimed ticket (no-overwrite)", () => {
    expect(() => checkCanClaim("claimed", "userA")).toThrow(/claim/i);
    expect(() => checkCanClaim("claimed", "userB")).toThrow(/claim/i);
  });
});

describe("checkCanClose", () => {
  it("allows closing an open ticket", () => {
    expect(() => checkCanClose("open")).not.toThrow();
  });
  it("allows closing a claimed ticket", () => {
    expect(() => checkCanClose("claimed")).not.toThrow();
  });
  it("rejects closing an already-closed ticket", () => {
    expect(() => checkCanClose("closed")).toThrow(/close/i);
  });
});

describe("checkCanReopen — status guard", () => {
  it("allows reopening a closed ticket", () => {
    expect(() => checkCanReopen("closed")).not.toThrow();
  });
  it.each(["open", "claimed"])("rejects reopening a non-closed ticket (status=%s)", (status) => {
    expect(() => checkCanReopen(status)).toThrow(/reopen/i);
  });
});

describe("checkCanTransfer — reassign + same-user reject", () => {
  it("allows transfer on an open ticket to a new staff member", () => {
    expect(() => checkCanTransfer("open", null, "userB")).not.toThrow();
  });
  it("allows transfer on a claimed ticket to a different staff member", () => {
    expect(() => checkCanTransfer("claimed", "userA", "userB")).not.toThrow();
  });
  it("rejects transferring a closed ticket", () => {
    expect(() => checkCanTransfer("closed", "userA", "userB")).toThrow(/closed/i);
  });
  it("rejects transfer to the same staff member who already claimed it", () => {
    expect(() => checkCanTransfer("claimed", "userA", "userA")).toThrow(/same/i);
  });
  it("rejects transfer without a target", () => {
    expect(() => checkCanTransfer("open", null, null)).toThrow(/target/i);
  });
});

describe("checkCanAddNote — cap enforcement", () => {
  it("allows adding a note under the cap", () => {
    expect(() => checkCanAddNote(30, NOTE_CAP)).not.toThrow();
  });
  it("rejects adding a note at the cap", () => {
    expect(() => checkCanAddNote(NOTE_CAP, NOTE_CAP)).toThrow(/cap/i);
  });
  it("rejects adding a note above the cap", () => {
    expect(() => checkCanAddNote(NOTE_CAP + 5, NOTE_CAP)).toThrow(/cap/i);
  });
});

describe("checkCanDeleteNote — author-only", () => {
  it("allows the author to delete their own note", () => {
    expect(() => checkCanDeleteNote("userA", "userA")).not.toThrow();
  });
  it("rejects deleting another author's note", () => {
    expect(() => checkCanDeleteNote("userA", "userB")).toThrow(/author|owner/i);
  });
});

describe("checkSubticketParent — parentId FK invariants (depth max 2)", () => {
  it("allows a valid parent in the same guild with no parentId", () => {
    const parent = { id: "parent-1", guildId: "guildA", parentId: null };
    expect(() => checkSubticketParent(parent, "guildA", "guildA", "child-1")).not.toThrow();
  });
  it("rejects a missing parent", () => {
    expect(() => checkSubticketParent(null, "guildA", "guildA", "child-1")).toThrow(/parent/i);
  });
  it("rejects a self-referential parent", () => {
    const parent = { id: "t-1", guildId: "guildA", parentId: null };
    expect(() => checkSubticketParent(parent, "guildA", "guildA", "t-1")).toThrow(/self/i);
  });
  it("rejects a parent that is itself a subticket (depth limit)", () => {
    const parent = { id: "parent-1", guildId: "guildA", parentId: "grandparent-1" };
    expect(() => checkSubticketParent(parent, "guildA", "guildA", "child-1")).toThrow(/depth|nested|sub/i);
  });
  it("rejects a cross-guild parent", () => {
    const parent = { id: "parent-1", guildId: "guildA", parentId: null };
    expect(() => checkSubticketParent(parent, "guildA", "guildB", "child-1")).toThrow(/guild/i);
  });
});