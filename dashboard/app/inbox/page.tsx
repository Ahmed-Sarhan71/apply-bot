import Link from "next/link";
import { connection } from "next/server";
import { listInbox } from "@/lib/db";

const COLS = ["Posted", "Channel", "Email", "Post", "Status"];
const ROW = "grid grid-cols-[6.5rem_10rem_1.2fr_2.4fr_4.5rem] items-start gap-4 px-4";
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/;
const SELECT = "rounded-md border border-black/15 bg-transparent px-2 py-1.5 text-sm dark:border-white/20";

const dmY = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

export default async function InboxPage({ searchParams }: PageProps<"/inbox">) {
  await connection();
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const channel = one(sp.channel);
  const status = one(sp.status);
  const q = one(sp.q).trim().toLowerCase();

  const all = listInbox();
  const rows = all.filter(
    (p) =>
      (!channel || p.channel === channel) &&
      (!status || status === "all" || p.status === status) &&
      (!q || p.text.toLowerCase().includes(q)),
  );
  const channels = [...new Set(all.map((p) => p.channel))].sort();
  const fresh = all.filter((p) => p.status === "new").length;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Inbox</h1>
          <p className="mt-1 text-sm opacity-70">
            {all.length} posts · {fresh} new · {all.length - fresh} done
          </p>
        </div>
        <div className="flex items-baseline gap-4 text-sm">
          <Link href="/" className="underline">
            All applications
          </Link>
          <Link href="/table" className="underline">
            Table view
          </Link>
        </div>
      </header>

      <form className="mb-4 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="opacity-70">Channel</span>
          <select name="channel" defaultValue={channel} className={SELECT}>
            <option value="" className="text-black">
              All channels
            </option>
            {channels.map((c) => (
              <option key={c} value={c} className="text-black">
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="opacity-70">Status</span>
          <select name="status" defaultValue={status || "all"} className={SELECT}>
            {["all", "new", "done"].map((s) => (
              <option key={s} value={s} className="text-black">
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="opacity-70">Search post text</span>
          <input type="search" name="q" defaultValue={q} className={SELECT} />
        </label>
        <button type="submit" className="rounded-md bg-black px-3 py-1.5 font-medium text-white dark:bg-white dark:text-black">
          Filter
        </button>
        {channel || (status && status !== "all") || q ? (
          <Link href="/inbox" className="underline">
            Reset
          </Link>
        ) : null}
      </form>

      {all.length === 0 ? (
        <p className="text-sm opacity-70">
          No posts in the inbox yet. Run <code className="font-mono">uv run python telegram_reader.py --once</code>.
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm opacity-70">No posts match the filters.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/15">
          <div className="min-w-[52rem]">
            <div className={`${ROW} border-b border-black/10 bg-black/5 py-3 text-sm font-medium dark:border-white/10 dark:bg-white/10`}>
              {COLS.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </div>
            {rows.map((p) => {
              const email = p.text.match(EMAIL)?.[0];
              return (
                <div
                  key={p.id}
                  className={`${ROW} border-b border-black/10 py-2.5 text-[15px] last:border-0 dark:border-white/10`}
                >
                  <span className="tabular-nums">{dmY(p.posted_at ?? p.saved_at)}</span>
                  {p.link ? (
                    <a href={p.link} target="_blank" rel="noreferrer" className="truncate underline underline-offset-2">
                      {p.channel}
                    </a>
                  ) : (
                    <span className="truncate">{p.channel}</span>
                  )}
                  <span className="truncate">{email ?? "—"}</span>
                  <details>
                    <summary className="cursor-pointer">
                      <span className="line-clamp-1">{p.text}</span>
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-sm opacity-80">{p.text}</pre>
                  </details>
                  <span className="truncate">{p.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </main>
  );
}
