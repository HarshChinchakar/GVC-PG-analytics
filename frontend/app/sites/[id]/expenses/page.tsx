import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import { rupees, rupeesShort } from "@/lib/format";
import { TopBar } from "@/components/top-bar";
import { MonthPicker } from "@/components/month-picker";
import { ExpenseWorkspace } from "@/components/expense-form";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ year?: string; month?: string }>;
};

/**
 * Money out, per site and per month.
 *
 * Open to managers as well as owners — a manager who buys cleaning supplies
 * has to be able to file it, or the spend never gets recorded at all. Which
 * *categories* each role may use is decided server-side.
 */
export default async function ExpensesPage({ params, searchParams }: Props) {
  if (!(await getToken())) redirect("/login");

  const { id } = await params;
  const { year, month } = await searchParams;

  let user, data;
  try {
    [user, data] = await Promise.all([
      api.me(),
      api.expenses(
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

  const currentPeriod = `${data.period_year}-${String(data.period_month).padStart(2, "0")}`;
  const periods = data.trend.length
    ? data.trend.map((t) => t.period).reverse()
    : [currentPeriod];
  const biggest = data.by_category[0];
  const previous = data.trend.length > 1 ? data.trend[data.trend.length - 2] : null;
  const change =
    previous && previous.total > 0
      ? ((data.total - previous.total) / previous.total) * 100
      : null;

  return (
    <>
      <TopBar
        userName={user.full_name}
        role={user.role}
        locationName={data.location_name}
        locationCode={data.location_code}
      />

      <main className="mx-auto max-w-[72rem] px-4 py-6 sm:px-6 sm:py-8">
        <Link
          href={`/sites/${data.location_id}`}
          className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold"
          style={{ color: "var(--ink-faint)" }}
        >
          <span aria-hidden>&larr;</span> Back to dashboard
        </Link>

        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label mb-1.5">Expenses</p>
            <h1
              className="text-3xl tracking-tight sm:text-[2.5rem] sm:leading-none"
              style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
            >
              {data.location_name}
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              Everything paid out in{" "}
              <strong style={{ color: "var(--ink)" }}>{data.period_label}</strong>.
            </p>
          </div>
          <MonthPicker
            periods={periods}
            current={currentPeriod}
            locationId={data.location_id}
            basePath={`/sites/${data.location_id}/expenses`}
          />
        </div>

        {/* Four figures only — this page is for entry, not analysis. The
            revenue-versus-spend picture belongs on the financial dashboard. */}
        <section
          className="sheet-raised mb-4 grid grid-cols-2 gap-px overflow-hidden lg:grid-cols-4"
          style={{ background: "var(--rule)" }}
        >
          {[
            {
              label: "Spent this month",
              value: rupees(data.total),
              note: `${data.entry_count} ${data.entry_count === 1 ? "entry" : "entries"}`,
              tone: "var(--ink)",
            },
            {
              label: "Largest category",
              value: biggest ? rupeesShort(biggest.amount) : "—",
              note: biggest ? `${biggest.label} · ${biggest.share}%` : "nothing recorded",
              tone: "var(--ink)",
            },
            {
              label: "Vs last month",
              value: change === null ? "—" : `${change > 0 ? "+" : ""}${change.toFixed(0)}%`,
              note: previous ? `${previous.label}: ${rupeesShort(previous.total)}` : "no history",
              tone: change !== null && change > 10 ? "var(--clay)" : "var(--ink)",
            },
            {
              label: "Owed back to staff",
              value: rupees(data.reimbursements_owed),
              note:
                data.reimbursements_owed > 0
                  ? "paid from own pocket"
                  : "nothing outstanding",
              tone: data.reimbursements_owed > 0 ? "var(--amber)" : "var(--ink-faint)",
            },
          ].map((m) => (
            <div
              key={m.label}
              className="px-4 py-4 sm:px-5"
              style={{ background: "var(--paper-raised)" }}
            >
              <p className="label">{m.label}</p>
              <p
                className="num mt-2 text-[1.5rem] leading-none font-semibold tracking-tight sm:text-[1.75rem]"
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

        {data.by_category.length > 0 && (
          <section className="sheet mb-4 overflow-hidden">
            <div className="rule-b px-4 py-3 sm:px-5">
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">
                Where it went
              </h2>
            </div>
            <ul className="px-4 py-3 sm:px-5">
              {data.by_category.map((c) => (
                <li key={c.category} className="mb-2.5 last:mb-0">
                  <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                    <span>
                      {c.label}
                      <span
                        className="num ml-2 text-xs"
                        style={{ color: "var(--ink-faint)" }}
                      >
                        {c.count}
                      </span>
                    </span>
                    <span className="num font-semibold">
                      {rupees(c.amount)}
                      <span
                        className="ml-2 text-xs font-normal"
                        style={{ color: "var(--ink-faint)" }}
                      >
                        {c.share}%
                      </span>
                    </span>
                  </div>
                  <div
                    className="h-1.5 w-full"
                    style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}
                  >
                    <div
                      style={{
                        width: `${c.share}%`,
                        height: "100%",
                        background:
                          c.group === "Fixed" ? "var(--ink)" : "var(--clay)",
                        borderRadius: "2px",
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <ExpenseWorkspace data={data} />
      </main>
    </>
  );
}
