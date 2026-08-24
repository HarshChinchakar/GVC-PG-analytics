"use client";

import { useMemo, useState } from "react";
import type { Board, Seat, SeatState } from "@/lib/api";
import { fullDate, rupees, shortDate, telHref } from "@/lib/format";

/**
 * The seat map.
 *
 * A cinema booking chart applied to a PG: a room *is* a price tier, so beds
 * sit in tier rows the way stalls, circle and balcony do. Colour carries the
 * state, and a glyph carries it again — colour alone fails for colour-blind
 * staff and in daylight on a tablet by the front door.
 *
 * Read-only by design. This is a board you consult, not a form you fill; the
 * write actions land here later, in the same drawer.
 */

const STATE_META: Record<
  SeatState,
  { label: string; glyph: string; fill: string; ink: string; border: string }
> = {
  occupied_paid: {
    label: "Paid",
    glyph: "✓",
    fill: "var(--moss)",
    ink: "var(--paper-raised)",
    border: "var(--moss)",
  },
  occupied_unpaid: {
    label: "Rent due",
    glyph: "!",
    fill: "var(--amber)",
    ink: "var(--paper-raised)",
    border: "var(--amber)",
  },
  notice: {
    label: "On notice",
    glyph: "→",
    fill: "var(--slate)",
    ink: "var(--paper-raised)",
    border: "var(--slate)",
  },
  booked: {
    label: "Booked",
    glyph: "◆",
    fill: "var(--indigo)",
    ink: "var(--paper-raised)",
    border: "var(--indigo)",
  },
  // Washed rather than solid: an empty seat should still read as empty, but a
  // bare outline was too quiet to pick out at a glance on a tablet.
  vacant: {
    label: "Vacant",
    glyph: "",
    fill: "var(--clay-wash)",
    ink: "var(--clay)",
    border: "var(--clay)",
  },
  blocked: {
    label: "Out of service",
    glyph: "×",
    fill: "var(--paper-sunk)",
    ink: "var(--ink-faint)",
    border: "var(--rule-strong)",
  },
};

const FILTERS: { key: string; label: string; match: (s: Seat) => boolean }[] = [
  { key: "vacant", label: "Vacant", match: (s) => s.seat_state === "vacant" },
  { key: "unpaid", label: "Rent due", match: (s) => s.seat_state === "occupied_unpaid" },
  { key: "notice", label: "On notice", match: (s) => s.seat_state === "notice" },
  { key: "booked", label: "Booked", match: (s) => s.seat_state === "booked" },
  { key: "attached", label: "Attached bath", match: (s) => s.tier === "attached_bath" },
  { key: "hall", label: "Hall beds", match: (s) => s.tier === "hall" },
];

