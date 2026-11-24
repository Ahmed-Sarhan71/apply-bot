import Link from "next/link";
import { connection } from "next/server";
import { listApplications } from "@/lib/db";

const FALLBACK_COLUMNS = [
  "id",
  "applied_at",
  "to_email",
  "company",
  "role_title",
  "subject",
  "post_text",
  "post_hash",
  "status",
  "note",
  "updated_at",
];

export default async function TablePage() {
  await connection();
  const apps = listApplications();
  const rows = apps as unknown as Record<string, string | number | null>[];
  const columns = rows.length ? Object.keys(rows[0]) : FALLBACK_COLUMNS;

  return (
    <main className="mx-auto w-full max-w-[95rem] px-6 py-10">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">All columns</h1>
          <p className="mt-1 text-sm opacity-70">{rows.length} row(s)</p>
        </div>
        <Link href="/" className="text-sm underline">
          Back to cards
        </Link>
      </header>

      {rows.length === 0 ? (
        <p className="text-sm opacity-70">No applications yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/15">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-black/5 dark:bg-white/10">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="whitespace-nowrap px-3 py-2 font-mono text-xs font-semibold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-black/10 align-top dark:border-white/10">
                  {columns.map((c) => (
                    <td key={c} className="max-w-[22rem] truncate px-3 py-2 font-mono text-xs">
                      {row[c] === null || row[c] === "" ? "—" : String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
