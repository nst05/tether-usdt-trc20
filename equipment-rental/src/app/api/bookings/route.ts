import { NextResponse } from "next/server";
import { and, eq, inArray, lt, gt } from "drizzle-orm";
import { db } from "@/db";
import { bookings, listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { bookingSchema } from "@/lib/validators";
import { PLATFORM_COMMISSION_PERCENT } from "@/lib/utils";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const parsed = bookingSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Некорректные данные" },
      { status: 400 }
    );
  }

  const { listingId, startDate, endDate, message } = parsed.data;

  const [listing] = await db
    .select()
    .from(listings)
    .where(eq(listings.id, listingId))
    .limit(1);

  if (!listing || listing.status !== "active") {
    return NextResponse.json(
      { error: "Объявление недоступно" },
      { status: 404 }
    );
  }

  if (listing.ownerId === session.user.id) {
    return NextResponse.json(
      { error: "Нельзя арендовать собственную технику" },
      { status: 400 }
    );
  }

  const overlapping = await db
    .select({ id: bookings.id })
    .from(bookings)
    .where(
      and(
        eq(bookings.listingId, listingId),
        inArray(bookings.status, ["confirmed", "paid"]),
        lt(bookings.startDate, endDate),
        gt(bookings.endDate, startDate)
      )
    )
    .limit(1);

  if (overlapping.length > 0) {
    return NextResponse.json(
      { error: "Техника уже забронирована на эти даты" },
      { status: 409 }
    );
  }

  const days = Math.max(
    1,
    Math.round(
      (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)
    )
  );
  const subtotal = days * Number(listing.pricePerDay);
  const commission = Math.round(subtotal * (PLATFORM_COMMISSION_PERCENT / 100));
  const total = subtotal + commission;

  const [booking] = await db
    .insert(bookings)
    .values({
      listingId,
      renterId: session.user.id,
      startDate,
      endDate,
      days,
      subtotalAmount: String(subtotal),
      commissionPercent: String(PLATFORM_COMMISSION_PERCENT),
      commissionAmount: String(commission),
      totalAmount: String(total),
      message: message || null,
      status: "pending",
    })
    .returning();

  return NextResponse.json(booking, { status: 201 });
}

export async function GET(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const as = searchParams.get("as");

  if (as === "owner") {
    const ownedListings = await db
      .select({ id: listings.id })
      .from(listings)
      .where(eq(listings.ownerId, session.user.id));

    const listingIds = ownedListings.map((l) => l.id);
    if (listingIds.length === 0) return NextResponse.json([]);

    const rows = await db.query.bookings.findMany({
      where: inArray(bookings.listingId, listingIds),
      with: {
        listing: { with: { images: { limit: 1 } } },
        renter: { columns: { id: true, name: true, phone: true } },
      },
      orderBy: (b, { desc }) => desc(b.createdAt),
    });
    return NextResponse.json(rows);
  }

  const rows = await db.query.bookings.findMany({
    where: eq(bookings.renterId, session.user.id),
    with: {
      listing: { with: { images: { limit: 1 }, owner: { columns: { name: true } } } },
    },
    orderBy: (b, { desc }) => desc(b.createdAt),
  });

  return NextResponse.json(rows);
}
