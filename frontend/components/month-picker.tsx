"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { periodLabel } from "@/lib/format";

/**
 * Month selector.
 *
 * Driven by the months that actually have rent data, so the owner can never
 * land on an empty month and wonder whether the figures are broken.
 */
export function MonthPicker({
  periods,
  current,
  locationId,
  basePath,
}: {
  periods: string[];
  current: string;
  locationId: string;
  /** Where to navigate on change. Defaults to the dashboard, so the picker
   *  keeps you on the analysis page when it is used there. */
  basePath?: string;
}) {
  const router = useRouter();
  const params = useSearchParams();

  return (
    <label className="flex items-center gap-2">
      <span className="label">Month</span>
      <select
        value={current}
        onChange={(e) => {
          const [year, month] = e.target.value.split("-");
          const next = new URLSearchParams(params.toString());
          next.set("year", year);
          next.set("month", String(Number(month)));
          router.push(`${basePath ?? `/sites/${locationId}`}?${next}`);
        }}
        className="num"
        style={{
          background: "var(--paper-raised)",
          border: "1px solid var(--rule-strong)",
          borderRadius: "3px",
          padding: "0.3125rem 0.5rem",
          fontSize: "0.8125rem",
          fontWeight: 600,
          color: "var(--ink)",
        }}
      >
        {periods.map((p) => (
          <option key={p} value={p}>
            {periodLabel(p)}
          </option>
        ))}
      </select>
    </label>
  );
}
