import { NextResponse } from "next/server";
import { db } from "@/db";
import { listingImages, listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { findListings } from "@/lib/listings";
import { listingSchema } from "@/lib/validators";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);

  const rows = await findListings({
    category: searchParams.get("category"),
    city: searchParams.get("city"),
    q: searchParams.get("q"),
    minPrice: searchParams.get("minPrice"),
    maxPrice: searchParams.get("maxPrice"),
    sort: searchParams.get("sort"),
    ownerId: searchParams.get("ownerId"),
  });

  return NextResponse.json(rows);
}

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const parsed = listingSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Некорректные данные" },
      { status: 400 }
    );
  }

  const { images, ...data } = parsed.data;

  const [created] = await db
    .insert(listings)
    .values({
      ownerId: session.user.id,
      categoryId: data.categoryId,
      title: data.title,
      description: data.description,
      city: data.city,
      address: data.address || null,
      pricePerDay: String(data.pricePerDay),
      pricePerHour:
        data.pricePerHour != null ? String(data.pricePerHour) : null,
      depositAmount: String(data.depositAmount ?? 0),
      year: data.year ?? null,
      powerHp: data.powerHp ?? null,
      capacityTons:
        data.capacityTons != null ? String(data.capacityTons) : null,
      withOperator: data.withOperator ?? false,
    })
    .returning();

  if (images.length > 0) {
    await db.insert(listingImages).values(
      images.map((url, position) => ({
        listingId: created.id,
        url,
        position,
      }))
    );
  }

  return NextResponse.json(created, { status: 201 });
}
