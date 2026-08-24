import { NextResponse } from "next/server";

/**
 * Reject cross-site state-changing requests.
 *
 * The session cookie is SameSite=Lax, which already stops it being attached to
 * a cross-site POST — so this is defence in depth rather than the only guard.
 * It is worth having because Lax is a browser behaviour we do not control: it
 * has exceptions, it varies by browser version, and a future change to
 * SameSite=None (for an embed, say) would silently remove the protection.
 * An explicit origin check keeps working regardless.
 */
export function assertSameOrigin(request: Request): NextResponse | null {
  const origin = request.headers.get("origin");

  // Same-origin fetch() from a browser always sends Origin on POST. A request
  // without one is not a browser form we should trust with a write.
  if (!origin) {
    return NextResponse.json(
      { detail: "Request rejected: missing origin" },
      { status: 403 },
    );
  }

  const target = new URL(request.url);
  let source: URL;
  try {
    source = new URL(origin);
  } catch {
    return NextResponse.json({ detail: "Request rejected" }, { status: 403 });
  }

  if (source.host !== target.host) {
    return NextResponse.json(
      { detail: "Request rejected: cross-site write" },
      { status: 403 },
    );
  }
  return null;
}
