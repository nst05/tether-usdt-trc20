import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import Stripe from "stripe";
import { db } from "@/db";
import { bookings, users } from "@/db/schema";
import { stripe } from "@/lib/stripe";

export async function POST(req: Request) {
  const signature = req.headers.get("stripe-signature");
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (!signature || !webhookSecret) {
    return NextResponse.json({ error: "Webhook не настроен" }, { status: 400 });
  }

  const rawBody = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, signature, webhookSecret);
  } catch {
    return NextResponse.json({ error: "Неверная подпись" }, { status: 400 });
  }

  switch (event.type) {
    case "checkout.session.completed": {
      const checkoutSession = event.data.object as Stripe.Checkout.Session;
      const bookingId = checkoutSession.metadata?.bookingId;
      if (bookingId) {
        await db
          .update(bookings)
          .set({
            status: "paid",
            stripePaymentIntentId:
              typeof checkoutSession.payment_intent === "string"
                ? checkoutSession.payment_intent
                : null,
          })
          .where(eq(bookings.id, bookingId));
      }
      break;
    }
    case "account.updated": {
      const account = event.data.object as Stripe.Account;
      const ready = Boolean(account.charges_enabled && account.payouts_enabled);
      await db
        .update(users)
        .set({ stripeOnboardingComplete: ready })
        .where(eq(users.stripeAccountId, account.id));
      break;
    }
    default:
      break;
  }

  return NextResponse.json({ received: true });
}
