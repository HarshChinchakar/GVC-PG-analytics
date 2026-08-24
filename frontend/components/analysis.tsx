import type { Dimension, Segment } from "@/lib/api";
import { percent, rupees, rupeesShort } from "@/lib/format";

/**
 * Building blocks for the revenue drill-down.
 *
 * Every segment table shares one column set, so a floor, a flat type and a
 * gender are read the same way and can be compared at a glance.
 */

/** A horizontal bar sized against the strongest segment in its group. */
function Bar({
  value,
  max,
  tone = "ink",
}: {
  value: number;
  max: number;
  tone?: "ink" | "clay" | "moss";
}) {
  const width = max > 0 ? Math.max(1.5, (value / max) * 100) : 0;
  const fill =
    tone === "clay" ? "var(--clay)" : tone === "moss" ? "var(--moss)" : "var(--ink)";
  return (
    <div
      className="h-1.5 w-full overflow-hidden"
      style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}
    >
      <div style={{ width: `${width}%`, height: "100%", background: fill, borderRadius: "2px" }} />
    </div>
  );
}

/** Yield: the number with a proportional bar beneath it.
 *
 *  Stacked rather than side by side -- laid out in a row the bar pushed the
 *  percentage out of the column and it was clipped on narrower screens.
 */
function YieldCell({ value, best }: { value: number; best: number }) {
  const tone = value >= 70 ? "moss" : value >= 50 ? "ink" : "clay";
  const colour =
    tone === "moss" ? "var(--moss)" : tone === "clay" ? "var(--clay)" : "var(--ink)";
  return (
    <div style={{ minWidth: "3.75rem" }}>
      <span
        className="num block text-right text-sm font-semibold whitespace-nowrap"
        style={{ color: colour }}
      >
        {percent(value)}
      </span>
      <div className="mt-1">
        <Bar value={value} max={Math.max(best, 1)} tone={tone} />
      </div>
    </div>
  );
}

/**
 * One dimension rendered as a table on desktop and stacked cards on a phone.
 *
 * The same six measures every time: beds, occupancy, what the beds are worth,
 * what came in, revenue per available bed, and yield.
 */
