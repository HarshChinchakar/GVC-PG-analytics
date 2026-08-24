import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import {
  fullDate, percent, rupees, rupeesShort, shortDate, telHref,
} from "@/lib/format";
import { TopBar } from "@/components/top-bar";
import { MonthPicker } from "@/components/month-picker";
import { Chip, Empty, Figure, Meter, SectionHead } from "@/components/ui";

export const dynamic = "force-dynamic";

/** The rent panel: clickable for the owner, static for a manager. */
function RentPanel({
  isOwner,
  href,
  children,
}: {
  isOwner: boolean;
  href: string;
  children: React.ReactNode;
}) {
  if (!isOwner) {
    return <div className="sheet-raised p-5">{children}</div>;
  }
  return (
    <Link
      href={href}
      className="sheet-raised sheet-interactive block p-5"
      style={{ textDecoration: "none", color: "inherit" }}
    >
      {children}
    </Link>
  );
}

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ year?: string; month?: string }>;
};

export default async function DashboardPage({ params, searchParams }: Props) {
  if (!(await getToken())) redirect("/login");

  const { id } = await params;
  const { year, month } = await searchParams;

  let user, d;
  try {
    [user, d] = await Promise.all([
      api.me(),
      api.dashboard(
        id,
        year ? Number(year) : undefined,
        month ? Number(month) : undefined,
      ),
    ]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/logout?expired=1");
      // The backend answers 404 for another manager's building, so an
      // unauthorised guess and a genuine typo look identical from here.
      if (error.status === 404) notFound();
    }
    throw error;
  }

  const { occupancy: o, rent: r, vacancy: v, residents: res } = d;
  const currentPeriod = `${d.period_year}-${String(d.period_month).padStart(2, "0")}`;
  const isOwner = user.role === "super_admin";

  return (
    <>
      <TopBar
        userName={user.full_name}
        role={user.role}
        locationName={d.location_name}
        locationCode={d.location_code}
      />

      <main className="mx-auto max-w-[84rem] px-4 py-6 sm:px-6 sm:py-8">
        {/* --- page head ------------------------------------------------ */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label mb-1.5">Dashboard</p>
            <h1
              className="text-3xl tracking-tight sm:text-[2.5rem] sm:leading-none"
              style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
            >
              {d.location_name}
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
              Rent figures for{" "}
              <strong style={{ color: "var(--ink)" }}>{d.period_label}</strong>.
              Occupancy and deposits are live.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <MonthPicker
              periods={d.available_periods.length ? d.available_periods : [currentPeriod]}
              current={currentPeriod}
              locationId={d.location_id}
            />
            <Link
              href={`/sites/${d.location_id}/expenses?year=${d.period_year}&month=${d.period_month}`}
              className="btn btn-quiet"
            >
              Expenses
            </Link>
            <Link href="/sites" className="btn btn-quiet sm:hidden">
              Switch site
            </Link>
          </div>
        </div>

        {/* --- headline: occupancy + collection -------------------------- */}
        <section className="mb-4 grid gap-4 lg:grid-cols-2">
          {/* Open to managers too -- the board is operational, not financial. */}
          <Link
            href={`/sites/${d.location_id}/occupancy?year=${d.period_year}&month=${d.period_month}`}
            className="sheet-raised sheet-interactive block p-5"
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 className="label">Occupancy</h2>
              <span
                className="flex items-center gap-1 text-xs font-semibold"
                style={{ color: "var(--clay)" }}
              >
                See the board
                <span aria-hidden>&rarr;</span>
              </span>
            </div>
            <div className="flex items-end gap-4">
              <p
                className="num text-[3rem] leading-[0.9] font-semibold tracking-tight sm:text-[3.5rem]"
              >
                {percent(o.occupancy_rate)}
              </p>
              <p className="num pb-1.5 text-sm" style={{ color: "var(--ink-soft)" }}>
                {o.occupied + o.on_notice} of {o.total_beds - o.blocked} rentable beds
              </p>
            </div>
            <div className="mt-4">
              <Meter value={o.occupancy_rate} />
            </div>
            <dl className="num mt-4 grid grid-cols-5 gap-2 text-center">
              {[
                ["Occupied", o.occupied, "var(--ink)"],
                ["Notice", o.on_notice, "var(--slate)"],
                ["Booked", o.booked, "var(--indigo)"],
                ["Vacant", o.available, "var(--clay)"],
                ["Blocked", o.blocked, "var(--ink-faint)"],
              ].map(([label, value, color]) => (
                <div key={label as string} className="rule-t pt-2.5">
                  <dd className="text-lg font-semibold" style={{ color: color as string }}>
                    {value as number}
                  </dd>
                  <dt
                    className="mt-0.5 text-[0.625rem] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--ink-faint)", fontFamily: "var(--font-sans)" }}
                  >
                    {label as string}
                  </dt>
                </div>
              ))}
            </dl>
            {o.blocked > 0 && (
              <p className="mt-3 text-xs" style={{ color: "var(--ink-faint)" }}>
                {o.blocked} bed out of service — excluded from occupancy.
              </p>
            )}
          </Link>

          {/* For the owner the whole rent panel is the doorway to the revenue
              drill-down. Managers do not get that link at all: the analysis is
              owner-only, so offering it would lead them to a 404. */}
          <RentPanel
            isOwner={isOwner}
            href={`/sites/${d.location_id}/rent?year=${d.period_year}&month=${d.period_month}`}
          >
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 className="label">Rent collected · {d.period_label}</h2>
              {isOwner ? (
                <span
                  className="flex items-center gap-1 text-xs font-semibold"
                  style={{ color: "var(--clay)" }}
                >
                  Break it down
                  <span aria-hidden>&rarr;</span>
                </span>
              ) : (
                <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
                  {r.paid_count} paid / {r.pending_count} pending
                </span>
              )}
            </div>
            <div className="flex items-end gap-4">
              <p
                className="num text-[3rem] leading-[0.9] font-semibold tracking-tight sm:text-[3.5rem]"
                style={{ color: r.collection_rate >= 95 ? "var(--moss)" : "var(--ink)" }}
              >
                {percent(r.collection_rate)}
              </p>
              <p className="num pb-1.5 text-sm" style={{ color: "var(--ink-soft)" }}>
                {rupees(r.collected_rent)} of {rupees(r.expected_rent)}
              </p>
            </div>
            <div className="mt-4">
              <Meter value={r.collection_rate} tone={r.collection_rate >= 95 ? "moss" : "clay"} />
            </div>
            <dl className="num mt-4 grid grid-cols-3 gap-2">
              {[
                ["Expected", rupees(r.expected_rent), "var(--ink)"],
                ["Collected", rupees(r.collected_rent), "var(--moss)"],
                ["Pending", rupees(r.pending_rent), r.pending_rent > 0 ? "var(--clay)" : "var(--ink-faint)"],
              ].map(([label, value, color]) => (
                <div key={label} className="rule-t pt-2.5">
                  <dt
                    className="text-[0.625rem] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--ink-faint)", fontFamily: "var(--font-sans)" }}
                  >
                    {label}
                  </dt>
                  <dd className="mt-1 text-sm font-semibold" style={{ color }}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {isOwner && (
              <p className="mt-3 text-xs" style={{ color: "var(--ink-faint)" }}>
                {r.paid_count} paid · {r.pending_count} pending — open for yield
                by floor, room type and gender.
              </p>
            )}
          </RentPanel>
        </section>

        {/* --- secondary figures ----------------------------------------- */}
        <section
          className="sheet mb-8 grid grid-cols-2 gap-px overflow-hidden md:grid-cols-4"
          style={{ background: "var(--rule)" }}
        >
          <Figure
            label="Vacancy loss / month"
            value={rupeesShort(v.potential_monthly_loss)}
            note={`${v.vacant_beds} empty ${v.vacant_beds === 1 ? "bed" : "beds"}, at each bed's own rent`}
            tone={v.potential_monthly_loss > 0 ? "clay" : "default"}
          />
          <Figure
            label="Residents living here"
            value={String(res.living_here)}
            note={`${res.active} active · ${res.notice} under notice`}
          />
          <Figure
            label="Leaving in 30 days"
            value={String(d.upcoming_move_outs.length)}
            note={
              d.upcoming_move_outs.length
                ? `Next: ${shortDate(d.upcoming_move_outs[0].expected_move_out_date)}`
                : "No notices served"
            }
          />
          {isOwner && d.deposits ? (
            <Figure
              label="Deposits held"
              value={rupeesShort(d.deposits.held)}
              note={
                d.deposits.approved_unpaid > 0
                  ? `${rupees(d.deposits.approved_unpaid)} refund due`
                  : `${rupees(d.deposits.refunded_to_date)} refunded to date`
              }
            />
          ) : (
            <Figure
              label="Beds out of service"
              value={String(o.blocked)}
              note={o.blocked ? "Excluded from occupancy" : "All beds in service"}
            />
          )}
        </section>

        {/* --- operational lists ----------------------------------------- */}
        <div className="grid items-start gap-6 xl:grid-cols-[1.4fr_1fr]">
          {/* Pending payments — the most-used list, so it leads. */}
          <section className="sheet overflow-hidden">
            <SectionHead
              title="Rent pending"
              meta={
                d.pending_payments.length
                  ? `${d.pending_payments.length} · ${rupees(r.pending_rent)}`
                  : undefined
              }
            />
            {d.pending_payments.length === 0 ? (
              <Empty>Every resident has paid for {d.period_label}.</Empty>
            ) : (
              <>
                {/* Desktop: a proper table. */}
                <div className="scroll-x hidden sm:block">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="rule-b" style={{ background: "var(--paper-sunk)" }}>
                        {["Resident", "Flat", "Bed", "Due", "Amount"].map((h, i) => (
                          <th
                            key={h}
                            className="label px-4 py-2 font-semibold"
                            style={{ textAlign: i >= 3 ? "right" : "left" }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {d.pending_payments.map((p) => (
                        <tr key={p.rent_record_id} className="rule-b last:border-0">
                          <td className="px-4 py-2.5">
                            <div className="font-medium">{p.resident_name}</div>
                            <a
                              href={telHref(p.phone)}
                              className="num text-xs underline decoration-dotted underline-offset-2"
                              style={{ color: "var(--ink-faint)" }}
                            >
                              {p.phone}
                            </a>
                          </td>
                          <td className="num px-4 py-2.5" style={{ color: "var(--ink-soft)" }}>
                            {p.flat_number ?? "—"}
                          </td>
                          <td className="num px-4 py-2.5">{p.bed_label ?? "—"}</td>
                          <td
                            className="num px-4 py-2.5 text-right"
                            style={{ color: "var(--ink-faint)" }}
                          >
                            {shortDate(p.due_date)}
                          </td>
                          <td
                            className="num px-4 py-2.5 text-right font-semibold"
                            style={{ color: "var(--clay)" }}
                          >
                            {rupees(p.amount_due)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Phone: one row per card, phone number tappable. */}
                <ul className="sm:hidden">
                  {d.pending_payments.map((p) => (
                    <li
                      key={p.rent_record_id}
                      className="rule-b flex items-start justify-between gap-3 px-4 py-3 last:border-0"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{p.resident_name}</p>
                        <p className="num mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                          {p.flat_number ?? "—"} · {p.bed_label ?? "—"}
                        </p>
                        <a
                          href={telHref(p.phone)}
                          className="num mt-1 inline-block text-xs font-medium underline decoration-dotted underline-offset-2"
                          style={{ color: "var(--clay)" }}
                        >
                          Call {p.phone}
                        </a>
                      </div>
                      <span
                        className="num shrink-0 text-sm font-semibold"
                        style={{ color: "var(--clay)" }}
                      >
                        {rupees(p.amount_due)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <div className="grid gap-6">
            {/* Upcoming move-outs */}
            <section className="sheet overflow-hidden">
              <SectionHead
                title="Leaving soon"
                meta={d.upcoming_move_outs.length ? "next 30 days" : undefined}
              />
              {d.upcoming_move_outs.length === 0 ? (
                <Empty>No move-out notices are open.</Empty>
              ) : (
                <ul>
                  {d.upcoming_move_outs.map((n) => (
                    <li
                      key={n.id}
                      className="rule-b flex items-center justify-between gap-3 px-4 py-3 last:border-0 sm:px-5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{n.resident_name}</p>
                        <p className="num mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                          {n.bed_label} · notice {shortDate(n.notice_date)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="num text-sm font-semibold">
                          {shortDate(n.expected_move_out_date)}
                        </p>
                        <p className="num text-xs" style={{ color: "var(--amber)" }}>
                          {n.days_remaining !== null && n.days_remaining >= 0
                            ? `in ${n.days_remaining}d`
                            : "overdue"}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Vacant beds */}
            <section className="sheet overflow-hidden">
              <SectionHead
                title="Vacant beds"
                meta={
                  d.vacant_beds.length
                    ? `${d.vacant_beds.length} · ${rupees(v.potential_monthly_loss)}/mo`
                    : undefined
                }
              />
              {d.vacant_beds.length === 0 ? (
                <Empty>Every bed is taken.</Empty>
              ) : (
                <ul className="flex flex-wrap gap-2 px-4 py-4 sm:px-5">
                  {d.vacant_beds.map((b) => (
                    <li
                      key={b.id}
                      className="num flex items-baseline gap-2 px-2.5 py-1.5"
                      style={{
                        background: "var(--paper-sunk)",
                        border: "1px solid var(--rule)",
                        borderRadius: "2px",
                      }}
                      title={`${b.is_attached ? "Attached" : "Non-attached"} · ${rupees(b.default_rent)} per month`}
                    >
                      <span className="text-xs font-semibold">{b.label}</span>
                      <span className="text-[0.6875rem]" style={{ color: "var(--ink-faint)" }}>
                        {rupees(b.default_rent)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Beds under notice — future capacity, distinct from vacant. */}
            {d.freeing_soon.length > 0 && (
              <section className="sheet overflow-hidden">
                <SectionHead title="Freeing up" meta={`${d.freeing_soon.length} beds`} />
                <ul>
                  {d.freeing_soon.map((b) => (
                    <li
                      key={b.id}
                      className="rule-b flex items-center justify-between gap-3 px-4 py-2.5 last:border-0 sm:px-5"
                    >
                      <div className="flex items-baseline gap-2.5">
                        <span className="num text-sm font-semibold">{b.label}</span>
                        <span className="truncate text-xs" style={{ color: "var(--ink-soft)" }}>
                          {b.resident_name}
                        </span>
                      </div>
                      <Chip tone="notice">{fullDate(b.expected_vacant_on)}</Chip>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>

        <p
          className="num mt-8 text-center text-[0.6875rem]"
          style={{ color: "var(--ink-faint)" }}
        >
          Figures generated {new Date(d.generated_at).toLocaleString("en-IN")}
        </p>
      </main>
    </>
  );
}
