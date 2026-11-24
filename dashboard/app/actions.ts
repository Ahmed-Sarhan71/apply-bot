"use server";

import { revalidatePath } from "next/cache";
import { getDb, STATUSES, type Status } from "@/lib/db";

export async function updateApplication(formData: FormData) {
  const id = Number(formData.get("id"));
  const status = String(formData.get("status") ?? "") as Status;
  const note = String(formData.get("note") ?? "").trim().slice(0, 2000);
  if (!Number.isInteger(id) || id <= 0 || !STATUSES.includes(status)) return;

  const db = getDb();
  try {
    db.prepare(
      "UPDATE applications SET status = ?, note = ?, updated_at = ? WHERE id = ?",
    ).run(status, note || null, new Date().toISOString().slice(0, 19), id);
  } finally {
    db.close();
  }
  revalidatePath("/");
}
