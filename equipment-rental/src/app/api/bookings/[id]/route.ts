import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { bookings } from "@/db/schema";
import { auth } from "@/lib/auth";

const OWNER_ALLOWED_FROM_PAID = new Set(["completed", "declined"]);
const RENTER_ALLOWED = new Set(["cancelled"]);

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const status = body?.status as string | undefined;
  if (!status) {
    return NextResponse.json({ error: "Не указан статус" }, { status: 400 });
  }

  const booking = await db.query.bookings.findFirst({
    where: eq(bookings.id, id),
    with: { listing: true },
  });

  if (!booking) {
    return NextResponse.json({ error: "Не найдено" }, { status: 404 });
  }

  const isOwner = booking.listing.ownerId === session.user.id;
  const isRenter = booking.renterId === session.user.id;

  if (isOwner && booking.status === "paid" && OWNER_ALLOWED_FROM_PAID.has(status)) {
    await db.update(bookings).set({ status: status as never }).where(eq(bookings.id, id));
    return NextResponse.json({ ok: true });
  }

  if (isRenter && RENTER_ALLOWED.has(status) && booking.status === "pending") {
    await db.update(bookings).set({ status: status as never }).where(eq(bookings.id, id));
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "Недопустимое действие" }, { status: 403 });
}
