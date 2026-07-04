import { Fragment } from "react";
import { Ticket as TicketIcon } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getTicketsForGuild } from "@/lib/actions/ticket-actions";
import type { Ticket, TicketStatus } from "@/lib/types";
import { buildTicketTree } from "./_lib/build-ticket-tree";
import { TicketRowActions } from "./_components/TicketRowActions";

export const metadata = {
  title: "Tickets — NebulosaBot Dashboard",
};

interface TicketsPageProps {
  params: Promise<{ guildId: string }>;
}

/**
 * Status → badge styling. Color carries the at-a-glance signal; the text
 * label (and a small dot) ensures the status is never conveyed by color
 * alone. Unknown runtime values fall back to a neutral pill (no crash).
 */
const STATUS_BADGE: Record<
  TicketStatus,
  { label: string; className: string }
> = {
  open: {
    label: "Open",
    className: "bg-green-500/10 text-green-600 ring-green-500/20",
  },
  claimed: {
    label: "Claimed",
    className: "bg-yellow-500/10 text-yellow-600 ring-yellow-500/20",
  },
  closed: {
    label: "Closed",
    className: "bg-muted text-muted-foreground ring-border",
  },
};

const NEUTRAL_BADGE = {
  label: "Unknown",
  className: "bg-muted text-muted-foreground ring-border",
};

function StatusBadge({ status }: { status: TicketStatus }) {
  const tone = STATUS_BADGE[status] ?? NEUTRAL_BADGE;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone.className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {tone.label}
    </span>
  );
}

interface StatCardProps {
  label: string;
  count: number;
  dotClassName: string;
}

function StatCard({ label, count, dotClassName }: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">
            {count}
          </p>
        </div>
        <span
          className={`h-2.5 w-2.5 rounded-full ${dotClassName}`}
          aria-hidden="true"
        />
      </CardContent>
    </Card>
  );
}

function PageHeader() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Tickets</h1>
      <p className="mt-1 text-muted-foreground">
        Monitor support tickets for this guild.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-ticket tree
// ---------------------------------------------------------------------------

/**
 * One table row for a ticket. Children render with a leading connector glyph
 * and an accessible "Sub-ticket of #N" label (visually hidden) so the
 * hierarchy is conveyed by text, not by indentation alone. The Actions cell
 * holds the client {@link TicketRowActions} leaf.
 */
function TicketRow({
  ticket,
  isChild,
  parentNumber,
}: {
  ticket: Ticket;
  isChild: boolean;
  parentNumber?: number;
}) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-3 py-2 font-medium text-foreground">
        <div
          className={
            isChild
              ? "flex items-center gap-1.5 pl-6"
              : "flex items-center gap-1.5"
          }
        >
          {isChild && (
            <span aria-hidden="true" className="text-muted-foreground">
              ↳
            </span>
          )}
          <span>#{ticket.ticketNumber}</span>
          {isChild && parentNumber != null && (
            <span className="sr-only">Sub-ticket of #{parentNumber}</span>
          )}
        </div>
      </td>
      <td className="px-3 py-2">
        <StatusBadge status={ticket.status} />
      </td>
      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
        {ticket.authorId}
      </td>
      <td className="px-3 py-2 text-muted-foreground">
        {new Date(ticket.createdAt).toLocaleString()}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
        {ticket.claimedBy ?? "—"}
      </td>
      <td className="px-3 py-2 align-top">
        <TicketRowActions ticket={ticket} />
      </td>
    </tr>
  );
}

/**
 * Read-only ticket overview for a guild.
 *
 * Shows open / claimed / closed counts plus a capped (50) ticket list,
 * newest first. Auth and guild isolation are enforced by
 * `getTicketsForGuild`; this component only renders what the action returns.
 */
export default async function TicketsPage({ params }: TicketsPageProps) {
  const { guildId } = await params;
  const result = await getTicketsForGuild(guildId);

  // Auth or database failure: surface the action error without redirecting.
  if (result.error !== null) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">
              Couldn&apos;t load tickets
            </CardTitle>
            <CardDescription>{result.error}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const tickets = result.data;

  return (
    <div className="space-y-6">
      <PageHeader />

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="Open"
          count={tickets.filter((t) => t.status === "open").length}
          dotClassName="bg-green-500"
        />
        <StatCard
          label="Claimed"
          count={tickets.filter((t) => t.status === "claimed").length}
          dotClassName="bg-yellow-500"
        />
        <StatCard
          label="Closed"
          count={tickets.filter((t) => t.status === "closed").length}
          dotClassName="bg-muted-foreground"
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Recent tickets</CardTitle>
          <CardDescription>
            Showing the {tickets.length} most recent{" "}
            {tickets.length === 1 ? "ticket" : "tickets"}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tickets.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <TicketIcon className="h-6 w-6 text-muted-foreground" />
              </div>
              <div className="space-y-1">
                <p className="font-medium text-foreground">No tickets yet</p>
                <p className="text-sm text-muted-foreground">
                  Tickets created from the bot&apos;s panel will appear here.
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th scope="col" className="px-3 py-2 font-medium">
                      Number
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Status
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Author
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Created
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Claimed By
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {buildTicketTree(tickets).map((node) => (
                    <Fragment key={node.ticket.id}>
                      <TicketRow ticket={node.ticket} isChild={false} />
                      {node.children.map((child) => (
                        <TicketRow
                          key={child.id}
                          ticket={child}
                          isChild
                          parentNumber={node.ticket.ticketNumber}
                        />
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
