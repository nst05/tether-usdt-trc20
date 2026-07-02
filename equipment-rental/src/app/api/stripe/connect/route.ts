import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { users } from "@/db/schema";
import { auth } from "@/lib/auth";
import { stripe, getAppUrl } from "@/lib/stripe";

export async function POST() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Требуется вход" }, { status: 401 });
  }

  const [me] = await db
    .select()
    .from(users)
    .where(eq(users.id, session.user.id))
    .limit(1);

  if (!me) {
    return NextResponse.json({ error: "Пользователь не найден" }, { status: 404 });
  }

  let accountId = me.stripeAccountId;

  if (!accountId) {
    const account = await stripe.accounts.create({
      type: "express",
      email: me.email,
      business_type: "individual",
    });
    accountId = account.id;
    await db
      .update(users)
      .set({ stripeAccountId: accountId })
      .where(eq(users.id, me.id));
  }

  const appUrl = getAppUrl();

  const accountLink = await stripe.accountLinks.create({
    account: accountId,
    refresh_url: `${appUrl}/dashboard/payouts`,
    return_url: `${appUrl}/dashboard/payouts?onboarding=complete`,
    type: "account_onboarding",
  });

  return NextResponse.json({ url: accountLink.url });
}
