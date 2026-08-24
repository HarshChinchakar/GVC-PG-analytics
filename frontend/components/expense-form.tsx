"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { DueItem, ExpenseMonth, ExpenseOptions, ExpenseRow } from "@/lib/api";
import { rupees } from "@/lib/format";
import { ExpenseLedger } from "./expense-ledger";

/**
 * Recording spend, with as little typing as the job allows.
 *
 * Most PG costs repeat: the lease, four salaries, the water tanker, the gas.
 * A form that has to be filled from scratch twelve times a year is a form that
 * quietly stops being filled, and then the financial picture is wrong. So
 * there are three ways in, in decreasing order of speed:
 *
 *   1. **Due this month** — a recurring item, pre-filled, one tap to confirm.
 *   2. **Repeat** — any past entry, copied forward to today.
 *   3. The form, for genuinely new spend.
 *
 * Every path funnels through the same submit, which carries an idempotency
 * key minted per attempt, so a double-tap or a retry on a bad connection
 * cannot book the money twice.
 */

const LAST_USED_KEY = "pg.expense.lastUsed";

type Draft = {
  location_id: string;
  category: string;
  payee: string;
  amount: string;
  expense_date: string;
  payment_mode: string;
  paid_from: string;
  description: string;
  payment_reference: string;
  template_id: string | null;
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function emptyDraft(locationId: string, options: ExpenseOptions, remembered: Partial<Draft>): Draft {
  const firstAllowed = options.categories.find((c) => c.allowed)?.value ?? "misc";
  return {
    location_id: locationId,
    category: firstAllowed,
    payee: "",
    amount: "",
    expense_date: todayISO(),
    // Remembering the last payment mode saves a tap on almost every entry:
    // a given site pays for most things the same way.
    payment_mode: remembered.payment_mode ?? "cash",
    paid_from: remembered.paid_from ?? "site_cash",
    description: "",
    payment_reference: "",
    template_id: null,
  };
}

export function ExpenseWorkspace({ data }: { data: ExpenseMonth }) {
  const router = useRouter();
  const options = data.options;

  const [remembered, setRemembered] = useState<Partial<Draft>>({});
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(data.location_id, options, {}));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  // localStorage is read after mount so the server and client render the same
  // markup; hydration mismatches on a form are ugly and hard to trace.
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(LAST_USED_KEY) ?? "{}");
      setRemembered(saved);
      setDraft((d) => ({
        ...d,
        payment_mode: saved.payment_mode ?? d.payment_mode,
        paid_from: saved.paid_from ?? d.paid_from,
      }));
    } catch {
      /* first visit, or storage blocked — defaults are fine */
    }
  }, []);

  const grouped = useMemo(() => {
    const groups = new Map<string, ExpenseOptions["categories"]>();
    for (const c of options.categories) {
      if (!groups.has(c.group)) groups.set(c.group, []);
      groups.get(c.group)!.push(c);
    }
    return [...groups.entries()];
  }, [options.categories]);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
    setError(null);
  }

  /** Pre-fill from a recurring item that has not been booked yet. */
  function fillFromDue(item: DueItem) {
    setDraft({
      location_id: data.location_id,
      category: item.category,
      payee: item.payee,
      amount: item.default_amount ? String(item.default_amount) : "",
      expense_date: item.suggested_date,
      payment_mode: item.payment_mode,
      paid_from: item.paid_from,
      description: item.name,
      payment_reference: "",
      template_id: item.id,
    });
    setOpen(true);
    setError(null);
    setDone(null);
    requestAnimationFrame(() =>
      document.getElementById("expense-amount")?.focus(),
    );
  }

  /** Copy a past entry forward to today. */
  function repeat(row: ExpenseRow) {
    setDraft({
      location_id: data.location_id,
      category: row.category,
      payee: row.payee,
      amount: String(row.amount),
      expense_date: todayISO(),
      payment_mode: row.payment_mode,
      paid_from: row.paid_from,
      description: row.description ?? "",
      payment_reference: "",
      template_id: null,
    });
    setOpen(true);
    setError(null);
    setDone(null);
    // Scroll the form itself into view rather than jumping to the page top.
    // The header is sticky, so a naive scroll-to-top leaves the form's first
    // control sitting underneath it -- invisible, and untappable.
    requestAnimationFrame(() => {
      document.getElementById("expense-form")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
      document.getElementById("expense-amount")?.focus();
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;

    const amount = Number(draft.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter an amount greater than zero");
      return;
    }
    if (!draft.payee.trim()) {
      setError("Say who was paid");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/expenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location_id: draft.location_id,
          category: draft.category,
          payee: draft.payee.trim(),
          amount: Math.round(amount),
          expense_date: draft.expense_date,
          payment_mode: draft.payment_mode,
          paid_from: draft.paid_from,
          description: draft.description.trim() || null,
          payment_reference: draft.payment_reference.trim() || null,
          template_id: draft.template_id,
          // Minted here, per attempt: the server treats a repeat of this key
          // as "already done" rather than as a second payment.
          idempotency_key: crypto.randomUUID(),
        }),
      });
      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        setError(body?.detail ?? "Could not save that");
        setBusy(false);
        return;
      }

      try {
        localStorage.setItem(
          LAST_USED_KEY,
          JSON.stringify({
            payment_mode: draft.payment_mode,
            paid_from: draft.paid_from,
          }),
        );
      } catch {
        /* storage blocked; not worth failing the save over */
      }

      setDone(`${rupees(Math.round(amount))} to ${draft.payee.trim()} recorded`);
      setDraft(emptyDraft(data.location_id, options, draft));
      setBusy(false);
      router.refresh();
    } catch {
      setError("Cannot reach the server. Nothing was saved.");
      setBusy(false);
    }
  }

  const allowedCategory = options.categories.find((c) => c.value === draft.category);

  return (
    <>
      {/* --- due this month: the one-tap path -------------------------- */}
      {data.due_this_month.length > 0 && (
        <section className="sheet-raised mb-4 overflow-hidden">
          <div className="rule-b flex items-baseline justify-between gap-3 px-4 py-3">
            <div>
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">
                Still to record this month
              </h2>
              <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                Recurring costs with no entry yet for {data.period_label}.
              </p>
            </div>
            <span className="num text-xs font-semibold" style={{ color: "var(--clay)" }}>
              {data.due_this_month.length}
            </span>
          </div>
          <ul className="flex flex-wrap gap-2 px-4 py-3">
            {data.due_this_month.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={!item.allowed}
                  onClick={() => fillFromDue(item)}
                  title={
                    item.allowed
                      ? `Record ${item.name}`
                      : "Only an owner can file this category"
                  }
                  className="flex items-baseline gap-2 px-3 py-2 text-left transition-colors"
                  style={{
                    background: item.allowed ? "var(--paper-sunk)" : "transparent",
                    border: `1px solid ${item.allowed ? "var(--rule-strong)" : "var(--rule)"}`,
                    borderRadius: "3px",
                    cursor: item.allowed ? "pointer" : "not-allowed",
                    opacity: item.allowed ? 1 : 0.45,
                  }}
                >
                  <span className="text-sm font-semibold">{item.name}</span>
                  {item.default_amount ? (
                    <span className="num text-xs" style={{ color: "var(--ink-faint)" }}>
                      {rupees(item.default_amount)}
                    </span>
                  ) : (
                    <span className="text-xs" style={{ color: "var(--ink-faint)" }}>
                      amount varies
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* --- the form --------------------------------------------------- */}
      <section
        id="expense-form"
        className="sheet-raised mb-6 overflow-hidden"
        // Keeps the section clear of the sticky header when scrolled to.
        style={{ scrollMarginTop: "5rem" }}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="rule-b flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
          aria-expanded={open}
        >
          <span className="text-[0.9375rem] font-semibold tracking-tight">
            Record an expense
          </span>
          <span className="text-xs font-semibold" style={{ color: "var(--clay)" }}>
            {open ? "Hide" : "Open"} <span aria-hidden>{open ? "↑" : "↓"}</span>
          </span>
        </button>

        {done && (
          <p
            className="rule-b px-4 py-2.5 text-sm"
            role="status"
            style={{ background: "var(--moss-wash)", color: "var(--moss)" }}
          >
            {done}
          </p>
        )}

        {open && (
          <form onSubmit={submit} className="px-4 py-4" noValidate>
            {/* Site first: an expense with no site is meaningless. */}
            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <label className="block" htmlFor="expense-site">
                <span className="label mb-1.5 block">Site</span>
                <select
                  id="expense-site"
                  value={draft.location_id}
                  onChange={(e) => set("location_id", e.target.value)}
                  className="field"
                  disabled={data.sites.length === 1}
                >
                  {data.sites.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label mb-1.5 block">Date</span>
                <input
                  type="date"
                  value={draft.expense_date}
                  max={todayISO()}
                  onChange={(e) => set("expense_date", e.target.value)}
                  className="field num"
                />
              </label>
            </div>

            {/* Categories as chips, not a select: one tap instead of three. */}
            <div className="mb-4">
              <span className="label mb-1.5 block">Category</span>
              {grouped.map(([group, items]) => (
                <div key={group} className="mb-2 last:mb-0">
                  <p
                    className="mb-1 text-[0.625rem] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--ink-faint)" }}
                  >
                    {group}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((c) => {
                      const on = draft.category === c.value;
                      return (
                        <button
                          key={c.value}
                          type="button"
                          disabled={!c.allowed}
                          aria-pressed={on}
                          onClick={() => set("category", c.value)}
                          title={c.allowed ? c.label : "Owners only"}
                          className="px-2.5 py-1.5 text-xs font-semibold transition-colors"
                          style={{
                            background: on ? "var(--ink)" : "var(--paper-raised)",
                            color: on
                              ? "var(--paper-raised)"
                              : c.allowed
                                ? "var(--ink-soft)"
                                : "var(--ink-faint)",
                            border: `1px solid ${on ? "var(--ink)" : "var(--rule-strong)"}`,
                            borderRadius: "2px",
                            cursor: c.allowed ? "pointer" : "not-allowed",
                            opacity: c.allowed ? 1 : 0.4,
                          }}
                        >
                          {c.label}
                          {c.owner_only && (
                            <span aria-hidden className="ml-1 opacity-60">
                              ★
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="label mb-1.5 block">Amount (₹)</span>
                <input
                  id="expense-amount"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  step={1}
                  value={draft.amount}
                  onChange={(e) => set("amount", e.target.value)}
                  className="field num"
                  style={{ fontSize: "1.125rem", fontWeight: 600 }}
                  placeholder="0"
                  required
                />
              </label>
              <label className="block">
                <span className="label mb-1.5 block">Paid to</span>
                <input
                  type="text"
                  value={draft.payee}
                  onChange={(e) => set("payee", e.target.value)}
                  className="field"
                  placeholder="Shop, staff member, vendor"
                  maxLength={120}
                  required
                />
              </label>
            </div>

            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="label mb-1.5 block">Paid by</span>
                <select
                  value={draft.payment_mode}
                  onChange={(e) => set("payment_mode", e.target.value)}
                  className="field"
                >
                  {options.payment_modes.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label mb-1.5 block">Money came from</span>
                <select
                  value={draft.paid_from}
                  onChange={(e) => set("paid_from", e.target.value)}
                  className="field"
                >
                  {options.paid_from.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="mb-4 block">
              <span className="label mb-1.5 block">
                What for{" "}
                <span style={{ textTransform: "none", fontWeight: 400 }}>
                  (optional)
                </span>
              </span>
              <input
                type="text"
                value={draft.description}
                onChange={(e) => set("description", e.target.value)}
                className="field"
                placeholder="Weekly provisions, tap repair in 203…"
                maxLength={200}
              />
            </label>

            {error && (
              <p
                role="alert"
                className="mb-3 px-3 py-2.5 text-sm"
                style={{
                  background: "var(--clay-wash)",
                  border: "1px solid color-mix(in oklab, var(--clay) 30%, transparent)",
                  borderRadius: "3px",
                  color: "var(--clay)",
                }}
              >
                {error}
              </p>
            )}

            <div className="flex items-center gap-3">
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "Saving…" : "Record expense"}
              </button>
              {draft.template_id && (
                <span className="text-xs" style={{ color: "var(--ink-faint)" }}>
                  Recurring — can only be recorded once for {data.period_label}
                </span>
              )}
              {allowedCategory?.owner_only && (
                <span className="text-xs" style={{ color: "var(--ink-faint)" }}>
                  ★ owner-only category
                </span>
              )}
            </div>
          </form>
        )}
      </section>

      {/* The ledger lives here rather than in the page so that "Repeat" can
          reach straight into the form's state -- passing a callback through a
          server component would mean a context bridge for no benefit. */}
      <ExpenseLedger data={data} onRepeat={repeat} onVoided={() => router.refresh()} />
    </>
  );
}
