import type { Ticket } from "@/lib/types";

/**
 * One node of the rendered ticket tree: a parent ticket and the child
 * tickets grouped under it.
 */
export interface TicketTreeNode {
  ticket: Ticket;
  children: Ticket[];
}

/**
 * Group a flat ticket list into a one-level parent→children tree.
 *
 * - Tickets with no `parentId` are top-level roots.
 * - Tickets whose `parentId` references a ticket present in the list become
 *   children of that parent.
 * - Tickets whose `parentId` references a ticket NOT in the list (parent was
 *   deleted, or the parent fell outside the 50-row cap) degrade to top-level
 *   roots instead of crashing or being dropped.
 *
 * Order is preserved from the input (newest-first from the action). A child
 * is attached to its parent even if it appears before the parent in the
 * input, so the rendered tree always nests children under their parent.
 *
 * Extracted as a pure function so the grouping logic is testable without
 * rendering the page (no React/Discord mocks required).
 */
export function buildTicketTree(tickets: Ticket[]): TicketTreeNode[] {
  const byId = new Map<string, Ticket>();
  for (const ticket of tickets) {
    byId.set(ticket.id, ticket);
  }

  const nodes = new Map<string, TicketTreeNode>();
  for (const ticket of tickets) {
    nodes.set(ticket.id, { ticket, children: [] });
  }

  const roots: TicketTreeNode[] = [];
  for (const ticket of tickets) {
    const node = nodes.get(ticket.id)!;
    const parentId = ticket.parentId;
    const parent = parentId ? byId.get(parentId) : undefined;
    if (parent && nodes.has(parent.id)) {
      nodes.get(parent.id)!.children.push(ticket);
    } else {
      roots.push(node);
    }
  }
  return roots;
}
