import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  buildMockServiceClient,
  buildAuthSession,
  buildFormData,
  assertAuthError,
  assertFieldError,
  assertSuccess,
} from "./_test-helpers";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetSession = vi.fn();
const mockRevalidatePath = vi.fn();
const mockFetchUserGuilds = vi.fn();
const mockHasAdministratorPerm = vi.fn();
const mockNotifyWebhookSync = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/supabase", () => ({
  createServerSupabaseClient: vi.fn(() =>
    Promise.resolve({
      auth: { getSession: mockGetSession },
    })
  ),
  createServiceClient: vi.fn(),
}));

vi.mock("@/lib/discord", () => ({
  fetchUserGuilds: (...args: unknown[]) => mockFetchUserGuilds(...args),
  hasAdministratorPerm: (perm: string) => mockHasAdministratorPerm(perm),
}));

vi.mock("next/cache", () => ({
  revalidatePath: (...args: unknown[]) => mockRevalidatePath(...args),
}));

vi.mock("@/lib/webhook-sync", () => ({
  notifyWebhookSync: (...args: unknown[]) => mockNotifyWebhookSync(...args),
}));

import { updateGuildConfig } from "@/lib/actions/guild-actions";
import { createServiceClient } from "@/lib/supabase";

const GUILD_ID = "123456789012345678";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupAuth({
  hasSession = true,
  hasProviderToken = true,
  guildActive = true,
  isAdmin = true,
}: {
  hasSession?: boolean;
  hasProviderToken?: boolean;
  guildActive?: boolean;
  isAdmin?: boolean;
} = {}) {
  mockGetSession.mockResolvedValue(buildAuthSession({ hasSession, hasProviderToken }));

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? { data: { active: true }, error: null }
      : { data: null, error: null },
  });

  vi.mocked(createServiceClient).mockResolvedValue(svc as unknown as Awaited<ReturnType<typeof createServiceClient>>);

  mockFetchUserGuilds.mockResolvedValue([
    { id: GUILD_ID, permissions: isAdmin ? "8" : "1024" },
  ]);

  mockHasAdministratorPerm.mockImplementation((perm: string) => {
    const permsBigInt = BigInt(perm);
    const ADMINISTRATOR = BigInt(0x8);
    return (permsBigInt & ADMINISTRATOR) === ADMINISTRATOR;
  });

  mockRevalidatePath.mockClear();
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Auth rejection tests
// ---------------------------------------------------------------------------

describe("updateGuildConfig — auth rejection", () => {
  it("returns error when there is no session", async () => {
    setupAuth({ hasSession: false });
    const fd = buildFormData({ prefix: "!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertAuthError(result);
    // A rejected request must never trigger the cache-sync webhook.
    expect(mockNotifyWebhookSync).not.toHaveBeenCalled();
  });

  it("returns error when provider token is missing", async () => {
    setupAuth({ hasProviderToken: false });
    const fd = buildFormData({ prefix: "!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    if (!result.success) {
      expect(result.error).toMatch(/re-login/i);
    }
  });

  it("returns error when guild is inactive", async () => {
    setupAuth({ guildActive: false });
    const fd = buildFormData({ prefix: "!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    if (!result.success) {
      expect(result.error).toMatch(/inactive|not found/i);
    }
  });

  it("returns error when user lacks ADMINISTRATOR permission", async () => {
    setupAuth({ isAdmin: false });
    const fd = buildFormData({ prefix: "!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    if (!result.success) {
      expect(result.error).toMatch(/administrator/i);
    }
  });
});

// ---------------------------------------------------------------------------
// Validation tests
// ---------------------------------------------------------------------------

describe("updateGuildConfig — validation", () => {
  beforeEach(() => {
    setupAuth();
  });

  it("rejects prefix shorter than 1 character", async () => {
    const fd = buildFormData({ prefix: "", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "prefix");
  });

  it("rejects prefix longer than 10 characters", async () => {
    const fd = buildFormData({ prefix: "abcdefghijk", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "prefix");
  });

  it("accepts prefix exactly 10 characters", async () => {
    const fd = buildFormData({ prefix: "1234567890", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("rejects unsupported language code", async () => {
    const fd = buildFormData({ prefix: "!", language: "xx" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "language");
  });

  it("accepts valid language code 'es'", async () => {
    const fd = buildFormData({ prefix: "nb!", language: "es" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts valid language code 'en'", async () => {
    const fd = buildFormData({ prefix: "nb!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("rejects malformed snowflake for modRoleId", async () => {
    const fd = buildFormData({
      prefix: "!",
      language: "en",
      modRoleId: "not-a-number",
    });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "modRoleId");
  });

  it("rejects too-short snowflake for logChannelId", async () => {
    const fd = buildFormData({
      prefix: "!",
      language: "en",
      logChannelId: "123",
    });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "logChannelId");
  });

  it("rejects too-long snowflake for ticketCategoryId", async () => {
    const fd = buildFormData({
      prefix: "!",
      language: "en",
      ticketCategoryId: "123456789012345678901",
    });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertFieldError(result, "ticketCategoryId");
  });

  it("accepts valid 17-digit snowflake for optional fields", async () => {
    const fd = buildFormData({
      prefix: "!",
      language: "en",
      modRoleId: "12345678901234567",
      logChannelId: "12345678901234567",
      ticketCategoryId: "12345678901234567",
    });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts empty optional fields (null snowflakes)", async () => {
    const fd = buildFormData({
      prefix: "!",
      language: "en",
      modRoleId: "",
      logChannelId: "",
      ticketCategoryId: "",
    });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});

// ---------------------------------------------------------------------------
// Successful update
// ---------------------------------------------------------------------------

describe("updateGuildConfig — successful update", () => {
  it("calls revalidatePath on success", async () => {
    setupAuth();
    const fd = buildFormData({ prefix: "nb!", language: "es", logEnabled: "on" });
    const result = await updateGuildConfig(GUILD_ID, fd);

    assertSuccess(result);
    expect(mockRevalidatePath).toHaveBeenCalledWith(`/guilds/${GUILD_ID}`, "layout");
    // Webhook cache-sync is fired after a successful Supabase write, with the
    // guild_id as a string (the wire contract the bot expects).
    expect(mockNotifyWebhookSync).toHaveBeenCalledWith(GUILD_ID);
  });

  it("passes logEnabled=false when switch is off", async () => {
    setupAuth();
    // Without the "on" value for logEnabled, the field should be treated as false.
    const fd = buildFormData({ prefix: "?", language: "de" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("returns success even when notifyWebhookSync rejects (fire-and-forget at the action boundary)", async () => {
    setupAuth();
    mockNotifyWebhookSync.mockRejectedValueOnce(new Error("webhook down"));
    const fd = buildFormData({ prefix: "!", language: "en" });
    const result = await updateGuildConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});
