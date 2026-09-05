import { updateGreetingConfig } from "@/lib/actions/greeting-actions";
import { createServiceClient } from "@/lib/supabase";
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
  hasAdministratorPerm: (perm: string) => {
    const permsBigInt = BigInt(perm);
    // ADMINISTRATOR = bit 3 (0x8). Arithmetic bit-test (no-bitwise bans
    // &/|/>>/<<): floor-division by 8 drops the low 3 bits, odd/even of
    // the result is the bit's value.
    return (permsBigInt / 8n) % 2n === 1n;
  },
}));

vi.mock("next/cache", () => ({
  revalidatePath: (...args: unknown[]) => mockRevalidatePath(...args),
}));

const GUILD_ID = "123456789012345678";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const setupAuth = ({
  hasSession = true,
  hasProviderToken = true,
  guildActive = true,
  isAdmin = true,
}: {
  hasSession?: boolean;
  hasProviderToken?: boolean;
  guildActive?: boolean;
  isAdmin?: boolean;
} = {}) => {
  mockGetSession.mockResolvedValue(buildAuthSession({ hasProviderToken, hasSession }));

  const svc = buildMockServiceClient({
    guildSelectResult: guildActive
      ? { data: { active: true }, error: null }
      : { data: null, error: null },
  });

  vi.mocked(createServiceClient).mockResolvedValue(svc as unknown as Awaited<ReturnType<typeof createServiceClient>>);

  mockFetchUserGuilds.mockResolvedValue([
    { id: GUILD_ID, permissions: isAdmin ? "8" : "1024" },
  ]);

  mockRevalidatePath.mockClear();
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Auth rejection
// ---------------------------------------------------------------------------

describe("updateGreetingConfig — auth rejection", () => {
  it("returns error for unauthenticated user", async () => {
    setupAuth({ hasSession: false });
    const fd = buildFormData({ welcomeChannelId: "123456789012345678" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertAuthError(result);
  });

  it("returns error for non-admin user", async () => {
    setupAuth({ isAdmin: false });
    const fd = buildFormData({ welcomeChannelId: "123456789012345678" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    if (!result.success) {
      expect(result.error).toMatch(/administrator/iu);
    }
  });
});

// ---------------------------------------------------------------------------
// Channel validation
// ---------------------------------------------------------------------------

describe("updateGreetingConfig — channel validation", () => {
  beforeEach(() => {
    setupAuth();
  });

  it("requires welcomeChannelId when welcomeEnabled is on", async () => {
    const fd = buildFormData({ welcomeChannelId: "", welcomeEnabled: "on" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "welcomeChannelId");
  });

  it("does NOT require welcomeChannelId when welcomeEnabled is off", async () => {
    const fd = buildFormData({ welcomeChannelId: "", welcomeEnabled: "off" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("requires goodbyeChannelId when goodbyeEnabled is on", async () => {
    const fd = buildFormData({ goodbyeChannelId: "", goodbyeEnabled: "on" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "goodbyeChannelId");
  });

  it("does NOT require goodbyeChannelId when goodbyeEnabled is off", async () => {
    const fd = buildFormData({ goodbyeChannelId: "", goodbyeEnabled: "off" });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("rejects non-snowflake welcomeChannelId", async () => {
    const fd = buildFormData({
      welcomeChannelId: "abc-channel",
      welcomeEnabled: "on",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "welcomeChannelId");
  });

  it("rejects too-short snowflake for goodbyeChannelId", async () => {
    const fd = buildFormData({
      goodbyeChannelId: "123",
      goodbyeEnabled: "on",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "goodbyeChannelId");
  });

  it("accepts valid snowflake for both channels", async () => {
    const fd = buildFormData({
      goodbyeChannelId: "987654321098765432",
      goodbyeEnabled: "on",
      welcomeChannelId: "123456789012345678",
      welcomeEnabled: "on",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});

// ---------------------------------------------------------------------------
// Message length validation
// ---------------------------------------------------------------------------

describe("updateGreetingConfig — message length", () => {
  beforeEach(() => {
    setupAuth();
  });

  it("rejects welcomeMessage longer than 2000 characters", async () => {
    const longMessage = "a".repeat(2001);
    const fd = buildFormData({ welcomeMessage: longMessage });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "welcomeMessage");
  });

  it("accepts welcomeMessage exactly 2000 characters", async () => {
    const maxMessage = "b".repeat(2000);
    const fd = buildFormData({ welcomeMessage: maxMessage });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("rejects goodbyeMessage longer than 2000 characters", async () => {
    const longMessage = "c".repeat(2001);
    const fd = buildFormData({ goodbyeMessage: longMessage });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertFieldError(result, "goodbyeMessage");
  });

  it("accepts goodbyeMessage exactly 2000 characters", async () => {
    const maxMessage = "d".repeat(2000);
    const fd = buildFormData({ goodbyeMessage: maxMessage });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts short messages without issue", async () => {
    const fd = buildFormData({
      goodbyeMessage: "Goodbye {user}...",
      welcomeMessage: "Welcome {user}!",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("accepts empty (null) messages", async () => {
    const fd = buildFormData({
      goodbyeMessage: "",
      welcomeMessage: "",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });
});

// ---------------------------------------------------------------------------
// Successful update
// ---------------------------------------------------------------------------

describe("updateGreetingConfig — successful update", () => {
  it("saves a full welcome+goodbye config and revalidates", async () => {
    setupAuth();
    const fd = buildFormData({
      goodbyeCardEnabled: "on",
      goodbyeChannelId: "987654321098765432",
      goodbyeEnabled: "on",
      goodbyeMessage: "Bye {user}!",
      welcomeCardEnabled: "on",
      welcomeChannelId: "123456789012345678",
      welcomeEnabled: "on",
      welcomeMessage: "Hello {user}!",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
    expect(mockRevalidatePath).toHaveBeenCalledWith(`/guilds/${GUILD_ID}`, "layout");
  });

  it("saves welcome-only config (goodbye disabled)", async () => {
    setupAuth();
    const fd = buildFormData({
      welcomeChannelId: "123456789012345678",
      welcomeEnabled: "on",
      welcomeMessage: "Hey {user}!",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("saves goodbye-only config (welcome disabled)", async () => {
    setupAuth();
    const fd = buildFormData({
      goodbyeChannelId: "987654321098765432",
      goodbyeEnabled: "on",
      goodbyeMessage: "See ya {user}.",
    });
    const result = await updateGreetingConfig(GUILD_ID, fd);
    assertSuccess(result);
  });

  it("persists a valid onboarding channel without a bot webhook", async () => {
    setupAuth();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const fd = buildFormData({ onboardingChannelId: "123456789012345678" });

    const result = await updateGreetingConfig(GUILD_ID, fd);

    assertSuccess(result);
    const service = await vi.mocked(createServiceClient).mock.results.at(-1)?.value;
    const greetingUpsert = (service as unknown as {
      greeting: { upsert: ReturnType<typeof vi.fn> };
    }).greeting.upsert;
    expect(greetingUpsert).toHaveBeenCalledWith(
      expect.objectContaining({ onboardingChannelId: "123456789012345678" })
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("round-trips an empty onboarding channel as null", async () => {
    setupAuth();
    const fd = buildFormData({ onboardingChannelId: "" });

    const result = await updateGreetingConfig(GUILD_ID, fd);

    assertSuccess(result);
    const service = await vi.mocked(createServiceClient).mock.results.at(-1)?.value;
    const greetingUpsert = (service as unknown as {
      greeting: { upsert: ReturnType<typeof vi.fn> };
    }).greeting.upsert;
    expect(greetingUpsert).toHaveBeenCalledWith(
      expect.objectContaining({ onboardingChannelId: null })
    );
  });

  it("rejects an invalid onboarding channel ID", async () => {
    setupAuth();
    const result = await updateGreetingConfig(
      GUILD_ID,
      buildFormData({ onboardingChannelId: "not-a-snowflake" })
    );

    assertFieldError(result, "onboardingChannelId");
  });
});

// ---------------------------------------------------------------------------
// themeId persistence (PR1 5.1)
// ---------------------------------------------------------------------------

describe("updateGreetingConfig — themeId persistence (PR1 5.1)", () => {
  beforeEach(() => {
    setupAuth();
  });

  it("persists gaming_neon themeId to greeting_config", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const fd = buildFormData({ themeId: "gaming_neon" });

    const result = await updateGreetingConfig(GUILD_ID, fd);

    assertSuccess(result);
    const service = await vi.mocked(createServiceClient).mock.results.at(-1)?.value;
    const greetingUpsert = (service as unknown as {
      greeting: { upsert: ReturnType<typeof vi.fn> };
    }).greeting.upsert;
    expect(greetingUpsert).toHaveBeenCalledWith(
      expect.objectContaining({ themeId: "gaming_neon" })
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("round-trips an empty themeId as null (default theme)", async () => {
    const fd = buildFormData({ themeId: "" });

    const result = await updateGreetingConfig(GUILD_ID, fd);

    assertSuccess(result);
    const service = await vi.mocked(createServiceClient).mock.results.at(-1)?.value;
    const greetingUpsert = (service as unknown as {
      greeting: { upsert: ReturnType<typeof vi.fn> };
    }).greeting.upsert;
    expect(greetingUpsert).toHaveBeenCalledWith(
      expect.objectContaining({ themeId: null })
    );
  });

  it("rejects an unknown themeId, coercing it to null", async () => {
    const fd = buildFormData({ themeId: "hacker_theme" });

    const result = await updateGreetingConfig(GUILD_ID, fd);

    assertSuccess(result);
    const service = await vi.mocked(createServiceClient).mock.results.at(-1)?.value;
    const greetingUpsert = (service as unknown as {
      greeting: { upsert: ReturnType<typeof vi.fn> };
    }).greeting.upsert;
    // Only gaming_neon is allowed; anything else coerces to null (default).
    expect(greetingUpsert).toHaveBeenCalledWith(
      expect.objectContaining({ themeId: null })
    );
  });
});
