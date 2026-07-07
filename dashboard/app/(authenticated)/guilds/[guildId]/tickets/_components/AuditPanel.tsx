"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { getTicketAudit } from "@/lib/actions/ticket-actions";
import type { TicketAudit, AuditOutcome } from "@/lib/types";

/** Rows per page — matches AUDIT_PAGE_SIZE in the server action. */
const AUDIT_PAGE_SIZE = 20;

/**
 * Paginated, guild-scoped view of the `ticket_audit` trail (PR3 TI-038 /
 * TI-021 / TI-028).
 *
 * The dashboard audit view is admin-only — the page layout and the
 * `getTicketAudit` server action both enforce `verifyGuildAdmin`, so this
 * component never renders for a non-admin. Rows are newest-first and
 * paginated 20 per page; the outcome (success | denied | error) is shown as
 * a badge whose text label conveys the state, so the meaning is never carried
 * by color alone (a11y — impeccable).
 */

interface AuditPanelProps {
  /** Discord guild ID whose audit trail to read (guild-scoped: never leaks across guilds). */
  guildId: string;
  /** Optional ticket id — narrows the view to a single ticket's history. */
  ticketId?: string;
}

/** Badge styling per outcome. Color is decorative; the text label is the a11y signal. */
const OUTCOME_BADGE: Record<
  AuditOutcome,
  { label: string; className: string }
> = {
  success: {
    label: "Success",
    className: "bg-green-500/10 text-green-700 ring-green-500/30",
  },
  denied: {
    label: "Denied",
    className: "bg-amber-500/10 text-amber-700 ring-amber-500/30",
  },
  error: {
    label: "Error",
    className: "bg-red-500/10 text-red-700 ring-red-500/30",
  },
};

const OUTCOME_FALLBACK = {
  label: "Unknown",
  className: "bg-muted text-muted-foreground ring-border",
};

function OutcomeBadge({ outcome }: { outcome: AuditOutcome }) {
  const tone = OUTCOME_BADGE[outcome] ?? OUTCOME_FALLBACK;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone.className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {tone.label}
      <span className="sr-only">audit outcome</span>
    </span>
  );
}

export function AuditPanel({ guildId, ticketId }: AuditPanelProps) {
  const [rows, setRows] = useState<TicketAudit[] | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setLoadError(null);
      const result = await getTicketAudit(guildId, ticketId, page);
      if (cancelled) return;
      if (result.error) {
        setLoadError(result.error);
        setRows([]);
      } else {
        setRows(result.data);
      }
      setIsLoading(false);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [guildId, ticketId, page]);

  const hasNext = rows !== null && rows.length === AUDIT_PAGE_SIZE;
  const hasPrev = page > 1;
  const showEmpty = !isLoading && rows !== null && rows.length === 0;

  return (
    <section
      aria-label="Ticket audit trail"
      className="space-y-3 rounded-md p-3 ring-1 ring-border"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Audit trail</h3>
        <span className="text-xs text-muted-foreground">
          Newest first · {AUDIT_PAGE_SIZE} per page
        </span>
      </div>

      {isLoading && (
        <p className="text-xs text-muted-foreground">Loading audit…</p>
      )}
      {loadError && (
        <p className="text-xs text-destructive" role="alert">
          {loadError}
        </p>
      )}
      {showEmpty && !loadError && (
        <p className="text-xs text-muted-foreground">No audit events yet.</p>
      )}

      {rows !== null && rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={row.id}
              className="space-y-1 rounded-md bg-muted/40 p-2 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <code className="font-mono font-medium text-foreground">
                    {row.action}
                  </code>
                  <OutcomeBadge outcome={row.outcome} />
                </div>
                <time className="text-muted-foreground" dateTime={row.createdAt}>
                  {new Date(row.createdAt).toLocaleString()}
                </time>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-muted-foreground">
                <span>
                  Actor:{" "}
                  <span className="font-mono">
                    {row.actorId ?? "system"}
                  </span>
                </span>
                {row.reason && (
                  <span>
                    Reason: <span className="text-foreground">{row.reason}</span>
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Page {page}
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!hasPrev || isLoading}
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNext || isLoading}
          >
            Next
          </Button>
        </div>
      </div>
    </section>
  );
}