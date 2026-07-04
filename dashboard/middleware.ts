import { updateSession } from "@/lib/supabase/middleware";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Auth guard middleware.
 *
 * Refreshes the Supabase session cookie on every request and redirects
 * unauthenticated users to /login. Exempts login, auth callback, static
 * assets, and Next.js internals from the guard.
 */
export async function middleware(request: NextRequest) {
  const { supabaseResponse, session } = await updateSession(request);

  const { pathname } = request.nextUrl;

  // Public routes — no auth required.
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico"
  ) {
    return supabaseResponse;
  }

  // Require authentication for everything else.
  if (!session) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return supabaseResponse;
}

/**
 * Match every route EXCEPT:
 *  - API routes (handled by route.ts files)
 *  - Next.js static files (_next/static, _next/image)
 *  - favicon.ico and favicon.png (served as static assets, never auth-guarded)
 *
 * `runtime: "nodejs"` runs the middleware on the Node.js runtime so that
 * @supabase/supabase-js (which references `process.version`) does not trigger
 * an Edge Runtime compatibility warning during `next build`.
 *
 * This ensures middleware runs for pages but not internal Next.js requests.
 */
export const config = {
  runtime: "nodejs",
  matcher: ["/((?!api|_next/static|_next/image|favicon\\.(?:ico|png)).*)"],
};
