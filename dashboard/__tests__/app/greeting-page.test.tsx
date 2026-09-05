import GreetingConfigPage from "@/app/(authenticated)/guilds/[guildId]/greeting/page";
import { describe, expect, it, vi, beforeEach } from "vitest";

const { mockCreateServiceClient, mockConfigForm } = vi.hoisted(() => ({
  mockConfigForm: vi.fn(() => null),
  mockCreateServiceClient: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  createServiceClient: mockCreateServiceClient,
}));

vi.mock("@/components/config-form", () => ({
  ConfigForm: mockConfigForm,
}));

vi.mock("@/lib/actions/greeting-actions", () => ({
  updateGreetingConfig: vi.fn(),
}));

const setupGreeting = (data: Record<string, unknown> | null) => {
  const terminal = { maybeSingle: vi.fn().mockResolvedValue({ data, error: null }) };
  const query = {
    select: vi.fn().mockReturnValue({
      eq: vi.fn().mockReturnValue(terminal),
    }),
  };
  mockCreateServiceClient.mockResolvedValue({ from: vi.fn().mockReturnValue(query) });
};

const findConfigForm = (node: unknown): { props: { fields: unknown[] } } => {
  if (node && typeof node === "object") {
    const candidate = node as { type?: unknown; props?: { children?: unknown; fields?: unknown[] } };
    if (candidate.type === mockConfigForm && candidate.props?.fields) {
      return candidate as { props: { fields: unknown[] } };
    }
    const children = candidate.props?.children;
    if (Array.isArray(children)) {
      for (const child of children) {
        try {
          return findConfigForm(child);
        } catch {
          // Continue searching sibling React children.
        }
      }
    } else if (children) {
      return findConfigForm(children);
    }
  }
  throw new Error("ConfigForm element not found");
};

describe("GreetingConfigPage onboarding setup control", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a clear nullable onboarding channel field for a new config", async () => {
    setupGreeting(null);

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as {
      name: string;
      label: string;
      defaultValue: string;
    }[];
    const onboarding = fields.find((field) => field.name === "onboardingChannelId");
    expect(onboarding).toMatchObject({
      defaultValue: "",
      name: "onboardingChannelId",
    });
    expect(onboarding?.label.toLowerCase()).toContain("onboarding");
  });

  it("loads the configured onboarding channel into the setup control", async () => {
    setupGreeting({
      goodbyeCardEnabled: true,
      goodbyeChannelId: null,
      goodbyeEnabled: false,
      goodbyeMessage: null,
      onboardingChannelId: "123456789012345678",
      welcomeCardEnabled: true,
      welcomeChannelId: null,
      welcomeEnabled: false,
      welcomeMessage: null,
    });

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as {
      name: string;
      defaultValue: string;
    }[];
    expect(fields.find((field) => field.name === "onboardingChannelId")).toMatchObject({
      defaultValue: "123456789012345678",
    });
  });
});

describe("GreetingThemeSelector — themeId field (PR1 5.1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a themeId field defaulting to empty for a new config", async () => {
    setupGreeting(null);

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as {
      name: string;
      label: string;
      defaultValue: string;
    }[];
    const theme = fields.find((field) => field.name === "themeId");
    expect(theme).toBeDefined();
    expect(theme?.defaultValue).toBe("");
    expect(theme?.label.toLowerCase()).toContain("theme");
  });

  it("loads the configured gaming_neon themeId into the selector", async () => {
    setupGreeting({
      goodbyeCardEnabled: false,
      goodbyeChannelId: null,
      goodbyeEnabled: false,
      goodbyeMessage: null,
      themeId: "gaming_neon",
      welcomeCardEnabled: false,
      welcomeChannelId: null,
      welcomeEnabled: false,
      welcomeMessage: null,
    });

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as {
      name: string;
      defaultValue: string;
    }[];
    expect(fields.find((field) => field.name === "themeId")).toMatchObject({
      defaultValue: "gaming_neon",
    });
  });

  it("loads a null themeId as an empty string for the form", async () => {
    setupGreeting({
      goodbyeCardEnabled: false,
      goodbyeChannelId: null,
      goodbyeEnabled: false,
      goodbyeMessage: null,
      themeId: null,
      welcomeCardEnabled: false,
      welcomeChannelId: null,
      welcomeEnabled: false,
      welcomeMessage: null,
    });

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as {
      name: string;
      defaultValue: string;
    }[];
    expect(fields.find((field) => field.name === "themeId")).toMatchObject({
      defaultValue: "",
    });
  });
});
