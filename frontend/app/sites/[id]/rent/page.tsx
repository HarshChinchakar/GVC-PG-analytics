import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import { percent, rupees, rupeesShort } from "@/lib/format";
import { TopBar } from "@/components/top-bar";
import { MonthPicker } from "@/components/month-picker";
import {
  DimensionTable,
  Extremes,
  FactorBreakdown,
  Waterfall,
} from "@/components/analysis";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ year?: string; month?: string }>;
};

/**
 * Revenue drill-down — what sits behind the rent card on the dashboard.
 *
 * Reads top to bottom as an argument, not a pile of charts:
 *   1. what the building earned, and what it could have earned
 *   2. why the gap exists (three factors that multiply to yield)
 *   3. where the money went (waterfall)
 *   4. which parts of the building are strong and weak (six dimensions)
 *   5. how promptly residents actually pay
 *   6. how all of this is moving month to month
 */
export default async function RentAnalysisPage({ params, searchParams }: Props) {
  if (!(await getToken())) redirect("/login");

  const { id } = await params;
  const { year, month } = await searchParams;

  let user, a, dash;
  try {
    [user, a, dash] = await Promise.all([
      api.me(),
      api.analysis(id, year ? Number(year) : undefined, month ? Number(month) : undefined),
      api.dashboard(id, year ? Number(year) : undefined, month ? Number(month) : undefined),
    ]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/logout?expired=1");
      // Managers get 404 here: this is owner-only analysis.
      if (error.status === 404) notFound();
    }
    throw error;
  }

  const { waterfall: w, factors: f, totals: t, payment_behaviour: pb } = a;
  const currentPeriod = `${a.period_year}-${String(a.period_month).padStart(2, "0")}`;
  const paidOnTimePct =
    pb.payments_counted > 0
      ? (pb.on_or_before_due / pb.payments_counted) * 100
      : 0;

  return (
    <>
      <TopBar
        userName={user.full_name}
        role={user.role}
        locationName={a.location_name}
        locationCode={a.location_code}
      />

      <main className="mx-auto max-w-[84rem] px-4 py-6 sm:px-6 sm:py-8">
        {/* --- head ------------------------------------------------------ */}
        <div className="mb-6">
          <Link
            href={`/sites/${a.location_id}?year=${a.period_year}&month=${a.period_month}`}
            className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold"
            style={{ color: "var(--ink-faint)" }}
          >
            <span aria-hidden>&larr;</span> Back to dashboard
          </Link>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="label mb-1.5">Revenue analysis</p>
              <h1
                className="text-3xl tracking-tight sm:text-[2.5rem] sm:leading-none"
                style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
              >
                {a.location_name}
              </h1>
              <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
                Every rupee for{" "}
                <strong style={{ color: "var(--ink)" }}>{a.period_label}</strong>,
                traced to the beds that produced it.
              </p>
            </div>
            <MonthPicker
              periods={dash.available_periods.length ? dash.available_periods : [currentPeriod]}
              current={currentPeriod}
              locationId={a.location_id}
              basePath={`/sites/${a.location_id}/rent`}
            />
          </div>
        </div>

        {/* --- headline figures ------------------------------------------ */}
        <section
          className="sheet-raised mb-4 grid grid-cols-2 gap-px overflow-hidden lg:grid-cols-4"
          style={{ background: "var(--rule)" }}
        >
          {[
            {
              label: "Collected",
              value: rupees(w.collected),
              note: `${t.paid_count} residents paid`,
              tone: "var(--moss)",
            },
            {
              label: "Full potential",
              value: rupees(w.potential),
              note: `all ${t.rentable} rentable beds at list rent`,
              tone: "var(--ink)",
            },
            {
              label: "Yield",
              value: percent(f.yield_rate),
              note: "collected ÷ potential",
              tone: f.yield_rate >= 70 ? "var(--moss)" : "var(--clay)",
            },
            {
              label: "Revenue per bed",
              value: rupees(t.revpab),
              note: `${rupees(t.arpo)} per occupied bed`,
              tone: "var(--ink)",
            },
          ].map((m) => (
            <div key={m.label} className="px-4 py-4 sm:px-5 sm:py-5" style={{ background: "var(--paper-raised)" }}>
              <p className="label">{m.label}</p>
              <p
                className="num mt-2 text-[1.75rem] leading-none font-semibold tracking-tight sm:text-[2rem]"
                style={{ color: m.tone }}
              >
                {m.value}
              </p>
              <p className="mt-2 text-xs leading-snug" style={{ color: "var(--ink-faint)" }}>
                {m.note}
              </p>
            </div>
          ))}
        </section>

        {/* --- why, and where it went ------------------------------------ */}
        <section className="mb-4 grid items-start gap-4 lg:grid-cols-2">
          <FactorBreakdown
            occupancy={f.value_occupancy_rate}
            rate={f.rate_realisation}
            collection={f.collection_rate}
            total={f.yield_rate}
          />
          <Waterfall
            potential={w.potential}
            vacancyLoss={w.vacancy_loss}
            rateLeakage={w.rate_leakage}
            pending={w.pending}
            collected={w.collected}
          />
        </section>

        {/* --- callouts --------------------------------------------------- */}
        {a.callouts.length > 0 && (
          <section className="sheet mb-8 overflow-hidden">
            <div className="rule-b px-4 py-3 sm:px-5">
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">
                What stands out
              </h2>
            </div>
            <ul>
              {a.callouts.map((c, i) => (
                <li key={i} className="rule-b flex gap-3 px-4 py-3 last:border-0 sm:px-5">
                  <span
                    aria-hidden
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: "var(--clay)" }}
                  />
                  <div>
                    <p className="text-sm font-medium">{c.headline}</p>
                    <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                      {c.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* --- dimensions -------------------------------------------------- */}
        <div className="mb-4">
          <h2
            className="text-xl tracking-tight"
            style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
          >
            Where the revenue comes from
          </h2>
          <p className="mt-1 text-sm" style={{ color: "var(--ink-soft)" }}>
            Every cut below covers the same {t.beds} beds, so the totals always
            agree.
          </p>
        </div>

        <div className="grid items-start gap-4 xl:grid-cols-2">
          {a.dimensions.map((dimension) => (
            <div key={dimension.name} className="grid gap-0">
              <DimensionTable dimension={dimension} />
              {dimension.segments.length > 2 && (
                <div className="sheet mt-px overflow-hidden">
                  <Extremes dimension={dimension} />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* --- payment behaviour + trend ------------------------------------ */}
        <div className="mt-4 grid items-start gap-4 lg:grid-cols-2">
          <section className="sheet overflow-hidden">
            <div className="rule-b px-4 py-3 sm:px-5">
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">
                How promptly people pay
              </h2>
              <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                Measured from each resident&rsquo;s own due date, not the 1st.
              </p>
            </div>
            <div className="px-4 py-4 sm:px-5">
              <div className="mb-4 flex items-end gap-4">
                <p className="num text-[2rem] leading-none font-semibold">
                  {percent(paidOnTimePct)}
                </p>
                <p className="pb-1 text-xs" style={{ color: "var(--ink-soft)" }}>
                  paid on or before the due date
                  <br />
                  <span className="num">
                    {pb.average_days_late < 0
                      ? `${Math.abs(pb.average_days_late)} days early on average`
                      : `${pb.average_days_late} days late on average`}
                  </span>
                </p>
              </div>
              <ul className="space-y-2">
                {[
                  ["On or before due date", pb.on_or_before_due, "var(--moss)"],
                  ["Within a week", pb.within_a_week, "var(--ink)"],
                  ["Within a fortnight", pb.within_a_fortnight, "var(--amber)"],
                  ["More than a fortnight", pb.over_a_fortnight, "var(--clay)"],
                ].map(([label, count, tone]) => (
                  <li key={label as string}>
                    <div className="mb-1 flex items-baseline justify-between text-xs">
                      <span>{label as string}</span>
                      <span className="num font-semibold">{count as number}</span>
                    </div>
                    <div className="h-1.5 w-full" style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}>
                      <div
                        style={{
                          width: `${pb.payments_counted ? ((count as number) / pb.payments_counted) * 100 : 0}%`,
                          height: "100%",
                          background: tone as string,
                          borderRadius: "2px",
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="sheet overflow-hidden">
            <div className="rule-b px-4 py-3 sm:px-5">
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">
                Month on month
              </h2>
              <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                Yield measured against today&rsquo;s bed inventory throughout.
              </p>
            </div>
            <div className="scroll-x">
              <table className="w-full text-sm">
                <thead>
                  <tr className="rule-b" style={{ background: "var(--paper-sunk)" }}>
                    <th className="label px-4 py-2 text-left font-semibold">Month</th>
                    <th className="label hidden px-3 py-2 text-right font-semibold sm:table-cell">Billed</th>
                    <th className="label px-3 py-2 text-right font-semibold">Collected</th>
                    <th className="label px-3 py-2 text-right font-semibold">Pending</th>
                    <th className="label px-4 py-2 text-right font-semibold">Yield</th>
                  </tr>
                </thead>
                <tbody>
                  {a.trend.map((m) => (
                    <tr
                      key={m.period}
                      className="rule-b last:border-0"
                      style={
                        m.period === currentPeriod
                          ? { background: "color-mix(in oklab, var(--clay) 5%, transparent)" }
                          : undefined
                      }
                    >
                      <td className="px-4 py-2.5 font-medium">{m.label}</td>
                      <td
                        className="num hidden px-3 py-2.5 text-right sm:table-cell"
                        style={{ color: "var(--ink-soft)" }}
                      >
                        {rupeesShort(m.billed)}
                      </td>
                      <td className="num px-3 py-2.5 text-right font-semibold">
                        {rupeesShort(m.collected)}
                      </td>
                      <td
                        className="num px-3 py-2.5 text-right"
                        style={{ color: m.pending > 0 ? "var(--clay)" : "var(--ink-faint)" }}
                      >
                        {m.pending > 0 ? rupeesShort(m.pending) : "—"}
                      </td>
                      <td className="num px-4 py-2.5 text-right font-semibold">
                        {percent(m.yield_rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <dl
          className="num mt-8 flex flex-wrap justify-center gap-x-5 gap-y-1 text-[0.6875rem]"
          style={{ color: "var(--ink-faint)" }}
        >
          {[
            ["Potential", w.potential],
            ["Contracted", w.contracted],
            ["Billed", w.billed],
            ["Collected", w.collected],
          ].map(([label, value]) => (
            <div key={label as string} className="flex gap-1.5 whitespace-nowrap">
              <dt>{label as string}</dt>
              <dd style={{ color: "var(--ink-soft)" }}>{rupees(value as number)}</dd>
            </div>
          ))}
        </dl>
      </main>
    </>
  );
}
