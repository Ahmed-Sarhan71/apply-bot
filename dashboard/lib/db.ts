import Database from "better-sqlite3";
import { existsSync } from "node:fs";
import path from "node:path";

// Same file the Python bot writes: data/applications.db at the repo root.
export const DB_PATH =
  process.env.APPLYBOT_DB ?? path.join(process.cwd(), "..", "data", "applications.db");

export const STATUSES = ["sent", "replied", "rejected", "no_reply"] as const;
export type Status = (typeof STATUSES)[number];

export type Application = {
  id: number;
  applied_at: string;
  to_email: string;
  company: string | null;
  role_title: string | null;
  subject: string;
  post_text: string;
  status: Status;
  note: string | null;
};

export function getDb() {
  return new Database(DB_PATH, { fileMustExist: true });
}

export function listApplications(): Application[] {
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return [];
  const db = getDb();
  try {
    return db
      .prepare("SELECT * FROM applications ORDER BY applied_at DESC, id DESC")
      .all() as Application[];
  } finally {
    db.close();
  }
}
