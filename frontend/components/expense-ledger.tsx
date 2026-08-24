"use client";

import { useState } from "react";
import type { ExpenseMonth, ExpenseRow } from "@/lib/api";
import { fullDate, rupees, shortDate } from "@/lib/format";

/**
 * The month's entries.
 *
 * Every row carries a Repeat button, because the second most common way to
 * record spend is "the same as last time". Voided rows stay visible, struck
 * through with their reason — money that was wrongly recorded should be seen
 * to have been corrected, not silently disappear.
 */

const PAID_FROM_LABEL: Record<string, string> = {
  site_cash: "Petty cash",
  business_account: "Business account",
  personal: "Own pocket",
};

function VoidButton({
  row,
  onVoided,
}: {
  row: ExpenseRow;
  onVoided: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!asking) {
    return (
      <button
        type="button"
        onClick={() => setAsking(true)}
        className="text-xs font-semibold underline decoration-dotted underline-offset-2"
        style={{ color: "var(--ink-faint)" }}
      >
        Void
      </button>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        type="text"
        value={reason}
        autoFocus
        onChange={(e) => setReason(e.target.value)}
        placeholder="Why is this wrong?"
        className="field"
        style={{ maxWidth: "16rem", padding: "0.375rem 0.625rem", fontSize: "0.8125rem" }}
      />
      <button
        type="button"
        disabled={busy || reason.trim().length < 3}
        onClick={async () => {
          setBusy(true);
          setError(null);
          const res = await fetch("/api/expenses/void", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expense_id: row.id, reason: reason.trim() }),
          }).catch(() => null);
          const body = await res?.json().catch(() => ({}));
          if (!res?.ok) {
            setError(body?.detail ?? "Could not void that");
            setBusy(false);
            return;
          }
          setAsking(false);
          setBusy(false);
          onVoided();
        }}
        className="btn btn-quiet"
        style={{ padding: "0.375rem 0.75rem", fontSize: "0.75rem" }}
      >
        {busy ? "…" : "Confirm void"}
      </button>
      <button
        type="button"
        onClick={() => {
          setAsking(false);
          setError(null);
        }}
        className="text-xs"
        style={{ color: "var(--ink-faint)" }}
      >
        Cancel
      </button>
      {error && (
        <span className="text-xs" style={{ color: "var(--clay)" }} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function ExpenseLedger({
  data,
  onRepeat,
  onVoided,
}: {
  data: ExpenseMonth;
  onRepeat: (row: ExpenseRow) => void;
  onVoided: () => void;
}) {
  const [showVoided, setShowVoided] = useState(false);
  const rows = data.expenses.filter(
    (r) => showVoided || r.status !== "void",
  );

  return (
    <section className="sheet overflow-hidden">
      <div className="rule-b flex flex-wrap items-baseline justify-between gap-3 px-4 py-3 sm:px-5">
        <h2 className="text-[0.9375rem] font-semibold tracking-tight">
          {data.period_label} entries
        </h2>
        <div className="flex items-baseline gap-3">
          {data.voided_count > 0 && (
            <button
              type="button"
              onClick={() => setShowVoided((v) => !v)}
              className="text-xs font-semibold underline decoration-dotted underline-offset-2"
              style={{ color: "var(--ink-faint)" }}
            >
              {showVoided ? "Hide" : "Show"} {data.voided_count} voided
            </button>
          )}
          <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
            {data.entry_count} · {rupees(data.total)}
          </span>
        </div>
      </div>

      {rows.length === 0 ? (
        <p
          className="px-4 py-10 text-center text-sm"
          style={{ color: "var(--ink-faint)" }}
        >
          Nothing recorded for {data.period_label} yet.
        </p>
      ) : (
        <ul>
          {rows.map((row) => {
            const voided = row.status === "void";
            return (
              <li
                key={row.id}
                className="rule-b px-4 py-3 last:border-0 sm:px-5"
                style={voided ? { opacity: 0.6 } : undefined}
              >
                <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-baseline gap-2">
                      <span
                        className="text-sm font-semibold"
                        style={voided ? { textDecoration: "line-through" } : undefined}
                      >
                        {row.payee}
                      </span>
                      <span
                        className="px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wide"
                        style={{
                          background: "var(--paper-sunk)",
                          color: "var(--ink-soft)",
                          borderRadius: "2px",
                        }}
                      >
                        {row.category_label}
                      </span>
                      {row.template_name && (
                        <span
                          className="text-[0.625rem] font-semibold uppercase tracking-wide"
                          style={{ color: "var(--ink-faint)" }}
                        >
                          recurring
                        </span>
                      )}
                      {row.paid_from === "personal" && !row.reimbursed_on && !voided && (
                        <span
                          className="px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase"
                          style={{
                            background: "var(--amber-wash)",
                            color: "var(--amber)",
                            borderRadius: "2px",
                          }}
                        >
                          to reimburse
                        </span>
                      )}
                    </p>
                    {row.description && (
                      <p className="mt-0.5 text-xs" style={{ color: "var(--ink-soft)" }}>
                        {row.description}
                      </p>
                    )}
                    <p className="num mt-1 text-xs" style={{ color: "var(--ink-faint)" }}>
                      {shortDate(row.expense_date)} · {PAID_FROM_LABEL[row.paid_from] ?? row.paid_from}
                      {" · "}
                      {row.payment_mode.replace("_", " ")} · by {row.paid_by}
                    </p>
                    {voided && row.void_reason && (
                      <p className="mt-1 text-xs" style={{ color: "var(--clay)" }}>
                        Voided — {row.void_reason}
                      </p>
                    )}
                  </div>

                  <div className="shrink-0 text-right">
                    <p
                      className="num text-base font-semibold"
                      style={
                        voided
                          ? { textDecoration: "line-through", color: "var(--ink-faint)" }
                          : undefined
                      }
                    >
                      {rupees(row.amount)}
                    </p>
                    {!voided && (
                      <div className="mt-1 flex items-baseline justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => onRepeat(row)}
                          className="text-xs font-semibold underline decoration-dotted underline-offset-2"
                          style={{ color: "var(--clay)" }}
                        >
                          Repeat
                        </button>
                        <VoidButton row={row} onVoided={onVoided} />
                      </div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
