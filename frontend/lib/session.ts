import { cookies } from "next/headers";

/**
 * Session handling.
 *
 * The access token never reaches client-side JavaScript. The browser talks
 * only to this Next.js origin; the token lives in a first-party httpOnly
 * cookie that only server components and route handlers can read, and they
 * forward it to FastAPI as a bearer header.
 *
 * This avoids third-party cookies entirely (Vercel and Render are different
 * origins, and Safari blocks cross-site cookies outright), and means an XSS
 * bug on the frontend cannot exfiltrate the token.
 */

export const SESSION_COOKIE = "pg_session";

export const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  // Matches the backend's 8-hour token lifetime, so the cookie cannot outlive
  // the credential it carries.
  maxAge: 60 * 60 * 8,
};

export async function getToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/**
 * Is the session actually usable?
 *
 * A cookie can be present and worthless -- the token may have expired, been
 * signed with a rotated secret, or reference a user that no longer exists.
 * Pages must never decide "logged in" from the cookie's mere presence: doing
 * so caused an infinite /sites -> /login -> /sites redirect loop, because the
 * protected page rejected the token while the login page saw a cookie and
 * bounced straight back.
 *
 * Returns false for any unusable session, so the only way past the login page
 * is a token the backend has actually accepted.
 */
export async function hasValidSession(): Promise<boolean> {
  if (!(await getToken())) return false;
  try {
    const { api } = await import("./api");
    await api.me();
    return true;
  } catch {
    return false;
  }
}
