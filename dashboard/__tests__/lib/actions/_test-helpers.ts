import { vi, expect } from "vitest";
import type { ActionResult } from "@/lib/types";

// ---------------------------------------------------------------------------
// Supabase chain mock helpers
// ---------------------------------------------------------------------------

/**
 * Spies for the `ticket` query chains.
 *
 * - Read list: `.from("ticket").select("*").eq("guildId", ...).order(...).limit(50)`
 * - Read one:  `.from("ticket").select(...).eq("id", ...).single()`
 * - Mutate:    `.from("ticket").update({...}).eq("id", ...)`
 *
 * Exposed on the returned mock client as `client.ticket` so tests can assert
 * the exact query shape (guild filter, ordering, hard limit, update payload)
 * in addition to the resolved data/error payload.
 */
export interface TicketChainSpies {
  select: ReturnType<typeof vi.fn>;
  eq: ReturnType<typeof vi.fn>;
  order: ReturnType<typeof vi.fn>;
  limit: ReturnType<typeof vi.fn>;
  single: ReturnType<typeof vi.fn>;
  update: ReturnType<typeof vi.fn>;
  updateEq: ReturnType<typeof vi.fn>;
}

/**
 * Spies for the `ticket_note` query chains.
 *
 * - Read list:  `.from("ticket_note").select("*").eq("ticketId", ...).order(...).limit(50)`
 * - Read one:   `.from("ticket_note").select(...).eq("id", ...).single()`
 * - Insert:     `.from("ticket_note").insert({...})`
 * - Delete:     `.from("ticket_note").delete().eq("id", ...)`
 *
 * Exposed on the returned mock client as `client.ticketNote`.
 */
export interface TicketNoteChainSpies {
  select: ReturnType<typeof vi.fn>;
  eq: ReturnType<typeof vi.fn>;
  order: ReturnType<typeof vi.fn>;
  limit: ReturnType<typeof vi.fn>;
  single: ReturnType<typeof vi.fn>;
  insert: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
  deleteEq: ReturnType<typeof vi.fn>;
}

/**
 * Builds a fake Supabase client whose `.from().select().eq().single()`
 * (and similar chains) return the supplied `data` / `error`.
 *
 * Also supports `.from().update().eq()` and `.from().upsert().eq()`.
 *
 * For the read-only ticket view, `.from("ticket").select().eq().order().limit()`
 * returns `overrides.ticketSelectResult` (defaulting to an empty success),
 * and the individual chain steps are exposed as spies on `client.ticket` for
 * query-shape assertions.
 *
 * The `ticket` table also supports `select().eq().single()` (fetch-by-id, used
 * by the ticket-mutation actions to resolve `guildId` before auth) and
 * `update().eq()` (reopen/transfer). The `ticket_note` table supports the
 * list/single/insert/delete chains used by the note actions.
 */
