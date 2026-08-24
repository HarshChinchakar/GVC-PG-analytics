import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/** Clear the session cookie. The JWT is stateless, so dropping it is enough. */
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
