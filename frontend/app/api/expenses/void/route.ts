import { NextResponse } from "next/server";
import { getToken } from "@/lib/session";
import { API_BASE } from "@/lib/api";
import { assertSameOrigin } from "@/lib/csrf";

/** Void an expense. Same proxy shape and same CSRF guard as recording one. */
export async function POST(request: Request) {
  const bad = assertSameOrigin(request);
  if (bad) return bad;

  const token = await getToken();
  if (!token) {
    return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
  }

  let body: { expense_id?: string; reason?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
  if (!body.expense_id) {
    return NextResponse.json({ detail: "Missing expense" }, { status: 400 });
  }

  const upstream = await fetch(
    `${API_BASE}/api/v1/expenses/${body.expense_id}/void`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason: body.reason ?? "" }),
      cache: "no-store",
    },
  ).catch(() => null);

  if (!upstream) {
    return NextResponse.json({ detail: "Cannot reach the server" }, { status: 503 });
  }
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(
    upstream.ok ? data : { detail: data?.detail ?? "Could not void that" },
    { status: upstream.status },
  );
}