export function buildMockServiceClient(overrides: {
  guildSelectResult?: { data: unknown; error: null } | { data: null; error: Error };
  guildUpdateError?: Error | null;
  economyUpsertError?: Error | null;
  greetingUpsertError?: Error | null;
  ticketSelectResult?: { data: unknown; error: null } | { data: null; error: Error };
  ticketSingleResult?: { data: unknown; error: null } | { data: null; error: Error };
  ticketUpdateResult?: { data: unknown | null; error: Error | null };
  ticketAuditSelectResult?: { data: unknown; error: null } | { data: null; error: Error };
  ticketNoteSelectResult?: { data: unknown; error: null } | { data: null; error: Error };
  ticketNoteSingleResult?: { data: unknown; error: null } | { data: null; error: Error };
  ticketNoteInsertResult?: { data: unknown | null; error: Error | null };
  ticketNoteDeleteResult?: { data: unknown | null; error: Error | null };
}) {
  const eqChain = {
    single: vi.fn().mockResolvedValue(overrides.guildSelectResult ?? { data: null, error: null }),
  };

  const updateEqChain = {
    // For update().eq()
    then: vi.fn(),
  };

  // Make updateEqChain thenable so await works.
  Object.defineProperty(updateEqChain, "then", {
    value: (resolve: (v: unknown) => void) =>
      resolve(overrides.guildUpdateError ? { error: overrides.guildUpdateError } : { error: null }),
    writable: true,
  });

  const upsertEqChainEconomy = {
    then: vi.fn(),
  };

  Object.defineProperty(upsertEqChainEconomy, "then", {
    value: (resolve: (v: unknown) => void) =>
      resolve(overrides.economyUpsertError ? { error: overrides.economyUpsertError } : { error: null }),
    writable: true,
  });

  const upsertEqChainGreeting = {
    then: vi.fn(),
  };

  Object.defineProperty(upsertEqChainGreeting, "then", {
    value: (resolve: (v: unknown) => void) =>
      resolve(overrides.greetingUpsertError ? { error: overrides.greetingUpsertError } : { error: null }),
    writable: true,
  });

  // Ticket read chain: select -> eq -> order -> limit (terminal, thenable).
  // Each step is a stable spy so tests can assert call args after the action runs.
  const ticketLimit = vi
    .fn()
    .mockResolvedValue(overrides.ticketSelectResult ?? { data: [], error: null });
  const ticketOrder = vi.fn().mockReturnValue({ limit: ticketLimit });
  // `eq()` branches to either `.order()` (list) or `.single()` (fetch-by-id).
  const ticketSingle = vi
    .fn()
    .mockResolvedValue(overrides.ticketSingleResult ?? { data: null, error: null });
  const ticketEq = vi.fn().mockReturnValue({ order: ticketOrder, single: ticketSingle });
  const ticketSelect = vi.fn().mockReturnValue({ eq: ticketEq });
  // Ticket update chain: update({...}) -> eq("id", ...) (terminal, thenable).
  const ticketUpdateEq = vi
    .fn()
    .mockResolvedValue(overrides.ticketUpdateResult ?? { data: null, error: null });
  const ticketUpdate = vi.fn().mockReturnValue({ eq: ticketUpdateEq });

  // Ticket-note chains.
  const ticketNoteLimit = vi
    .fn()
    .mockResolvedValue(overrides.ticketNoteSelectResult ?? { data: [], error: null });
  const ticketNoteOrder = vi.fn().mockReturnValue({ limit: ticketNoteLimit });
  const ticketNoteSingle = vi
    .fn()
    .mockResolvedValue(overrides.ticketNoteSingleResult ?? { data: null, error: null });
  const ticketNoteEq = vi.fn().mockReturnValue({
    order: ticketNoteOrder,
    single: ticketNoteSingle,
  });
  const ticketNoteSelect = vi.fn().mockReturnValue({ eq: ticketNoteEq });
  const ticketNoteInsert = vi
    .fn()
    .mockResolvedValue(overrides.ticketNoteInsertResult ?? { data: null, error: null });
  const ticketNoteDeleteEq = vi
    .fn()
    .mockResolvedValue(overrides.ticketNoteDeleteResult ?? { data: null, error: null });
  const ticketNoteDelete = vi.fn().mockReturnValue({ eq: ticketNoteDeleteEq });

  // Ticket audit chain: select -> eq("guildId") -> [eq("ticketId")] -> order -> range (terminal).
  // `eq` is chainable so the optional per-ticket filter (`.eq("ticketId", id)`)
  // before `.order()` works against the same builder.
  const ticketAuditRange = vi
    .fn()
    .mockResolvedValue(overrides.ticketAuditSelectResult ?? { data: [], error: null });
  const ticketAuditOrder = vi.fn().mockReturnValue({ range: ticketAuditRange });
  // `eq` returns a builder with `eq` (self, for chaining) + `order` (terminal-ish).
  const ticketAuditEq = vi.fn();
  const ticketAuditBuilder = { eq: ticketAuditEq, order: ticketAuditOrder };
  ticketAuditEq.mockReturnValue(ticketAuditBuilder);
  const ticketAuditSelect = vi.fn().mockReturnValue({ eq: ticketAuditEq });

  return {
    from: vi.fn((table: string) => {
      if (table === "guild") {
        return {
          select: vi.fn().mockReturnValue({
            eq: vi.fn().mockReturnValue(eqChain),
          }),
          update: vi.fn().mockReturnValue({
            eq: vi.fn().mockReturnValue(updateEqChain),
          }),
        };
      }
      if (table === "economy_config") {
        return {
          upsert: vi.fn().mockReturnValue({
            eq: vi.fn().mockReturnValue(upsertEqChainEconomy),
          }),
        };
      }
      if (table === "greeting_config") {
        return {
          upsert: vi.fn().mockReturnValue({
            eq: vi.fn().mockReturnValue(upsertEqChainGreeting),
          }),
        };
      }
      if (table === "ticket") {
        return { select: ticketSelect, update: ticketUpdate };
      }
      if (table === "ticket_note") {
        return {
          select: ticketNoteSelect,
          insert: ticketNoteInsert,
          delete: ticketNoteDelete,
        };
      }
      if (table === "ticket_audit") {
        return { select: ticketAuditSelect };
      }
      return {};
    }),
    // Test-only handle exposing the stable ticket-chain spies for assertions.
    ticket: {
      select: ticketSelect,
      eq: ticketEq,
      order: ticketOrder,
      limit: ticketLimit,
      single: ticketSingle,
      update: ticketUpdate,
      updateEq: ticketUpdateEq,
    } satisfies TicketChainSpies,
    // Test-only handle exposing the stable ticket-note-chain spies for assertions.
    ticketNote: {
      select: ticketNoteSelect,
      eq: ticketNoteEq,
      order: ticketNoteOrder,
      limit: ticketNoteLimit,
      single: ticketNoteSingle,
      insert: ticketNoteInsert,
      delete: ticketNoteDelete,
      deleteEq: ticketNoteDeleteEq,
    } satisfies TicketNoteChainSpies,
    // Test-only handle exposing the stable ticket-audit-chain spies.
    ticketAudit: {
      select: ticketAuditSelect,
      eq: ticketAuditEq,
      order: ticketAuditOrder,
      range: ticketAuditRange,
    },
  };
}

