import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-6">
      <div className="max-w-sm text-center">
        <p className="label mb-3">Not found</p>
        <h1
          className="text-2xl tracking-tight"
          style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
        >
          That site isn&rsquo;t available
        </h1>
        <p className="mt-3 text-sm" style={{ color: "var(--ink-soft)" }}>
          It may have been removed, or your account may not have access to it.
        </p>
        <Link href="/sites" className="btn btn-primary mt-6">
          Back to sites
        </Link>
      </div>
    </main>
  );
}
