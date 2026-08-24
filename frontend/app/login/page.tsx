import { redirect } from "next/navigation";
import { hasValidSession } from "@/lib/session";
import { LoginForm } from "./login-form";

export const metadata = { title: "Sign in — GVC Executive PG Tally" };

/**
 * Sign-in.
 *
 * Two panels on desktop: an identity panel carrying the business's name and
 * what the tool is for, and the form itself. On phones the identity panel
 * collapses to a compact header so the keyboard does not push the form
 * off-screen.
 *
 * There is no "create account" link by design — accounts are issued by the
 * owner from inside the application.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ expired?: string }>;
}) {
  const expired = (await searchParams).expired === "1";
  // Verified, not merely present -- see hasValidSession().
  if (await hasValidSession()) redirect("/sites");

  return (
    <main className="min-h-dvh lg:grid lg:grid-cols-[1.05fr_1fr]">
      {/* Identity panel */}
      <section
        className="grid-ground relative flex flex-col justify-between px-6 py-10 sm:px-10 lg:px-14 lg:py-12"
        style={{
          // backgroundColor, not the `background` shorthand: the shorthand
          // would reset the grid texture's background-image.
          backgroundColor: "var(--paper-sunk)",
          borderRight: "1px solid var(--rule-strong)",
        }}
      >
        <div className="flex items-baseline gap-3">
          <span
            className="num flex h-9 w-9 items-center justify-center text-sm font-semibold"
            style={{
              background: "var(--ink)",
              color: "var(--paper-raised)",
              borderRadius: "3px",
            }}
            aria-hidden
          >
            GV
          </span>
          <span
            className="text-sm font-semibold tracking-tight"
            style={{ color: "var(--ink-soft)" }}
          >
            GVC Executive
          </span>
        </div>

        <div className="hidden max-w-lg lg:block">
          <h1
            className="text-5xl leading-[1.05] tracking-tight xl:text-6xl"
            style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
          >
            The whole PG,
            <br />
            <span style={{ color: "var(--clay)" }}>on one page.</span>
          </h1>
          <dl className="mt-12 grid grid-cols-3 gap-px" style={{ background: "var(--rule)" }}>
            {[
              ["Occupancy", "Live"],
              ["Rent tally", "Monthly"],
              ["Spreadsheets", "None"],
            ].map(([label, value]) => (
              <div key={label} className="px-4 py-4" style={{ backgroundColor: "var(--paper-sunk)" }}>
                <dt className="label">{label}</dt>
                <dd className="mt-1.5 text-xl font-semibold tracking-tight">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="hidden text-xs lg:block" style={{ color: "var(--ink-faint)" }}>
          Internal tool · Authorised staff only
        </p>
      </section>

      {/* Form panel */}
      <section className="flex items-center justify-center px-6 py-12 sm:px-10 lg:py-14">
        <div className="w-full max-w-[24rem]">
          <div className="mb-8">
            <p className="label mb-2">Rent &amp; occupancy tally</p>
            <h2
              className="text-3xl tracking-tight"
              style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
            >
              Sign in
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              {expired
                ? "Your session has ended. Please sign in again."
                : "Use the account issued to you by the owner."}
            </p>
          </div>

          <LoginForm />

          <div className="rule-t mt-8 pt-5">
            <p className="text-xs leading-relaxed" style={{ color: "var(--ink-faint)" }}>
              Accounts are created by the owner. If you cannot sign in, ask for
              your password to be reset — repeated failed attempts will lock the
              account for 15&nbsp;minutes.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