// ---------------------------------------------------------------------------
// Auth session helpers
// ---------------------------------------------------------------------------

export function buildAuthSession(overrides: {
  hasSession: boolean;
  hasProviderToken: boolean;
  /**
   * Discord user ID to surface as `session.user.identities[0].id` (and
   * `session.user.id`). Defaults to a stable snowflake so actions that read
   * the author identity (e.g. addTicketNote) get a deterministic value.
   */
  discordUserId?: string;
}) {
  if (!overrides.hasSession) {
    return { data: { session: null } };
  }
  const discordUserId = overrides.discordUserId ?? "111222333444555666";
  return {
    data: {
      session: {
        provider_token: overrides.hasProviderToken ? "discord-token-abc" : null,
        user: {
          id: discordUserId,
          identities: [{ id: discordUserId, provider: "discord" }],
        },
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Discord mock helpers
// ---------------------------------------------------------------------------

export function buildDiscordMocks(adminGuildId: string) {
  const fetchUserGuilds = vi
    .fn()
    .mockResolvedValue([
      { id: adminGuildId, permissions: "8" },
      { id: "222", permissions: "1024" },
    ]);

  const hasAdministratorPerm = vi.fn((perm: string) => {
    const permsBigInt = BigInt(perm);
    const ADMINISTRATOR = BigInt(0x8);
    return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
  });

  return { fetchUserGuilds, hasAdministratorPerm };
}

// ---------------------------------------------------------------------------
// FormData builder
// ---------------------------------------------------------------------------

export function buildFormData(entries: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(entries)) {
    fd.append(key, value);
  }
  return fd;
}

// ---------------------------------------------------------------------------
// Assertion helpers
// ---------------------------------------------------------------------------

export function assertAuthError(result: ActionResult): void {
  expect(result.success).toBe(false);
  if (!result.success) {
    expect(result.error).toMatch(/authenticated|admin/i);
  }
}

export function assertFieldError(result: ActionResult, field: string): void {
  expect(result.success).toBe(false);
  if (!result.success) {
    expect(result.field).toBe(field);
  }
}

export function assertSuccess(result: ActionResult): void {
  expect(result.success).toBe(true);
  if (result.success) {
    expect(result.message).toBeTruthy();
  }
}
