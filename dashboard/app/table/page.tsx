import Link from "next/link";
import { connection } from "next/server";
import { updateApplication } from "../actions";
import { AutoSubmitSelect } from "../auto-submit-select";
import { listApplications, STATUSES } from "@/lib/db";

const COLS = ["ID", "Applied", "Email", "Company", "Role", "Status"];
const ROW = "grid grid-cols-[3.5rem_7rem_1.1fr_0.9fr_1.4fr_11rem] items-center gap-4 px-4";

const dmY = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

export default async function TablePage() {
  await connection();
  const rows = listApplications();
  const replied = rows.filter((r) => r.status === "replied").length;
  const rejected = rows.filter((r) => r.status === "rejected").length;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">All Applications</h1>
          <p className="mt-1 text-sm opacity-70">
            {rows.length} total · {replied} replied · {rejected} rejected
          </p>
        </div>
        <Link href="/" className="text-sm underline">
          Cards
        </Link>
      </header>

      {rows.length === 0 ? (
        <p className="text-sm opacity-70">No applications yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/15">
          <div className="min-w-[52rem]">
            <div className={`${ROW} border-b border-black/10 bg-black/5 py-3 text-sm font-medium dark:border-white/10 dark:bg-white/10`}>
              {COLS.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </div>
            {rows.map((r) => (
              <div
                key={r.id}
                className={`${ROW} border-b border-black/10 py-2.5 text-[15px] last:border-0 dark:border-white/10`}
              >
                <Link href={`/card/${r.id}`} className="font-medium underline underline-offset-2" title="Open card">
                  {r.id}
                </Link>
                <span className="tabular-nums">{dmY(r.applied_at)}</span>
                <span className="truncate">{r.to_email}</span>
                <span className="truncate">{r.company ?? "—"}</span>
                <span className="truncate">{r.role_title ?? "—"}</span>
                <form action={updateApplication}>
                  <input type="hidden" name="id" value={r.id} />
                  <AutoSubmitSelect value={r.status} options={STATUSES} />
                </form>
              </div>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
