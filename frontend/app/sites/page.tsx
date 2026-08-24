import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import { percent, rupees } from "@/lib/format";
import { TopBar } from "@/components/top-bar";
import { Meter } from "@/components/ui";

export const metadata = { title: "Choose a site — GVC Executive PG Tally" };
export const dynamic = "force-dynamic";

/**
 * Site picker.
 *
 * The owner runs several buildings, so the first decision after signing in is
 * which one. Each card carries enough live data — occupancy and money still
 * outstanding — to make that choice without opening it first.
 *
 * A manager with exactly one building is sent straight through; making them
 * pick from a list of one would be pure ceremony.
 */
export default async function SitesPage() {
  if (!(await getToken())) redirect("/login");

  let user, sites;
  try {
    [user, sites] = await Promise.all([api.me(), api.locations()]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401)
      redirect("/logout?expired=1");
    throw error;
  }

  if (user.role !== "super_admin" && sites.length === 1) {
    redirect(`/sites/${sites[0].id}`);
  }

  const totals = sites.reduce(
    (acc, s) => ({
      beds: acc.beds + s.total_beds,
      occupied: acc.occupied + s.occupied,
      available: acc.available + s.available,
      pending: acc.pending + s.pending_rent,
      pendingCount: acc.pendingCount + s.pending_count,
    }),
    { beds: 0, occupied: 0, available: 0, pending: 0, pendingCount: 0 },
  );

  return (
    <>
      <TopBar userName={user.full_name} role={user.role} />

      <main className="mx-auto max-w-[84rem] px-4 py-8 sm:px-6 sm:py-12">
        <div className="mb-8 sm:mb-10">
          <p className="label mb-2">
            {user.role === "super_admin" ? "All locations" : "Your locations"}
          </p>
          <h1
            className="text-3xl tracking-tight sm:text-4xl"
            style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
          >
            Good to see you, {user.full_name.split(" ")[0]}.
          </h1>
          <p className="mt-2 max-w-xl text-sm" style={{ color: "var(--ink-soft)" }}>
            Choose a site to open its dashboard.
          </p>
        </div>

        {/* Portfolio strip — owner only, and only when there is more than one
            building to aggregate. */}
        {user.role === "super_admin" && sites.length > 1 && (
          <div
            className="sheet-raised mb-8 grid grid-cols-2 gap-px overflow-hidden sm:grid-cols-4"
            style={{ background: "var(--rule)" }}
          >
            {[
              ["Beds across all sites", String(totals.beds)],
              ["Occupied", String(totals.occupied)],
              ["Vacant", String(totals.available)],
              ["Rent outstanding", rupees(totals.pending)],
            ].map(([label, value], i) => (
              <div
                key={label}
                className="px-4 py-4"
                style={{ background: "var(--paper-raised)" }}
              >
                <p className="label">{label}</p>
                <p
                  className="num mt-1.5 text-xl font-semibold sm:text-2xl"
                  style={{ color: i === 3 && totals.pending > 0 ? "var(--clay)" : "var(--ink)" }}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>
        )}

        {sites.length === 0 ? (
          <div className="sheet px-6 py-16 text-center">
            <p className="text-sm" style={{ color: "var(--ink-soft)" }}>
              No sites have been assigned to your account yet. Ask the owner to
              grant you access.
            </p>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {sites.map((site) => (
              <li key={site.id}>
                <Link
                  href={`/sites/${site.id}`}
                  className="sheet sheet-interactive block h-full"
                  style={{ textDecoration: "none" }}
                >
                  <div className="rule-b flex items-start justify-between gap-3 px-5 py-4">
                    <div className="min-w-0">
                      <h2 className="truncate text-lg font-semibold tracking-tight">
                        {site.name}
                      </h2>
                      {site.city && (
                        <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                          {site.city}
                        </p>
                      )}
                    </div>
                    <span
                      className="num shrink-0 px-2 py-1 text-[0.6875rem] font-semibold"
                      style={{
                        background: "var(--paper-sunk)",
                        color: "var(--ink-soft)",
                        borderRadius: "2px",
                      }}
                    >
                      {site.code}
                    </span>
                  </div>

                  <div className="px-5 py-4">
                    <div className="mb-1.5 flex items-baseline justify-between">
                      <span className="label">Occupancy</span>
                      <span className="num text-sm font-semibold">
                        {percent(site.occupancy_rate)}
                      </span>
                    </div>
                    <Meter value={site.occupancy_rate} />
                    <p className="num mt-2 text-xs" style={{ color: "var(--ink-faint)" }}>
                      {site.occupied} of {site.total_beds} beds · {site.available} vacant
                    </p>
                  </div>

                  <div
                    className="rule-t flex items-center justify-between px-5 py-3"
                    style={{ background: "var(--paper-sunk)" }}
                  >
                    {site.pending_count > 0 ? (
                      <>
                        <span className="text-xs font-medium" style={{ color: "var(--clay)" }}>
                          {site.pending_count} unpaid this month
                        </span>
                        <span
                          className="num text-sm font-semibold"
                          style={{ color: "var(--clay)" }}
                        >
                          {rupees(site.pending_rent)}
                        </span>
                      </>
                    ) : (
                      <span className="text-xs font-medium" style={{ color: "var(--moss)" }}>
                        All rent collected this month
                      </span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
