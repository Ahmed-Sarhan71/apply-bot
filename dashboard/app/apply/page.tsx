"use client";

import { useActionState } from "react";
import Link from "next/link";
import { submitPost } from "../actions";

export default function ApplyPage() {
  const [out, run, pending] = useActionState(submitPost, "");

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-10">
      <header className="mb-6 flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold">Paste a job post</h1>
        <Link href="/" className="text-sm underline">
          All applications
        </Link>
      </header>

      <form action={run} className="flex flex-col gap-3">
        <textarea
          name="post"
          rows={14}
          required
          placeholder="Paste the post here. Separate several posts with a line ---"
          className="w-full resize-y rounded-xl border border-black/15 bg-transparent px-4 py-3 font-mono text-sm outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/50"
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="send" className="size-4" />
          Actually send it through Gmail (otherwise it is a dry run)
        </label>
        <button
          type="submit"
          disabled={pending}
          className="self-start rounded-lg bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {pending ? "Working… about 20s per post" : "Run"}
        </button>
      </form>

      {out ? (
        <pre className="mt-6 overflow-x-auto rounded-xl border border-black/10 p-4 font-mono text-xs leading-relaxed dark:border-white/15">
          {out}
        </pre>
      ) : null}
    </main>
  );
}
