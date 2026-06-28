import { Sidebar } from "@/components/sidebar";
import { createServerSupabaseClient } from "@/lib/supabase";
import { redirect } from "next/navigation";

/**
 * Authenticated route group layout.
 *
 * Verifies a valid Supabase session exists before rendering.
 * Wraps all child pages with the navigation sidebar.
 *
 * Pages in this group are protected by both this layout AND the
 * middleware guard in `middleware.ts`.
 */
export default async function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createServerSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-6 md:p-8">{children}</main>
    </div>
  );
}
