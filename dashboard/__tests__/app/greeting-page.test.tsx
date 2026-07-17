import { describe, expect, it, vi, beforeEach } from "vitest";

const { mockCreateServiceClient, mockConfigForm } = vi.hoisted(() => ({
  mockCreateServiceClient: vi.fn(),
  mockConfigForm: vi.fn(() => null),
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

import GreetingConfigPage from "@/app/(authenticated)/guilds/[guildId]/greeting/page";

function setupGreeting(data: Record<string, unknown> | null) {
  const terminal = { maybeSingle: vi.fn().mockResolvedValue({ data, error: null }) };
  const query = {
    select: vi.fn().mockReturnValue({
      eq: vi.fn().mockReturnValue(terminal),
    }),
  };
  mockCreateServiceClient.mockResolvedValue({ from: vi.fn().mockReturnValue(query) });
}

function findConfigForm(node: unknown): { props: { fields: unknown[] } } {
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
}

describe("GreetingConfigPage onboarding setup control", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a clear nullable onboarding channel field for a new config", async () => {
    setupGreeting(null);

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as Array<{
      name: string;
      label: string;
      defaultValue: string;
    }>;
    const onboarding = fields.find((field) => field.name === "onboardingChannelId");
    expect(onboarding).toMatchObject({
      name: "onboardingChannelId",
      defaultValue: "",
    });
    expect(onboarding?.label.toLowerCase()).toContain("onboarding");
  });

  it("loads the configured onboarding channel into the setup control", async () => {
    setupGreeting({
      onboardingChannelId: "123456789012345678",
      welcomeEnabled: false,
      goodbyeEnabled: false,
      welcomeChannelId: null,
      goodbyeChannelId: null,
      welcomeMessage: null,
      goodbyeMessage: null,
      welcomeCardEnabled: true,
      goodbyeCardEnabled: true,
    });

    const page = await GreetingConfigPage({ params: Promise.resolve({ guildId: "guild-1" }) });

    const fields = findConfigForm(page).props.fields as Array<{
      name: string;
      defaultValue: string;
    }>;
    expect(fields.find((field) => field.name === "onboardingChannelId")).toMatchObject({
      defaultValue: "123456789012345678",
    });
  });
});
