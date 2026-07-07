import { describe, it, expect, vi } from "vitest";
import { pathToRegexp } from "next/dist/compiled/path-to-regexp";
import type { SupabaseClient } from "@supabase/supabase-js";

import { config, middleware } from "@/middleware";
import { updateSession } from "@/lib/supabase/middleware";
import { NextRequest, NextResponse } from "next/server";

// Replace the Supabase session helper so the auth-redirect path can be
// exercised without network/env access. Only `updateSession` is used by
// middleware.ts; the rest of the module is irrelevant here.
vi.mock("@/lib/supabase/middleware", () => ({
  updateSession: vi.fn(),
}));

/**
 * Compiles a Next.js middleware `matcher` entry into a RegExp that mirrors
 * how Next applies it at runtime.
 *
 * Next anchors the compiled matcher (`^...$`) and consumes the pathname's
 * leading "/" via an explicit `\/` that sits *before* the negative-lookahead
 * group — so the lookahead is evaluated against the path with its leading
 * slash removed. This was verified against the production
 * `middleware-manifest.json` `regexp` field, which compiles
 * `/((?!api|_next/static|_next/image|favicon.ico).*)` into
 * `^(?:\\/(_next\\/data\\/[^/]+))?(?:\\/((?!api|_next\\/static|_next\\/image|favicon.ico).*))...$`.
 *
 * For the favicon / protected-route / api / _next paths under test, the
 * optional `_next/data` prefix and `.json`/`.rsc` suffix never apply, so the
 * compiled matcher reduces to `^/<body>$` where `<body>` is the config entry
 * with its leading "/" dropped.
 */
function compileMatcher(entry: string): RegExp {
  // Drop only the leading "/" (the entry is a path-style source; it contains
  // additional "/" inside `_next/static` and `_next/image`, so delimiter
  // slicing via lastIndexOf would be incorrect).
  const body = entry.slice(1);
  return new RegExp(`^/${body}$`);
}

describe("middleware config", () => {
  it("runs on the Node.js runtime to avoid the Edge process.version warning", () => {
    expect(config.runtime).toBe("nodejs");
  });

  it("uses a matcher that Next.js can compile at build time", () => {
    // Next validates the matcher via path-to-regexp during `next build`;
    // capturing groups (e.g. `(ico|png)`) are rejected and break the build.
    // Guard the config against that class of error with Next's own validator.
    expect(() => pathToRegexp(config.matcher[0])).not.toThrow();
  });

  it("excludes favicon.ico and favicon.png from auth redirects", () => {
    const matcher = compileMatcher(config.matcher[0]);

    // Static favicon assets must be served (200), never 307-redirected.
    expect(matcher.test("/favicon.ico")).toBe(false);
    expect(matcher.test("/favicon.png")).toBe(false);
  });

  it("still matches protected routes and the login page", () => {
    const matcher = compileMatcher(config.matcher[0]);

    expect(matcher.test("/")).toBe(true);
    expect(matcher.test("/guilds/123")).toBe(true);
    expect(matcher.test("/guilds/123/config")).toBe(true);
    expect(matcher.test("/login")).toBe(true);
  });

  it("excludes api and Next.js internal paths", () => {
    const matcher = compileMatcher(config.matcher[0]);

    expect(matcher.test("/api/auth/callback")).toBe(false);
    expect(matcher.test("/_next/static/chunk.js")).toBe(false);
  });
});

describe("middleware auth guard", () => {
  it("redirects unauthenticated requests to /login with the original path", async () => {
    // No session -> middleware must redirect (307) to /login carrying the
    // original pathname so login can return the user to where they were.
    vi.mocked(updateSession).mockResolvedValue({
      supabaseResponse: NextResponse.next(),
      supabase: {} as SupabaseClient,
      session: null,
    });

    const request = new NextRequest("http://localhost/guilds/123");
    const response = await middleware(request);

    expect(response.status).toBe(307);

    const location = response.headers.get("location") ?? "";
    expect(location).toContain("/login?redirect=");
    // The redirect param is URL-encoded (%2F...), so decode before asserting
    // the original pathname round-trips through the login redirect.
    expect(decodeURIComponent(location)).toContain("redirect=/guilds/123");
  });

  it("lets authenticated requests through without redirect", async () => {
    // Valid session -> middleware must NOT redirect; it returns the
    // supabaseResponse (NextResponse.next) unchanged. Guards the Edge->Node
    // runtime switch happy path: auth pass-through still works.
    const next = NextResponse.next();
    vi.mocked(updateSession).mockResolvedValue({
      supabaseResponse: next,
      supabase: {} as SupabaseClient,
      session: { user: { id: "u1" } } as never,
    });

    const request = new NextRequest("http://localhost/guilds/123");
    const response = await middleware(request);

    expect(response.status).not.toBe(307);
    expect(response.headers.get("location")).toBeNull();
    expect(response).toBe(next);
  });
});
