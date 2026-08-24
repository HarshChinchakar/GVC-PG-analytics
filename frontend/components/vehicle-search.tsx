"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * The search box.
 *
 * Submits to the server rather than filtering client-side: the register may
 * eventually hold vehicles for residents who have long left, and the lookup
 * must stay fast without shipping the whole list to the browser.
 */
export function VehicleSearchBox({
  locationId,
  initial,
}: {
  locationId: string;
  initial: string;
}) {
  const router = useRouter();
  const [value, setValue] = useState(initial);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const q = value.trim();
    router.push(
      `/sites/${locationId}/vehicles${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    );
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <input
        type="search"
        name="q"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        // Plates are typed in a hurry at a gate; autocorrect only gets in the way.
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        placeholder="MH12 AB 4472, or just 4472"
        aria-label="Search by number plate, name or phone"
        className="field num"
        style={{ fontSize: "1.0625rem", padding: "0.875rem 1rem" }}
      />
      <button type="submit" className="btn btn-primary" style={{ padding: "0 1.5rem" }}>
        Search
      </button>
      {initial && (
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            setValue("");
            router.push(`/sites/${locationId}/vehicles`);
          }}
        >
          Clear
        </button>
      )}
    </form>
  );
}
