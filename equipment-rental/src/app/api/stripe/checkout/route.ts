import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { bookings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { stripe, getAppUrl } from "@/lib/stripe";

const STRIPE_CURRENCY = process.env.STRIPE_CURRENCY ?? "usd";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const bookingId = body?.bookingId as string | undefined;
  if (!bookingId) {
    return NextResponse.json({ error: "Не указана заявка" }, { status: 400 });
  }

  const booking = await db.query.bookings.findFirst({
    where: eq(bookings.id, bookingId),
    with: { listing: { with: { owner: true } } },
  });

  if (!booking) {
    return NextResponse.json({ error: "Заявка не найдена" }, { status: 404 });
  }
  if (booking.renterId !== session.user.id) {
    return NextResponse.json({ error: "Нет доступа" }, { status: 403 });
  }
  if (booking.status !== "pending") {
    return NextResponse.json(
      { error: "Оплата для этой заявки недоступна" },
      { status: 400 }
    );
  }

  const owner = booking.listing.owner;
  if (!owner.stripeAccountId || !owner.stripeOnboardingComplete) {
    return NextResponse.json(
      {
        error:
          "Владелец техники ещё не подключил приём выплат. Оплата временно недоступна.",
      },
      { status: 400 }
    );
  }

  const totalAmount = Number(booking.totalAmount);
  const commissionAmount = Number(booking.commissionAmount);
  const amountInMinorUnits = Math.round(totalAmount * 100);
  const applicationFeeInMinorUnits = Math.round(commissionAmount * 100);

  const appUrl = getAppUrl();

  const checkoutSession = await stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [
      {
        price_data: {
          currency: STRIPE_CURRENCY,
          unit_amount: amountInMinorUnits,
          product_data: {
            name: `Аренда: ${booking.listing.title}`,
            description: `${booking.days} сут. с ${booking.startDate.toISOString().slice(0, 10)} по ${booking.endDate.toISOString().slice(0, 10)}`,
          },
        },
        quantity: 1,
      },
    ],
    payment_intent_data: {
      application_fee_amount: applicationFeeInMinorUnits,
      transfer_data: {
        destination: owner.stripeAccountId,
      },
    },
    metadata: { bookingId: booking.id },
    success_url: `${appUrl}/dashboard/my-bookings?payment=success`,
    cancel_url: `${appUrl}/listings/${booking.listing.id}?payment=cancelled`,
  });

  await db
    .update(bookings)
    .set({ stripeCheckoutSessionId: checkoutSession.id })
    .where(eq(bookings.id, booking.id));

  return NextResponse.json({ url: checkoutSession.url });
}
