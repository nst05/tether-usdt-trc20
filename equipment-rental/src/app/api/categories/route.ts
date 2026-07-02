import { NextResponse } from "next/server";
import { db } from "@/db";
import { categories } from "@/db/schema";

export async function GET() {
  const rows = await db.select().from(categories).orderBy(categories.name);
  return NextResponse.json(rows);
}
