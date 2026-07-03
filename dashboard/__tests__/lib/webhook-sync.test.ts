import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createHmac } from "node:crypto";
import { notifyWebhookSync } from "@/lib/webhook-sync";

// ---------------------------------------------------------------------------
// Constants — the wire contract the bot (PR1) expects:
//   POST  ${WEBHOOK_URL}/webhook/sync
//   body  {"guild_id":"<str>"}            (guild_id is a STRING — DB TEXT)
//   header X-Webhook-Signature = HMAC-SHA256(rawBody, WEBHOOK_SECRET).hexdigest()
// ---------------------------------------------------------------------------

const GUILD_ID = "123456789012345678";
const WEBHOOK_URL = "https://bot-webhook.example.com";
const WEBHOOK_SECRET = "test-shared-secret-do-not-use-in-prod";

describe("notifyWebhookSync", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleDebugSpy: ReturnType<typeof vi.spyOn>;
  let originalUrl: string | undefined;
  let originalSecret: string | undefined;

  beforeEach(() => {
    originalUrl = process.env.WEBHOOK_URL;
    originalSecret = process.env.WEBHOOK_SECRET;
    process.env.WEBHOOK_URL = WEBHOOK_URL;
    process.env.WEBHOOK_SECRET = WEBHOOK_SECRET;

    fetchSpy = vi.fn().mockResolvedValue(new Response("ok", { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    consoleDebugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
  });

  afterEach(() => {
    if (originalUrl === undefined) delete process.env.WEBHOOK_URL;
    else process.env.WEBHOOK_URL = originalUrl;
    if (originalSecret === undefined) delete process.env.WEBHOOK_SECRET;
    else process.env.WEBHOOK_SECRET = originalSecret;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function expectedSignatureFor(body: string): string {
    return createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
  }

  // -------------------------------------------------------------------------
  // Happy path: sign + POST
  // -------------------------------------------------------------------------

  it("POSTs to ${WEBHOOK_URL}/webhook/sync with POST method, JSON content-type, signed body", async () => {
    const expectedBody = JSON.stringify({ guild_id: GUILD_ID });
    await notifyWebhookSync(GUILD_ID);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${WEBHOOK_URL}/webhook/sync`);
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["X-Webhook-Signature"]).toBe(expectedSignatureFor(expectedBody));
    expect(init.body).toBe(expectedBody);
  });

  it("sends guild_id as a STRING in the JSON body (DB TEXT convention)", async () => {
    await notifyWebhookSync(GUILD_ID);
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const parsed = JSON.parse(init.body as string) as { guild_id: unknown };
    expect(typeof parsed.guild_id).toBe("string");
    expect(parsed.guild_id).toBe(GUILD_ID);
  });

  it("computes X-Webhook-Signature as HMAC-SHA256 hexdigest of the exact raw body bytes", async () => {
    await notifyWebhookSync(GUILD_ID);
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = init.body as string;
    const expected = createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Webhook-Signature"]).toBe(expected);
  });

  it("strips a trailing slash from WEBHOOK_URL when building the endpoint", async () => {
    process.env.WEBHOOK_URL = `${WEBHOOK_URL}/`;
    await notifyWebhookSync(GUILD_ID);
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${WEBHOOK_URL}/webhook/sync`);
  });

  // -------------------------------------------------------------------------
  // Fire-and-forget: never surfaces failures to the caller
  // -------------------------------------------------------------------------

  it("is fire-and-forget: a fetch rejection does NOT throw (caller unaffected)", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("network down"));
    await expect(notifyWebhookSync(GUILD_ID)).resolves.toBeUndefined();
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it("is fire-and-forget: a non-ok HTTP response does NOT throw", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("bad sig", { status: 401 }));
    await expect(notifyWebhookSync(GUILD_ID)).resolves.toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // Graceful no-op when env is not configured (server-side only)
  // -------------------------------------------------------------------------

  it("is a no-op (no fetch, debug log) when WEBHOOK_URL is unset", async () => {
    delete process.env.WEBHOOK_URL;
    await notifyWebhookSync(GUILD_ID);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(consoleDebugSpy).toHaveBeenCalled();
  });

  it("is a no-op (no fetch) when WEBHOOK_SECRET is unset", async () => {
    delete process.env.WEBHOOK_SECRET;
    await notifyWebhookSync(GUILD_ID);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Cross-side Known-Answer Test (KAT)
  // -------------------------------------------------------------------------
  // The dashboard helper and the bot (bot/webhook/auth.py::compute_signature)
  // MUST produce the identical HMAC-SHA256 hexdigest for a canonical body +
  // secret. This is the single-source-of-truth fixture mirrored on the bot
  // side in tests/test_webhook_auth.py (TestCrossSideKat). If either side
  // changes its signing, BOTH tests fail.
  const KAT_BODY = '{"guild_id":"123456789"}';
  const KAT_SECRET = "nebulosabot-kat-secret";
  const KAT_EXPECTED_DIGEST =
    "37bf65a01696b7f45c61411ecf3c7d516cd1bfcc460505d36c2cde9859cddcc1";

  it("cross-side KAT: produces the canonical digest the bot also computes", async () => {
    // Override the shared secret to the canonical KAT secret.
    process.env.WEBHOOK_SECRET = KAT_SECRET;
    await notifyWebhookSync("123456789");

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    // The helper builds body = JSON.stringify({guild_id:"123456789"}) which is
    // byte-identical to KAT_BODY (JSON.stringify emits no whitespace).
    expect(init.body).toBe(KAT_BODY);
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Webhook-Signature"]).toBe(KAT_EXPECTED_DIGEST);
  });
});
