import { connection } from "next/server";
import Link from "next/link";
import { Card } from "./card-view";
import { listApplications } from "@/lib/db";

export default async function Page() {
  await connection(); // the page reads the db on every request, never at build time
  const apps = listApplications();
  const replied = apps.filter((a) => a.status === "replied").length;
  const rejected = apps.filter((a) => a.status === "rejected").length;

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">All Applications</h1>
          <p className="mt-1 text-sm opacity-70">
            {apps.length} total · {replied} replied · {rejected} rejected
          </p>
        </div>
        <Link href="/table" className="text-sm underline">
          Table view
        </Link>
      </header>

      {apps.length === 0 ? (
        <div className="rounded-xl border border-dashed border-black/20 p-10 text-center dark:border-white/20">
          <p className="font-medium">No applications yet.</p>
          <p className="mt-1 text-sm opacity-70">
            Run <code className="font-mono">uv run python cli.py --send</code> and the first one shows up here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {apps.map((app) => (
            <Card key={app.id} app={app} />
          ))}
        </div>
      )}
    </main>
  );
}
