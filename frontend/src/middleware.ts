import { NextRequest, NextResponse } from "next/server";

// Presence-only check for fast redirects -- this cannot validate the session
// (that needs a DB round trip), so it's a UX optimization, not the security
// boundary. The authoritative check is a real GET /auth/me call made
// server-side in each protected layout/page; FastAPI is the source of truth
// regardless of what happens here.
const SESSION_COOKIE_NAME = "session_token";
const PROTECTED_PREFIXES = ["/dashboard", "/organizations"];
const AUTH_ONLY_PATHS = ["/login", "/signup"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSessionCookie = request.cookies.has(SESSION_COOKIE_NAME);

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  if (isProtected && !hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (AUTH_ONLY_PATHS.includes(pathname) && hasSessionCookie) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/organizations/:path*", "/login", "/signup"],
};
