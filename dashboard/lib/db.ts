import Database from "better-sqlite3";
import { existsSync } from "node:fs";
import path from "node:path";

// Same file the Python bot writes: data/applications.db at the repo root.
export const DB_PATH =
  process.env.APPLYBOT_DB ?? path.join(process.cwd(), "..", "data", "applications.db");

export const STATUSES = ["sent", "replied", "rejected"] as const;
export type Status = (typeof STATUSES)[number];

export type Application = {
  id: number;
  applied_at: string;
  to_email: string;
  company: string | null;
  role_title: string | null;
  subject: string;
  body: string | null;
  post_text: string;
  /** 0 = sent from an old post: kept for the address guard, hidden from All Applications. */
  listed: number;
  status: Status;
  note: string | null;
};

export function getDb() {
  return new Database(DB_PATH, { fileMustExist: true });
}

/** The dashboard can open the file before the Python side has migrated it. */
function hasListed(db: Database.Database): boolean {
  const cols = db.prepare("PRAGMA table_info(applications)").all() as { name: string }[];
  return cols.some((c) => c.name === "listed");
}

export type Failure = {
  id: number;
  failed_at: string;
  post_hash: string;
  post_text: string;
  company: string | null;
  role_title: string | null;
  to_email: string | null;
  reason: string;
};

export function getApplication(id: number): Application | null {
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return null;
  const db = getDb();
  try {
    return (db.prepare("SELECT * FROM applications WHERE id = ?").get(id) as Application) ?? null;
  } finally {
    db.close();
  }
}

export function listApplications(): Application[] {
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return [];
  const db = getDb();
  try {
    const where = hasListed(db) ? " WHERE listed = 1" : "";
    return db
      .prepare(`SELECT * FROM applications${where} ORDER BY applied_at DESC, id DESC`)
      .all() as Application[];
  } finally {
    db.close();
  }
}

export function listFailures(): Failure[] {
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return [];
  const db = getDb();
  try {
    return db.prepare("SELECT * FROM failures ORDER BY failed_at DESC, id DESC").all() as Failure[];
  } finally {
    db.close();
  }
}

export type InboxPost = {
  id: number;
  post_hash: string;
  source: string;
  channel: string;
  message_id: number | null;
  link: string | null;
  posted_at: string | null;
  saved_at: string;
  text: string;
  status: "new" | "done";
};

export function listInbox(): InboxPost[] {
  if (!existsSync(/*turbopackIgnore: true*/ DB_PATH)) return [];
  const db = getDb();
  try {
    if (!db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'inbox'").get()) {
      return []; // database predates the Telegram collector
    }
    return db
      .prepare("SELECT * FROM inbox ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC")
      .all() as InboxPost[];
  } finally {
    db.close();
  }
}
