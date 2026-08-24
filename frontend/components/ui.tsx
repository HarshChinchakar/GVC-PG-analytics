import type { ReactNode } from "react";

/** Section heading with a hairline rule and an optional right-hand slot. */
export function SectionHead({
  title,
  meta,
  action,
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rule-b flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-5">
      <h2 className="text-[0.9375rem] font-semibold tracking-tight">{title}</h2>
      <div className="flex items-baseline gap-3">
        {meta && (
          <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
            {meta}
          </span>
        )}
        {action}
      </div>
    </div>
  );
}

/** Empty state. Plain sentence, no illustration, no exclamation. */
export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="px-4 py-8 text-center text-sm sm:px-5" style={{ color: "var(--ink-faint)" }}>
      {children}
    </p>
  );
}

export function Chip({
  tone,
  children,
}: {
  tone: "paid" | "pending" | "notice" | "vacant";
  children: ReactNode;
}) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

/**
 * A headline figure. The number leads at display size; the label sits above it
 * as a running head, and a note can qualify it underneath.
 */
export function Figure({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "clay" | "moss" | "default";
}) {
  const color =
    tone === "clay" ? "var(--clay)" : tone === "moss" ? "var(--moss)" : "var(--ink)";
  return (
    <div className="px-4 py-4 sm:px-5 sm:py-5" style={{ background: "var(--paper-raised)" }}>
      <p className="label">{label}</p>
      <p
        className="num mt-2 text-[1.75rem] leading-none font-semibold tracking-tight sm:text-[2rem]"
        style={{ color }}
      >
        {value}
      </p>
      {note && (
        <p className="mt-2 text-xs leading-snug" style={{ color: "var(--ink-faint)" }}>
          {note}
        </p>
      )}
    </div>
  );
}

/**
 * Horizontal proportion bar. Used for occupancy and collection, where the
 * shape of the number matters as much as the number.
 */
export function Meter({
  value,
  tone = "ink",
}: {
  value: number;
  tone?: "ink" | "moss" | "clay";
}) {
  const pct = Math.max(0, Math.min(100, value));
  const fill =
    tone === "moss" ? "var(--moss)" : tone === "clay" ? "var(--clay)" : "var(--ink)";
  return (
    <div
      className="h-1.5 w-full overflow-hidden"
      style={{ background: "var(--paper-sunk)", borderRadius: "2px" }}
      role="img"
      aria-label={`${pct.toFixed(1)} percent`}
    >
      <div style={{ width: `${pct}%`, height: "100%", background: fill }} />
    </div>
  );
}
