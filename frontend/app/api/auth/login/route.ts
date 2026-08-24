import { NextResponse } from "next/server";
import { SESSION_COOKIE, cookieOptions } from "@/lib/session";
import { API_BASE } from "@/lib/api";

/**
 * Login proxy.
 *
 * The browser posts here, not to FastAPI. This handler forwards the
 * credentials, and on success stores the token in a first-party httpOnly
 * cookie -- so the token is never readable by client-side JavaScript and the
 * backend URL is never exposed.
 */
export async function POST(request: Request) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }

  const email = String(body.email ?? "").trim();
  const password = String(body.password ?? "");
  if (!email || !password) {
    return NextResponse.json(
      { detail: "Enter your email and password" },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Preserve the caller's address so the backend rate-limits the real
        // client rather than the Vercel edge node.
        "X-Forwarded-For":
          request.headers.get("x-forwarded-for") ??
          request.headers.get("x-real-ip") ??
          "",
      },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "Cannot reach the server. Please try again." },
      { status: 503 },
    );
  }

  const data = await upstream.json().catch(() => ({}));

  if (!upstream.ok) {
    // Pass the backend's message through unchanged -- it is deliberately
    // uninformative about which half of the credentials was wrong.
    return NextResponse.json(
      { detail: data?.detail ?? "Sign-in failed" },
      { status: upstream.status },
    );
  }

  const response = NextResponse.json({ user: data.user });
  response.cookies.set(SESSION_COOKIE, data.access_token, cookieOptions);
  return response;
}
