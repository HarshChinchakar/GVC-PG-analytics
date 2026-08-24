import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Clear the session and return to sign-in.
 *
 * A GET route because server components cannot set cookies during render:
 * when a protected page finds its token rejected, redirecting here is the only
 * way to actually delete the bad cookie, rather than leaving it in place to be
 * retried -- and rejected -- on every subsequent request.
 */
export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const target = new URL("/login", request.url);
  if (incoming.searchParams.get("expired")) {
    target.searchParams.set("expired", "1");
  }
  const response = NextResponse.redirect(target);
  response.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
