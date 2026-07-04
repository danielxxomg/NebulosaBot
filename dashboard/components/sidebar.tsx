"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard,
  Settings,
  Coins,
  MessageSquareHeart,
  Ticket,
  Menu,
  X,
  LogOut,
} from "lucide-react";

interface SidebarProps {
  /** If provided, guild-scoped nav links are shown. */
  guildId?: string;
}

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

/**
 * Collapsible navigation sidebar.
 *
 * Shows guild-scoped links when `guildId` is provided; otherwise
 * shows only the guild selector ("Guilds") link.
 *
 * Mobile: hidden by default, toggled via hamburger button.
 * Desktop: always visible on the left edge.
 */
export function Sidebar({ guildId }: SidebarProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems: NavItem[] = guildId
    ? [
        { href: `/guilds/${guildId}`, label: "Overview", icon: LayoutDashboard },
        { href: `/guilds/${guildId}/config`, label: "Config", icon: Settings },
        { href: `/guilds/${guildId}/economy`, label: "Economy", icon: Coins },
        {
          href: `/guilds/${guildId}/greeting`,
          label: "Greeting",
          icon: MessageSquareHeart,
        },
        {
          href: `/guilds/${guildId}/tickets`,
          label: "Tickets",
          icon: Ticket,
        },
      ]
    : [{ href: "/", label: "Guilds", icon: LayoutDashboard }];

  return (
    <>
      {/* Mobile toggle button */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed top-4 left-4 z-50 md:hidden"
        onClick={() => setMobileOpen((prev) => !prev)}
        aria-label={mobileOpen ? "Close sidebar" : "Open sidebar"}
      >
        {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      {/* Sidebar panel */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-sidebar-border bg-sidebar",
          "transform transition-transform duration-200 ease-in-out",
          "md:relative md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
          <span className="text-lg font-semibold text-sidebar-primary-foreground">
            NebulosaBot
          </span>
        </div>

        {/* Navigation links */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                )}
                onClick={() => setMobileOpen(false)}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="border-t border-sidebar-border p-3">
          <form action="/api/auth/logout" method="POST">
            <Button
              variant="ghost"
              className="w-full justify-start gap-3 text-sidebar-foreground hover:text-sidebar-accent-foreground"
              type="submit"
            >
              <LogOut className="h-4 w-4 shrink-0" />
              Logout
            </Button>
          </form>
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  );
}