function SeatButton({
  seat,
  dimmed,
  selected,
  onSelect,
}: {
  seat: Seat;
  dimmed: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const meta = STATE_META[seat.seat_state];
  const who = seat.resident?.name ?? seat.reservation?.person_name;

  return (
    <button
      type="button"
      onClick={onSelect}
      title={`${seat.label} · ${meta.label}${who ? ` · ${who}` : ""}`}
      aria-label={`Bed ${seat.label}, ${meta.label}${who ? `, ${who}` : ""}`}
      aria-pressed={selected}
      className="num relative flex shrink-0 items-center justify-center font-semibold transition-transform"
      style={{
        // 44px: a comfortable touch target on the tablet this is used on.
        width: "2.75rem",
        height: "2.75rem",
        borderRadius: "3px",
        background: meta.fill,
        color: meta.ink,
        border: `1.5px solid ${meta.border}`,
        fontSize: "0.8125rem",
        opacity: dimmed ? 0.22 : 1,
        outline: selected ? "2px solid var(--ink)" : "none",
        outlineOffset: "2px",
        cursor: "pointer",
        // A hatch makes "out of service" readable without relying on grey.
        backgroundImage:
          seat.seat_state === "blocked"
            ? "repeating-linear-gradient(45deg, transparent, transparent 3px, var(--rule-strong) 3px, var(--rule-strong) 4px)"
            : undefined,
      }}
    >
      {seat.number}
      {meta.glyph && (
        <span
          aria-hidden
          className="absolute"
          style={{ top: "1px", right: "3px", fontSize: "0.5625rem", opacity: 0.9 }}
        >
          {meta.glyph}
        </span>
      )}
    </button>
  );
}

function DetailPanel({ seat, onClose }: { seat: Seat; onClose: () => void }) {
  const meta = STATE_META[seat.seat_state];
  const r = seat.resident;
  const b = seat.reservation;

  return (
    <aside
      className="sheet-raised"
      style={{ position: "sticky", top: "5rem" }}
      aria-label={`Details for bed ${seat.label}`}
    >
      <div className="rule-b flex items-start justify-between gap-3 px-4 py-3">
        <div>
          <p className="num text-lg font-semibold leading-none">{seat.label}</p>
          <span
            className="mt-2 inline-block px-2 py-0.5 text-[0.6875rem] font-semibold"
            style={{
              background: seat.seat_state === "vacant" ? "transparent" : meta.fill,
              color: seat.seat_state === "vacant" ? "var(--clay)" : meta.ink,
              border: `1px solid ${meta.border}`,
              borderRadius: "2px",
            }}
          >
            {meta.label}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="btn btn-quiet"
          style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
        >
          Close
        </button>
      </div>

      <dl className="px-4 py-3 text-sm">
        {r ? (
          <>
            <div className="mb-3">
              <dt className="label">Resident</dt>
              <dd className="mt-0.5 font-semibold">{r.name}</dd>
              <dd className="mt-0.5">
                <a
                  href={telHref(r.phone)}
                  className="num text-xs underline decoration-dotted underline-offset-2"
                  style={{ color: "var(--clay)" }}
                >
                  {r.phone}
                </a>
              </dd>
            </div>
            <div className="rule-t grid grid-cols-2 gap-3 pt-3">
              <div>
                <dt className="label">Rent</dt>
                <dd className="num mt-0.5 font-semibold">
                  {rupees(r.monthly_rent ?? seat.rent)}
                </dd>
              </div>
              <div>
                <dt className="label">This month</dt>
                <dd
                  className="num mt-0.5 font-semibold"
                  style={{
                    color:
                      r.rent_status === "pending" ? "var(--clay)" : "var(--moss)",
                  }}
                >
                  {r.rent_status === "pending"
                    ? "Pending"
                    : r.paid_on
                      ? `Paid ${shortDate(r.paid_on)}`
                      : "Settled"}
                </dd>
              </div>
              <div>
                <dt className="label">Joined</dt>
                <dd className="num mt-0.5">{fullDate(r.joined_on)}</dd>
              </div>
              {r.free_from && (
                <div>
                  <dt className="label">Free from</dt>
                  <dd className="num mt-0.5 font-semibold" style={{ color: "var(--slate)" }}>
                    {fullDate(r.free_from)}
                  </dd>
                </div>
              )}
            </div>
            <div className="rule-t mt-3 pt-3">
              <dt className="label">Vehicles</dt>
              {r.vehicles.length === 0 ? (
                <dd className="mt-1 text-xs" style={{ color: "var(--ink-faint)" }}>
                  None registered
                </dd>
              ) : (
                r.vehicles.map((v) => (
                  <dd key={v.number} className="mt-1">
                    <span className="num text-xs font-semibold">{v.number}</span>
                    <span className="ml-2 text-xs" style={{ color: "var(--ink-faint)" }}>
                      {[v.make_model, v.colour].filter(Boolean).join(" · ")}
                    </span>
                  </dd>
                ))
              )}
            </div>
          </>
        ) : b ? (
          <>
            <div className="mb-3">
              <dt className="label">Reserved for</dt>
              <dd className="mt-0.5 font-semibold">{b.person_name}</dd>
              <dd className="mt-0.5">
                <a
                  href={telHref(b.phone)}
                  className="num text-xs underline decoration-dotted underline-offset-2"
                  style={{ color: "var(--clay)" }}
                >
                  {b.phone}
                </a>
              </dd>
            </div>
            <div className="rule-t grid grid-cols-2 gap-3 pt-3">
              <div>
                <dt className="label">Moving in</dt>
                <dd className="num mt-0.5 font-semibold">
                  {fullDate(b.expected_move_in)}
                </dd>
                <dd className="num text-xs" style={{ color: "var(--ink-faint)" }}>
                  in {b.days_away} days
                </dd>
              </div>
              <div>
                <dt className="label">Token paid</dt>
                <dd className="num mt-0.5 font-semibold">{rupees(b.token_amount)}</dd>
              </div>
              <div>
                <dt className="label">Agreed rent</dt>
                <dd className="num mt-0.5">{rupees(b.agreed_rent ?? seat.rent)}</dd>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <dt className="label">Rent</dt>
                <dd className="num mt-0.5 text-lg font-semibold">{rupees(seat.rent)}</dd>
              </div>
              <div>
                <dt className="label">Tier</dt>
                <dd className="mt-0.5 text-sm">
                  {seat.tier === "attached_bath"
                    ? "Attached bath"
                    : seat.tier === "hall"
                      ? "Hall"
                      : "Shared bath"}
                </dd>
              </div>
            </div>
            {seat.notes && (
              <div className="rule-t mt-3 pt-3">
                <dt className="label">Note</dt>
                <dd className="mt-0.5 text-xs">{seat.notes}</dd>
              </div>
            )}
            <p className="rule-t mt-3 pt-3 text-xs" style={{ color: "var(--ink-faint)" }}>
              {seat.seat_state === "blocked"
                ? "Not available to let."
                : `Empty — ${rupees(seat.rent)} a month unearned.`}
            </p>
          </>
        )}
      </dl>
    </aside>
  );
}

export function OccupancyBoard({ board }: { board: Board }) {
  const [floorNumber, setFloorNumber] = useState<number | "all">(
    board.floors[0]?.number ?? "all",
  );
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [selected, setSelected] = useState<Seat | null>(null);

  const visibleFloors = useMemo(
    () =>
      floorNumber === "all"
        ? board.floors
        : board.floors.filter((f) => f.number === floorNumber),
    [board.floors, floorNumber],
  );

  const matches = useMemo(() => {
    if (activeFilters.length === 0) return null;
    const active = FILTERS.filter((f) => activeFilters.includes(f.key));
    // Any-of: ticking "Vacant" and "Attached bath" highlights both, which is
    // how staff actually scan ("show me anything worth acting on").
    return (seat: Seat) => active.some((f) => f.match(seat));
  }, [activeFilters]);

  const matchCount = useMemo(() => {
    if (!matches) return 0;
    return board.floors
      .flatMap((f) => f.flats)
      .flatMap((f) => f.tiers)
      .flatMap((t) => t.beds)
      .filter(matches).length;
  }, [board.floors, matches]);

  return (
    <>
      {/* --- floor switcher + filters --------------------------------- */}
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div
          className="flex overflow-hidden"
          style={{ border: "1px solid var(--rule-strong)", borderRadius: "3px" }}
          role="tablist"
          aria-label="Floor"
        >
          {board.floors.map((f) => (
            <button
              key={f.number}
              type="button"
              role="tab"
              aria-selected={floorNumber === f.number}
              onClick={() => setFloorNumber(f.number)}
              className="num px-3.5 py-2 text-sm font-semibold transition-colors"
              style={{
                background:
                  floorNumber === f.number ? "var(--ink)" : "var(--paper-raised)",
                color:
                  floorNumber === f.number ? "var(--paper-raised)" : "var(--ink-soft)",
                borderRight: "1px solid var(--rule)",
              }}
            >
              F{f.number}
            </button>
          ))}
          <button
            type="button"
            role="tab"
            aria-selected={floorNumber === "all"}
            onClick={() => setFloorNumber("all")}
            className="px-3.5 py-2 text-sm font-semibold transition-colors"
            style={{
              background: floorNumber === "all" ? "var(--ink)" : "var(--paper-raised)",
              color: floorNumber === "all" ? "var(--paper-raised)" : "var(--ink-soft)",
            }}
          >
            All
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {FILTERS.map((f) => {
            const on = activeFilters.includes(f.key);
            return (
              <button
                key={f.key}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  setActiveFilters((prev) =>
                    prev.includes(f.key)
                      ? prev.filter((k) => k !== f.key)
                      : [...prev, f.key],
                  )
                }
                className="px-2.5 py-1.5 text-xs font-semibold transition-colors"
                style={{
                  background: on ? "var(--clay)" : "var(--paper-raised)",
                  color: on ? "var(--paper-raised)" : "var(--ink-soft)",
                  border: `1px solid ${on ? "var(--clay)" : "var(--rule-strong)"}`,
                  borderRadius: "2px",
                }}
              >
                {f.label}
              </button>
            );
          })}
          {activeFilters.length > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilters([])}
              className="num px-2 py-1.5 text-xs font-semibold underline decoration-dotted underline-offset-2"
              style={{ color: "var(--ink-faint)" }}
            >
              {matchCount} shown · clear
            </button>
          )}
        </div>
      </div>

      {/* --- legend ---------------------------------------------------- */}
      <div
        className="sheet-sunk mb-5 flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5"
      >
        {(Object.keys(STATE_META) as SeatState[]).map((key) => {
          const meta = STATE_META[key];
          const count = board.seat_totals[key] ?? 0;
          return (
            <span key={key} className="flex items-center gap-1.5 text-xs">
              <span
                aria-hidden
                style={{
                  width: "0.875rem",
                  height: "0.875rem",
                  borderRadius: "2px",
                  background: meta.fill,
                  border: `1.5px solid ${meta.border}`,
                  display: "inline-block",
                }}
              />
              <span style={{ color: "var(--ink-soft)" }}>{meta.label}</span>
              <span className="num font-semibold">{count}</span>
            </span>
          );
        })}
      </div>

      {/* --- board + detail -------------------------------------------- */}
      <div className="grid gap-5 xl:grid-cols-[1fr_20rem]">
        <div className="grid items-start gap-4">
          {visibleFloors.map((floor) => (
            <section key={floor.number}>
              {floorNumber === "all" && (
                <h2 className="label mb-2">{floor.name}</h2>
              )}
              <div className="grid items-start gap-4 lg:grid-cols-2">
                {floor.flats.map((flat) => (
                  <div key={flat.id} className="sheet overflow-hidden">
                    <div className="rule-b flex items-baseline justify-between gap-2 px-4 py-2.5">
                      <div className="flex items-baseline gap-2">
                        <span className="num text-base font-semibold">
                          {flat.flat_number}
                        </span>
                        <span
                          className="text-[0.6875rem] font-semibold uppercase tracking-wide"
                          style={{ color: "var(--ink-faint)" }}
                        >
                          {flat.flat_type.replace("bhk", " BHK")}
                        </span>
                        <span
                          className="px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase"
                          style={{
                            background:
                              flat.gender_policy === "female"
                                ? "var(--clay-wash)"
                                : "var(--slate-wash)",
                            color:
                              flat.gender_policy === "female"
                                ? "var(--clay)"
                                : "var(--slate)",
                            borderRadius: "2px",
                          }}
                        >
                          {flat.gender_policy}
                        </span>
                      </div>
                      <span
                        className="num text-xs font-semibold"
                        style={{
                          color:
                            flat.vacant > 0 ? "var(--clay)" : "var(--ink-faint)",
                        }}
                      >
                        {flat.filled}/{flat.rentable}
                      </span>
                    </div>

                    <div className="px-4 py-3">
                      {flat.tiers.map((tier) => (
                        <div
                          key={tier.room_id}
                          className="mb-3 flex items-center gap-3 last:mb-0"
                        >
                          <div
                            className="shrink-0"
                            style={{ width: "6.5rem" }}
                          >
                            <p
                              className="text-[0.625rem] font-semibold uppercase tracking-wide"
                              style={{ color: "var(--ink-faint)" }}
                            >
                              {tier.tier_label}
                            </p>
                            <p className="num text-xs font-semibold">
                              {rupees(tier.rent)}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {tier.beds.map((seat) => (
                              <SeatButton
                                key={seat.id}
                                seat={seat}
                                dimmed={matches ? !matches(seat) : false}
                                selected={selected?.id === seat.id}
                                onSelect={() =>
                                  setSelected((cur) =>
                                    cur?.id === seat.id ? null : seat,
                                  )
                                }
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>

        {/* Detail rail on tablet and up; the same panel drops inline below
            the board on a phone, so a tap never scrolls you somewhere else. */}
        <div className="xl:block">
          {selected ? (
            <DetailPanel seat={selected} onClose={() => setSelected(null)} />
          ) : (
            <div className="sheet-sunk hidden px-4 py-6 text-center xl:block">
              <p className="text-xs" style={{ color: "var(--ink-faint)" }}>
                Tap any bed to see who is in it.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