export function DimensionTable({ dimension }: { dimension: Dimension }) {
  const best = Math.max(...dimension.segments.map((s) => s.yield_rate), 1);
  const worst = dimension.segments.reduce(
    (acc, s) => (s.yield_rate < acc.yield_rate ? s : acc),
    dimension.segments[0],
  );

  return (
    <section className="sheet overflow-hidden">
      <div className="rule-b px-4 py-3 sm:px-5">
        <h2 className="text-[0.9375rem] font-semibold tracking-tight">
          {dimension.title}
        </h2>
        <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
          {dimension.question}
        </p>
      </div>

      {/* Desktop table */}
      <div className="scroll-x hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="rule-b" style={{ background: "var(--paper-sunk)" }}>
              <th className="label px-4 py-2 text-left font-semibold">Segment</th>
              <th className="label px-2.5 py-2 text-right font-semibold whitespace-nowrap">Beds</th>
              <th className="label px-2.5 py-2 text-right font-semibold whitespace-nowrap">Occupancy</th>
              <th className="label px-2.5 py-2 text-right font-semibold whitespace-nowrap">Potential</th>
              <th className="label px-2.5 py-2 text-right font-semibold whitespace-nowrap">Collected</th>
              <th className="label px-2.5 py-2 text-right font-semibold whitespace-nowrap" title="Revenue per available bed">
                RevPAB
              </th>
              <th className="label px-4 py-2 text-right font-semibold">Yield</th>
            </tr>
          </thead>
          <tbody>
            {dimension.segments.map((s) => (
              <tr
                key={s.key}
                className="rule-b last:border-0"
                style={
                  s.key === worst?.key && dimension.segments.length > 1
                    ? { background: "color-mix(in oklab, var(--clay) 4%, transparent)" }
                    : undefined
                }
              >
                <td className="px-4 py-2.5">
                  <span className="block font-medium whitespace-nowrap">{s.label}</span>
                  {s.vacant > 0 && (
                    <span
                      className="num block text-xs whitespace-nowrap"
                      style={{ color: "var(--clay)" }}
                    >
                      {s.vacant} empty · {rupeesShort(s.vacancy_loss)}
                    </span>
                  )}
                </td>
                <td className="num px-2.5 py-2.5 text-right whitespace-nowrap" style={{ color: "var(--ink-soft)" }}>
                  {s.occupied}/{s.rentable}
                </td>
                <td className="num px-2.5 py-2.5 text-right whitespace-nowrap">{percent(s.occupancy_rate)}</td>
                <td className="num px-2.5 py-2.5 text-right whitespace-nowrap" style={{ color: "var(--ink-soft)" }}>
                  {rupees(s.potential)}
                </td>
                <td className="num px-2.5 py-2.5 text-right font-semibold whitespace-nowrap">
                  {rupees(s.collected)}
                </td>
                <td className="num px-2.5 py-2.5 text-right whitespace-nowrap">{rupees(s.revpab)}</td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end">
                    <YieldCell value={s.yield_rate} best={best} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Phone cards */}
      <ul className="md:hidden">
        {dimension.segments.map((s) => (
          <li key={s.key} className="rule-b px-4 py-3 last:border-0">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold">{s.label}</span>
              <YieldCell value={s.yield_rate} best={best} />
            </div>
            <dl className="num mt-2 grid grid-cols-3 gap-2 text-xs">
              <div>
                <dt style={{ color: "var(--ink-faint)" }}>Beds</dt>
                <dd className="font-semibold">
                  {s.occupied}/{s.rentable}
                </dd>
              </div>
              <div>
                <dt style={{ color: "var(--ink-faint)" }}>Collected</dt>
                <dd className="font-semibold">{rupeesShort(s.collected)}</dd>
              </div>
              <div>
                <dt style={{ color: "var(--ink-faint)" }}>RevPAB</dt>
                <dd className="font-semibold">{rupees(s.revpab)}</dd>
              </div>
            </dl>
            {s.vacant > 0 && (
              <p className="num mt-1.5 text-xs" style={{ color: "var(--clay)" }}>
                {s.vacant} empty · {rupees(s.vacancy_loss)}/mo
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * The revenue waterfall: full potential stepped down to cash received.
 *
 * Each losing step is shown at its real width relative to potential, so the
 * biggest leak is the one that visibly takes the most off the bar.
 */
export function Waterfall({
  potential,
  vacancyLoss,
  rateLeakage,
  pending,
  collected,
}: {
  potential: number;
  vacancyLoss: number;
  rateLeakage: number;
  pending: number;
  collected: number;
}) {
  const steps = [
    { label: "Empty beds", amount: vacancyLoss, why: "Nobody in them" },
    { label: "Below list price", amount: Math.max(rateLeakage, 0), why: "Let under the asking rent" },
    { label: "Unpaid", amount: pending, why: "Billed but not received" },
  ].filter((s) => s.amount > 0);

  const pct = (n: number) => (potential > 0 ? (n / potential) * 100 : 0);

  return (
    <div className="sheet-raised p-5">
      <h2 className="label mb-1">Where the money goes</h2>
      <p className="mb-4 text-xs" style={{ color: "var(--ink-faint)" }}>
        Full potential of every bed, stepped down to what actually arrived.
      </p>

      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-semibold">Potential at list rent</span>
        <span className="num text-sm font-semibold">{rupees(potential)}</span>
      </div>
      <div
        className="h-3 w-full"
        style={{ background: "var(--ink)", borderRadius: "2px", opacity: 0.15 }}
      />

      <ul className="mt-4 space-y-3">
        {steps.map((s) => (
          <li key={s.label}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium">
                {s.label}
                <span className="ml-1.5" style={{ color: "var(--ink-faint)" }}>
                  {s.why}
                </span>
              </span>
              <span className="num text-sm font-semibold" style={{ color: "var(--clay)" }}>
                −{rupees(s.amount)}
              </span>
            </div>
            <div className="mt-1 h-2 w-full" style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}>
              <div
                style={{
                  width: `${pct(s.amount)}%`,
                  height: "100%",
                  background: "var(--clay)",
                  borderRadius: "2px",
                }}
              />
            </div>
          </li>
        ))}
      </ul>

      <div className="rule-t mt-4 pt-3">
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="text-xs font-semibold">Collected</span>
          <span className="num text-lg font-semibold" style={{ color: "var(--moss)" }}>
            {rupees(collected)}
          </span>
        </div>
        <div className="h-3 w-full" style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}>
          <div
            style={{
              width: `${pct(collected)}%`,
              height: "100%",
              background: "var(--moss)",
              borderRadius: "2px",
            }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Yield split into the three things that cause it.
 *
 * These multiply to yield exactly, which is what makes the screen actionable:
 * a weak number here points at empty beds, at pricing, or at collections —
 * three different problems with three different fixes.
 */
export function FactorBreakdown({
  occupancy,
  rate,
  collection,
  total,
}: {
  occupancy: number;
  rate: number;
  collection: number;
  total: number;
}) {
  const factors = [
    { label: "Beds filled", value: occupancy, note: "by rent value, not headcount" },
    { label: "Billed vs list", value: rate, note: "pricing realised" },
    { label: "Rent collected", value: collection, note: "of what was billed" },
  ];
  const weakest = factors.reduce((a, b) => (b.value < a.value ? b : a));

  return (
    <div className="sheet-raised p-5">
      <h2 className="label mb-1">Why the yield is what it is</h2>
      <p className="mb-4 text-xs" style={{ color: "var(--ink-faint)" }}>
        These three multiply to the yield exactly. The lowest one is the problem
        worth fixing first.
      </p>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
        {factors.map((f, i) => (
          <div key={f.label} className="flex items-center gap-2">
            <div
              className="px-3 py-2"
              style={{
                background:
                  f.label === weakest.label
                    ? "var(--clay-wash)"
                    : "var(--paper-sunk)",
                border: `1px solid ${
                  f.label === weakest.label
                    ? "color-mix(in oklab, var(--clay) 30%, transparent)"
                    : "var(--rule)"
                }`,
                borderRadius: "3px",
                minWidth: "5.5rem",
              }}
            >
              <p
                className="num text-lg font-semibold leading-none"
                style={{
                  color: f.label === weakest.label ? "var(--clay)" : "var(--ink)",
                }}
              >
                {percent(f.value)}
              </p>
              <p className="mt-1 text-[0.625rem] font-semibold uppercase tracking-wide" style={{ color: "var(--ink-faint)" }}>
                {f.label}
              </p>
            </div>
            {i < factors.length - 1 && (
              <span className="num text-sm" style={{ color: "var(--ink-faint)" }} aria-hidden>
                ×
              </span>
            )}
          </div>
        ))}
        <span className="num text-sm" style={{ color: "var(--ink-faint)" }} aria-hidden>
          =
        </span>
        <div
          className="px-3 py-2"
          style={{ background: "var(--ink)", borderRadius: "3px", minWidth: "5.5rem" }}
        >
          <p
            className="num text-lg font-semibold leading-none"
            style={{ color: "var(--paper-raised)" }}
          >
            {percent(total)}
          </p>
          <p
            className="mt-1 text-[0.625rem] font-semibold uppercase tracking-wide"
            style={{ color: "var(--paper-sunk)", opacity: 0.7 }}
          >
            Yield
          </p>
        </div>
      </div>

      <p className="mt-4 text-xs leading-relaxed" style={{ color: "var(--ink-soft)" }}>
        <strong style={{ color: "var(--clay)" }}>{weakest.label}</strong> at{" "}
        {percent(weakest.value)} is holding this building back —{" "}
        {weakest.note}.
      </p>
    </div>
  );
}

/** Best and worst segment of a dimension, called out in words. */
export function Extremes({ dimension }: { dimension: Dimension }) {
  const ranked = [...dimension.segments]
    .filter((s) => s.rentable > 0)
    .sort((a, b) => b.yield_rate - a.yield_rate);
  if (ranked.length < 2) return null;
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];

  return (
    <div className="grid grid-cols-2 gap-px" style={{ background: "var(--rule)" }}>
      {[
        { tag: "Strongest", s: best, tone: "var(--moss)" },
        { tag: "Weakest", s: worst, tone: "var(--clay)" },
      ].map(({ tag, s, tone }) => (
        <div key={tag} className="px-4 py-3" style={{ background: "var(--paper-raised)" }}>
          <p className="label" style={{ color: tone }}>
            {tag}
          </p>
          <p className="mt-1 text-sm font-semibold">{s.label}</p>
          <p className="num mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
            {percent(s.yield_rate)} yield · {rupees(s.revpab)}/bed
          </p>
        </div>
      ))}
    </div>
  );
}
