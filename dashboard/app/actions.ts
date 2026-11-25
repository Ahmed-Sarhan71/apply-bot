"use server";

import { revalidatePath } from "next/cache";
import path from "node:path";
import { getDb, STATUSES, type Status } from "@/lib/db";

export async function updateApplication(formData: FormData) {
  const id = Number(formData.get("id"));
  const status = String(formData.get("status") ?? "") as Status;
  if (!Number.isInteger(id) || id <= 0 || !STATUSES.includes(status)) return;

  // The table form sends no note; don't wipe the note the cards form wrote.
  const hasNote = formData.has("note");
  const note = String(formData.get("note") ?? "").trim().slice(0, 2000);
  const now = new Date().toISOString().slice(0, 19);

  const db = getDb();
  try {
    if (hasNote) {
      db.prepare("UPDATE applications SET status = ?, note = ?, updated_at = ? WHERE id = ?").run(
        status,
        note || null,
        now,
        id,
      );
    } else {
      db.prepare("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?").run(status, now, id);
    }
  } finally {
    db.close();
  }
  revalidatePath("/");
  revalidatePath("/table");
  revalidatePath(`/card/${id}`);
}

// The whole pipeline lives in cli.py; the web form just feeds it stdin instead of the terminal.
export async function submitPost(_prev: string, formData: FormData): Promise<string> {
  const post = String(formData.get("post") ?? "").trim();
  if (!post) return "nothing pasted";
  const send = formData.get("send") === "on";

  const { spawn } = await import("node:child_process");
  const child = spawn("uv", ["run", "python", "cli.py", "-q", ...(send ? ["--send"] : [])], {
    cwd: path.join(process.cwd(), ".."),
    // plain text for a browser: no colour codes, wrapped at a readable width
    env: { ...process.env, NO_COLOR: "1", TERM: "dumb", COLUMNS: "110" },
  });
  const timer = setTimeout(() => child.kill(), 300_000); // ponytail: one hard 5-min cap, stream progress if it ever bites
  let out = "";
  child.on("error", (e) => (out += `spawn failed: ${e.message}\n`));
  child.stdout.on("data", (d) => (out += d));
  child.stderr.on("data", (d) => (out += d));
  child.stdin.end(post + "\nEND\n");
  const code = await new Promise<number | null>((done) => child.on("close", done));
  clearTimeout(timer);

  revalidatePath("/");
  revalidatePath("/table");
  const text = out.replace(/\x1b\[[0-9;]*m/g, "").trim(); // belt and braces: rich can still emit colour
  return (text || `cli exited with ${code}`).slice(-8000);
}
