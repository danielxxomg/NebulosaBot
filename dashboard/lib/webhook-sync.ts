import { createHmac } from "node:crypto";

/**
 * Webhook URL path the bot (PR1) serves for cache-sync invalidation.
 * Kept in sync with `bot/webhook/server.py::_WEBHOOK_PATH`.
 */
const WEBHOOK_PATH = "/webhook/sync";

/**
 * Notify the bot's cache-sync webhook that a guild's config changed.
 *
 * Builds the JSON body `{"guild_id":"<guildId>"}` (guild_id is a STRING to
 * match the bot's universal str guild_id convention — the DB schema stores
 * guild ids as TEXT and cache keys are `{guild_id}:{entity}`), signs it with
 * HMAC-SHA256 over the raw body bytes using the shared `WEBHOOK_SECRET`, and
 * POSTs it to `${WEBHOOK_URL}/webhook/sync` with the `X-Webhook-Signature`
 * hexdigest header.
 *
 * The call is fire-and-forget: any network error is logged and swallowed so
 * the calling Server Action's success path is never affected — a failed
 * invalidation just means the bot serves stale cache until its TTL expires.
 *
 * Server-side only: reads `process.env.WEBHOOK_URL` and
 * `process.env.WEBHOOK_SECRET` (NEVER `NEXT_PUBLIC_*` — the secret must not
 * reach the browser). When either is unset the helper is a graceful no-op
 * (debug log, no fetch, no throw), so the dashboard keeps working before the
 * webhook is wired up.
 *
 * @param guildId Discord guild id whose cached config was just written.
 */
export async function notifyWebhookSync(guildId: string): Promise<void> {
  const webhookUrl = process.env.WEBHOOK_URL;
  const webhookSecret = process.env.WEBHOOK_SECRET;

  if (!webhookUrl || !webhookSecret) {
    console.debug(
      "[webhook-sync] Skipped: WEBHOOK_URL or WEBHOOK_SECRET not set."
    );
    return;
  }

  // guild_id MUST be a string in the JSON payload (DB TEXT convention).
  const body = JSON.stringify({ guild_id: guildId });
  const signature = createHmac("sha256", webhookSecret)
    .update(body)
    .digest("hex");

  // WEBHOOK_URL is the base URL; strip any trailing slash before appending the
  // fixed endpoint path.
  const endpoint = `${webhookUrl.replace(/\/$/, "")}${WEBHOOK_PATH}`;

  try {
    await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
      },
      body,
    });
  } catch (error) {
    // Fire-and-forget: never surface webhook failures to the Server Action.
    console.error(
      "[webhook-sync] Failed to notify bot cache-sync webhook:",
      error
    );
  }
}
