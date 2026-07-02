import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { listingImages, listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { listingSchema } from "@/lib/validators";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;

  const listing = await db.query.listings.findFirst({
    where: eq(listings.id, id),
    with: {
      images: { orderBy: (img, { asc }) => asc(img.position) },
      category: true,
      owner: { columns: { id: true, name: true, image: true, city: true } },
    },
  });

  if (!listing) {
    return NextResponse.json({ error: "Не найдено" }, { status: 404 });
  }

  return NextResponse.json(listing);
}

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const [existing] = await db
    .select({ ownerId: listings.ownerId })
    .from(listings)
    .where(eq(listings.id, id))
    .limit(1);

  if (!existing) {
    return NextResponse.json({ error: "Не найдено" }, { status: 404 });
  }
  if (existing.ownerId !== session.user.id) {
    return NextResponse.json({ error: "Нет доступа" }, { status: 403 });
  }

  const body = await req.json().catch(() => null);

  if (body?.status) {
    await db
      .update(listings)
      .set({ status: body.status, updatedAt: new Date() })
      .where(eq(listings.id, id));
    return NextResponse.json({ ok: true });
  }

  const parsed = listingSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Некорректные данные" },
      { status: 400 }
    );
  }

  const { images, ...data } = parsed.data;

  await db
    .update(listings)
    .set({
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
      updatedAt: new Date(),
    })
    .where(eq(listings.id, id));

  await db.delete(listingImages).where(eq(listingImages.listingId, id));
  if (images.length > 0) {
    await db.insert(listingImages).values(
      images.map((url, position) => ({
        listingId: id,
        url,
        position,
      }))
    );
  }

  return NextResponse.json({ ok: true });
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const [existing] = await db
    .select({ ownerId: listings.ownerId })
    .from(listings)
    .where(eq(listings.id, id))
    .limit(1);

  if (!existing) {
    return NextResponse.json({ error: "Не найдено" }, { status: 404 });
  }
  if (existing.ownerId !== session.user.id) {
    return NextResponse.json({ error: "Нет доступа" }, { status: 403 });
  }

  await db.delete(listings).where(eq(listings.id, id));

  return NextResponse.json({ ok: true });
}
