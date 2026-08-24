import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import { TopBar } from "@/components/top-bar";
import { OccupancyBoard } from "@/components/occupancy-board";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ year?: string; month?: string }>;
};

/**
 * Occupancy board — what sits behind the occupancy card on the dashboard.
 *
 * Open to managers as well as the owner: knowing which bed is free and who
 * has not paid is the daily job, not privileged analysis.
 *
 * Deliberately does NOT repeat the dashboard's counts, occupancy percentage,
 * vacancy loss or move-out list. What it adds is spatial: which bed, next to
 * which, in which tier, free from when.
 */
export default async function OccupancyPage({ params, searchParams }: Props) {
  if (!(await getToken())) redirect("/login");

  const { id } = await params;
  const { year, month } = await searchParams;

  let user, board;
  try {
    [user, board] = await Promise.all([
      api.me(),
      api.occupancy(
        id,
        year ? Number(year) : undefined,
        month ? Number(month) : undefined,
      ),
    ]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/logout?expired=1");
      if (error.status === 404) notFound();
    }
    throw error;
  }

  const totalBeds = Object.values(board.seat_totals).reduce((a, b) => a + b, 0);

  return (
    <>
      <TopBar
        userName={user.full_name}
        role={user.role}
        locationName={board.location_name}
        locationCode={board.location_code}
      />

      <main className="mx-auto max-w-[92rem] px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6">
          <Link
            href={`/sites/${board.location_id}`}
            className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold"
            style={{ color: "var(--ink-faint)" }}
          >
            <span aria-hidden>&larr;</span> Back to dashboard
          </Link>

          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="label mb-1.5">Occupancy board</p>
              <h1
                className="text-3xl tracking-tight sm:text-[2.5rem] sm:leading-none"
                style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
              >
                {board.location_name}
              </h1>
              <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
                All {totalBeds} beds, laid out as they are in the building.
                Rent status shown for{" "}
                <strong style={{ color: "var(--ink)" }}>{board.period_label}</strong>.
              </p>
            </div>

            {/* Deliberately prominent: at the gate this is the most-used
                thing on the whole screen. */}
            <Link
              href={`/sites/${board.location_id}/vehicles`}
              className="btn btn-primary"
            >
              <span aria-hidden>⌕</span> Vehicle lookup
            </Link>
          </div>
        </div>

        {/* Tier and gender availability — the two things you are asked for on
            the phone ("any attached bed free? anything on the ladies' side?")
            and which appear nowhere else in the app. */}
        <div className="mb-5 grid gap-3 sm:grid-cols-2">
          <div className="sheet px-4 py-3">
            <p className="label mb-2">Free by tier</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5">
              {board.tiers.map((t) => (
                <span key={t.tier} className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="num font-semibold"
                    style={{ color: t.vacant > 0 ? "var(--clay)" : "var(--ink-faint)" }}
                  >
                    {t.vacant}
                  </span>
                  <span style={{ color: "var(--ink-soft)" }}>{t.label}</span>
                  <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
                    of {t.beds}
                  </span>
                </span>
              ))}
            </div>
          </div>

          <div className="sheet px-4 py-3">
            <p className="label mb-2">Free by side</p>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5">
              {board.gender.map((g) => (
                <span key={g.policy} className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="num font-semibold"
                    style={{ color: g.vacant > 0 ? "var(--clay)" : "var(--ink-faint)" }}
                  >
                    {g.vacant}
                  </span>
                  <span className="capitalize" style={{ color: "var(--ink-soft)" }}>
                    {g.policy}
                  </span>
                  <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
                    of {g.beds}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>

        <OccupancyBoard board={board} />
      </main>
    </>
  );
}
