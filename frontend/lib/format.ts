/**
 * Formatting helpers.
 *
 * Rupees use the Indian digit grouping (2,50,000 not 250,000) because that is
 * how the owner reads and says these numbers. Everything comes from the backend
 * as whole rupees, so there is never a decimal to render.
 */

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function rupees(value: number): string {
  return `₹${inr.format(value)}`;
}

/** Compact form for headline tiles: ₹5.6L, ₹1.2Cr. */
export function rupeesShort(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_00_00_000) return `₹${(value / 1_00_00_000).toFixed(2)}Cr`;
  if (abs >= 1_00_000) return `₹${(value / 1_00_000).toFixed(2)}L`;
  if (abs >= 1_000) return `₹${inr.format(value)}`;
  return `₹${value}`;
}

export function percent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

export function fullDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** "2026-08" -> "August 2026", for the month picker. */
export function periodLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

/** Digits only, for tel: links on the defaulters list. */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}
