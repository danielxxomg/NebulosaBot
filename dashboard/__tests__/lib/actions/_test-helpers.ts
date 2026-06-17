import { vi } from "vitest";
import type { ActionResult } from "@/lib/types";

// ---------------------------------------------------------------------------
// Supabase chain mock helpers
// ---------------------------------------------------------------------------

/**
 * Builds a fake Supabase client whose `.from().select().eq().single()`
 * (and similar chains) return the supplied `data` / `error`.
 *
 * Also supports `.from().update().eq()` and `.from().upsert().eq()`.
 */
export function buildMockServiceClient(overrides: {
  guildSelectResult?: { data: unknown; error: null } | { data: null; error: Error };
  guildUpdateError?: Error | null;
  economyUpsertError?: Error | null;
  greetingUpsertError?: Error | null;
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
      return {};
    }),
  };
}

// ---------------------------------------------------------------------------
// Auth session helpers
// ---------------------------------------------------------------------------

export function buildAuthSession(overrides: {
  hasSession: boolean;
  hasProviderToken: boolean;
}) {
  if (!overrides.hasSession) {
    return { data: { session: null } };
  }
  return {
    data: {
      session: {
        provider_token: overrides.hasProviderToken ? "discord-token-abc" : null,
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
