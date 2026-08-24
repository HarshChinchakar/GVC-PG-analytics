"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(data?.detail ?? "Sign-in failed");
        setPassword("");
        setBusy(false);
        return;
      }
      // Full navigation so server components re-read the new cookie.
      router.replace("/sites");
      router.refresh();
    } catch {
      setError("Cannot reach the server. Check your connection.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <div className="mb-5">
        <label htmlFor="email" className="label mb-2 block">
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="field"
          placeholder="you@gvcexecutive.in"
          disabled={busy}
        />
      </div>

      <div className="mb-6">
        <label htmlFor="password" className="label mb-2 block">
          Password
        </label>
        <div className="relative">
          <input
            id="password"
            name="password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field pr-16"
            placeholder="••••••••"
            disabled={busy}
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold uppercase tracking-wider"
            style={{ color: "var(--ink-faint)" }}
            aria-label={show ? "Hide password" : "Show password"}
            tabIndex={-1}
          >
            {show ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-5 flex items-start gap-2.5 px-3.5 py-3 text-sm"
          style={{
            background: "var(--clay-wash)",
            border: "1px solid color-mix(in oklab, var(--clay) 30%, transparent)",
            borderRadius: "3px",
            color: "var(--clay)",
          }}
        >
          <span aria-hidden className="mt-px font-bold">!</span>
          <span>{error}</span>
        </div>
      )}

      <button type="submit" className="btn btn-primary w-full" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
