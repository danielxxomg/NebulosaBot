import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSingle = vi.fn();
const mockEq = vi.fn(() => ({ single: mockSingle }));
const mockSelect = vi.fn(() => ({ eq: mockEq }));
const mockFrom = vi.fn(() => ({ select: mockSelect }));

vi.mock("@/lib/supabase", () => ({
  createServiceClient: vi.fn(async () => ({
    from: mockFrom,
  })),
}));

vi.mock("@/lib/actions/guild-actions", () => ({
  updateGuildConfig: vi.fn(),
}));

import GuildConfigPage from "@/app/(authenticated)/guilds/[guildId]/config/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const GUILD_ID = "123456789012345678";

function buildGuildRow(overrides: Record<string, unknown> = {}) {
  return {
    id: GUILD_ID,
    prefix: "nb!",
    language: "es",
    modRoleId: null,
    logChannelId: null,
    ticketCategoryId: null,
    logEnabled: false,
    ...overrides,
  };
}

async function renderConfigPage() {
  const ui = await GuildConfigPage({
    params: Promise.resolve({ guildId: GUILD_ID }),
  });
  return render(ui);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GuildConfigPage — ticket category label", () => {
  it("renders the ticket category label matching spec exactly", async () => {
    mockSingle.mockResolvedValue({ data: buildGuildRow(), error: null });

    await renderConfigPage();

    // Spec scenario: "THEN the label reads 'Discord Category Channel ID
    // (right-click → Copy Channel ID)'". The <Label htmlFor="ticketCategoryId">
    // element MUST contain this text.  Current label is "Ticket Category ID"
    // which does NOT match the spec.
    const labelEl = document.querySelector('label[for="ticketCategoryId"]');
    expect(labelEl).not.toBeNull();
    expect(labelEl!.textContent).toContain("Discord Category Channel ID");
  });
});
