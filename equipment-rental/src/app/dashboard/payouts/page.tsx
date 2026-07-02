import { eq } from "drizzle-orm";
import { redirect } from "next/navigation";
import { db } from "@/db";
import { users } from "@/db/schema";
import { auth } from "@/lib/auth";
import { PLATFORM_COMMISSION_PERCENT } from "@/lib/utils";
import { ConnectPayoutsButton } from "@/components/connect-payouts-button";

export default async function PayoutsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const [me] = await db
    .select()
    .from(users)
    .where(eq(users.id, session.user.id))
    .limit(1);

  return (
    <div className="max-w-xl">
      <h1 className="mb-1 text-2xl font-bold">Выплаты</h1>
      <p className="mb-6 text-sm text-gray-500">
        Чтобы получать оплату за аренду вашей техники напрямую на банковский
        счёт, подключите приём выплат. Мы используем Stripe Connect для
        безопасных выплат и удерживаем комиссию платформы (
        {PLATFORM_COMMISSION_PERCENT}%) автоматически с каждой сделки.
      </p>

      <div className="rounded-xl border border-black/5 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <span className="font-medium">Статус подключения</span>
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              me?.stripeOnboardingComplete
                ? "bg-green-100 text-green-700"
                : "bg-yellow-100 text-yellow-700"
            }`}
          >
            {me?.stripeOnboardingComplete ? "Подключено" : "Не подключено"}
          </span>
        </div>
        <ConnectPayoutsButton
          isComplete={Boolean(me?.stripeOnboardingComplete)}
        />
      </div>
    </div>
  );
}
