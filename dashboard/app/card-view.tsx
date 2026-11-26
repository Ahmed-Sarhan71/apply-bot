import { updateApplication } from "./actions";
import { STATUSES, type Application, type Status } from "@/lib/db";

const BADGE: Record<Status, string> = {
  sent: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  replied: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function Card({ app }: { app: Application }) {
  return (
    <article className="rounded-xl border border-black/10 p-5 dark:border-white/15">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{app.role_title ?? "Unknown role"}</h2>
          <p className="text-sm opacity-70">
            {app.company ?? "-"} · {app.to_email}
          </p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE[app.status]}`}>
          {app.status.replace("_", " ")}
        </span>
      </div>

      <p className="mt-2 text-sm opacity-70">
        Applied {formatDate(app.applied_at)} · {app.subject}
      </p>

      <details className="mt-3">
        <summary className="cursor-pointer text-sm underline">Show job post</summary>
        <pre className="mt-2 whitespace-pre-wrap font-sans text-sm opacity-80">{app.post_text}</pre>
      </details>

      {app.body ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm underline">Show email sent</summary>
          <pre className="mt-2 whitespace-pre-wrap font-sans text-sm opacity-80">{app.body}</pre>
        </details>
      ) : null}

      <form action={updateApplication} className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-start">
        <input type="hidden" name="id" value={app.id} />
        <select
          name="status"
          defaultValue={app.status}
          className="rounded-md border border-black/15 bg-transparent px-2 py-1.5 text-sm dark:border-white/20"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s} className="text-black">
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <textarea
          name="note"
          rows={2}
          defaultValue={app.note ?? ""}
          placeholder="Note (recruiter name, follow-up date...)"
          className="flex-1 rounded-md border border-black/15 bg-transparent px-2 py-1.5 text-sm dark:border-white/20"
        />
        <button
          type="submit"
          className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-black"
        >
          Save
        </button>
      </form>
    </article>
  );
}
