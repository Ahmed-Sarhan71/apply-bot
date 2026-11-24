"use server";

import { revalidatePath } from "next/cache";
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
