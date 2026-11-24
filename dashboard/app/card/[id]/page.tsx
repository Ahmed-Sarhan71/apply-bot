import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Card } from "../../card-view";
import { getApplication } from "@/lib/db";

export default async function ApplicationPage({ params }: PageProps<"/card/[id]">) {
  await connection();
  const { id } = await params;
  const app = getApplication(Number(id));
  if (!app) notFound();

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-10">
      <Link href="/table" className="text-sm underline">
        ← All applications
      </Link>
      <div className="mt-4">
        <Card app={app} />
      </div>
    </main>
  );
}
