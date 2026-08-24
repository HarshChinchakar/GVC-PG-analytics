import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { getToken } from "@/lib/session";
import { telHref } from "@/lib/format";
import { TopBar } from "@/components/top-bar";
import { VehicleSearchBox } from "@/components/vehicle-search";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ q?: string }>;
};

const TYPE_LABEL: Record<string, string> = {
  two_wheeler: "Two-wheeler",
  four_wheeler: "Car",
  bicycle: "Bicycle",
  other: "Other",
};

/**
 * Vehicle register.
 *
 * Built around one question asked at the gate — whose is this? — so the search
 * box is the page, and the full register sits underneath it.
 */
export default async function VehiclesPage({ params, searchParams }: Props) {
  if (!(await getToken())) redirect("/login");

  const { id } = await params;
  const { q } = await searchParams;

  let user, data;
  try {
    [user, data] = await Promise.all([api.me(), api.vehicles(id, q)]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/logout?expired=1");
      if (error.status === 404) notFound();
    }
    throw error;
  }

  const searching = Boolean(q?.trim());

  return (
    <>
      <TopBar
        userName={user.full_name}
        role={user.role}
        locationName={data.location_name}
        locationCode={data.location_code}
      />

      <main className="mx-auto max-w-[64rem] px-4 py-6 sm:px-6 sm:py-8">
        <Link
          href={`/sites/${data.location_id}/occupancy`}
          className="mb-3 inline-flex items-center gap-1.5 text-xs font-semibold"
          style={{ color: "var(--ink-faint)" }}
        >
          <span aria-hidden>&larr;</span> Back to the board
        </Link>

        <div className="mb-6">
          <p className="label mb-1.5">Vehicle lookup</p>
          <h1
            className="text-3xl tracking-tight sm:text-[2.5rem] sm:leading-none"
            style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
          >
            Whose vehicle is this?
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--ink-soft)" }}>
            Type any part of a number plate — the last four digits are enough.
            You can also search by resident name or phone.
          </p>
        </div>

        <VehicleSearchBox locationId={data.location_id} initial={q ?? ""} />

        <div className="mt-6">
          <p className="label mb-3">
            {searching
              ? `${data.count} ${data.count === 1 ? "match" : "matches"} for “${data.query}”`
              : `All registered vehicles · ${data.count}`}
          </p>

          {data.results.length === 0 ? (
            <div className="sheet px-6 py-12 text-center">
              <p className="text-sm" style={{ color: "var(--ink-soft)" }}>
                No vehicle matches that.
              </p>
              <p className="mt-1 text-xs" style={{ color: "var(--ink-faint)" }}>
                Try fewer characters — searching the last four digits usually
                works best.
              </p>
            </div>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {data.results.map((v) => {
                const gone = v.resident_status === "left";
                return (
                  <li key={v.vehicle_number} className="sheet px-4 py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="num text-base font-semibold tracking-tight">
                        {v.vehicle_number}
                      </span>
                      <span
                        className="px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase"
                        style={{
                          background: gone ? "var(--clay-wash)" : "var(--moss-wash)",
                          color: gone ? "var(--clay)" : "var(--moss)",
                          borderRadius: "2px",
                        }}
                      >
                        {gone ? "Left the PG" : v.resident_status}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs" style={{ color: "var(--ink-faint)" }}>
                      {[TYPE_LABEL[v.vehicle_type] ?? v.vehicle_type, v.make_model, v.colour]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>

                    <div className="rule-t mt-2.5 pt-2.5">
                      <p className="text-sm font-semibold">{v.resident_name}</p>
                      <p className="num mt-0.5 text-xs" style={{ color: "var(--ink-soft)" }}>
                        {v.bed_label
                          ? `${v.bed_label} · ${v.floor_name}`
                          : "No current bed"}
                      </p>
                      <a
                        href={telHref(v.phone)}
                        className="num mt-1 inline-block text-xs font-semibold underline decoration-dotted underline-offset-2"
                        style={{ color: "var(--clay)" }}
                      >
                        Call {v.phone}
                      </a>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>
    </>
  );
}
