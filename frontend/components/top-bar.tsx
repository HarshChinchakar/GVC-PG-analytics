import Link from "next/link";
import { LogoutButton } from "./logout-button";

/**
 * Application chrome.
 *
 * The currently selected building is stated in the bar itself, not buried in a
 * dropdown — Project.md is explicit that it must always be obvious which PG you
 * are looking at.
 */
export function TopBar({
  userName,
  role,
  locationName,
  locationCode,
}: {
  userName: string;
  role: string;
  locationName?: string;
  locationCode?: string;
}) {
  return (
    <header
      className="rule-b sticky top-0 z-20"
      style={{ background: "var(--paper-raised)" }}
    >
      <div className="mx-auto flex max-w-[84rem] items-center gap-3 px-4 py-3 sm:px-6">
        <Link href="/sites" className="flex shrink-0 items-center gap-2.5">
          <span
            className="num flex h-7 w-7 items-center justify-center text-[0.6875rem] font-semibold"
            style={{
              background: "var(--ink)",
              color: "var(--paper-raised)",
              borderRadius: "3px",
            }}
            aria-hidden
          >
            GV
          </span>
          <span className="hidden text-sm font-semibold tracking-tight sm:inline">
            GVC Executive
          </span>
        </Link>

        {locationName && (
          <>
            <span aria-hidden style={{ color: "var(--rule-strong)" }}>
              /
            </span>
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-sm font-semibold">{locationName}</span>
              <span
                className="num hidden shrink-0 px-1.5 py-0.5 text-[0.625rem] font-semibold sm:inline"
                style={{
                  background: "var(--clay-wash)",
                  color: "var(--clay)",
                  borderRadius: "2px",
                }}
              >
                {locationCode}
              </span>
            </div>
            <Link
              href="/sites"
              className="ml-1 hidden shrink-0 text-xs font-semibold underline decoration-dotted underline-offset-4 sm:inline"
              style={{ color: "var(--ink-faint)" }}
            >
              Switch
            </Link>
          </>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-xs font-semibold leading-tight">{userName}</p>
            <p className="label" style={{ fontSize: "0.625rem" }}>
              {role === "super_admin" ? "Owner" : "Manager"}
            </p>
          </div>
          <LogoutButton />
        </div>
      </div>
    </header>
  );
}
