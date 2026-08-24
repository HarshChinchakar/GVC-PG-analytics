import { NextResponse } from "next/server";
import { getToken } from "@/lib/session";
import { API_BASE } from "@/lib/api";
import { assertSameOrigin } from "@/lib/csrf";

/**
 * Expense write proxy.
 *
 * The browser posts here rather than to FastAPI, so the session cookie stays
 * first-party and the backend's address stays off the client. This handler
 * reads a cookie, which makes it the one place in the app where CSRF is
 * possible — see assertSameOrigin.
 */
export async function POST(request: Request) {
  const bad = assertSameOrigin(request);
  if (bad) return bad;

  const token = await getToken();
  if (!token) {
    return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
  }

  let body: { location_id?: string; [k: string]: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }

  const { location_id: locationId, ...payload } = body;
  if (!locationId) {
    return NextResponse.json({ detail: "Choose a site" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/api/v1/locations/${locationId}/expenses`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "Cannot reach the server. Your entry was not saved." },
      { status: 503 },
    );
  }

  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(
      { detail: data?.detail ?? "Could not save that" },
      { status: upstream.status },
    );
  }
  return NextResponse.json(data, { status: upstream.status });
}
