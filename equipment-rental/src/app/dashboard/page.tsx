import Link from "next/link";
import { and, eq, inArray } from "drizzle-orm";
import { redirect } from "next/navigation";
import { db } from "@/db";
import { bookings, listings, users } from "@/db/schema";
import { auth } from "@/lib/auth";
import { formatMoney } from "@/lib/utils";

export default async function DashboardOverviewPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const [me] = await db
    .select()
    .from(users)
    .where(eq(users.id, session.user.id))
    .limit(1);

  const myListings = await db
    .select({ id: listings.id, status: listings.status })
    .from(listings)
    .where(eq(listings.ownerId, session.user.id));

  const listingIds = myListings.map((l) => l.id);

  const incomingBookings = listingIds.length
    ? await db
        .select()
        .from(bookings)
        .where(
          and(
            inArray(bookings.listingId, listingIds),
            inArray(bookings.status, ["pending", "confirmed", "paid"])
          )
        )
    : [];

  const myBookingsAsRenter = await db
    .select()
    .from(bookings)
    .where(eq(bookings.renterId, session.user.id));

  const earnings = incomingBookings
    .filter((b) => b.status === "paid")
    .reduce((sum, b) => sum + Number(b.subtotalAmount), 0);

  const stats = [
    { label: "Активные объявления", value: myListings.filter((l) => l.status === "active").length },
    { label: "Всего объявлений", value: myListings.length },
    { label: "Заявки на мою технику", value: incomingBookings.length },
    { label: "Мои аренды", value: myBookingsAsRenter.length },
  ];

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Здравствуйте, {me?.name}</h1>
      <p className="mb-6 text-sm text-gray-500">
        Обзор вашей активности на платформе.
      </p>

      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border border-black/5 bg-white p-4">
            <p className="text-2xl font-bold">{s.value}</p>
            <p className="text-xs text-gray-500">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-black/5 bg-white p-5">
          <p className="mb-1 font-semibold">Заработано (получено оплат)</p>
          <p className="text-2xl font-bold text-orange-500">{formatMoney(earnings)}</p>
          <p className="mt-1 text-xs text-gray-500">
            Без учёта комиссии платформы. Выплаты приходят на ваш Stripe-счёт.
          </p>
        </div>
        <div className="rounded-lg border border-black/5 bg-white p-5">
          <p className="mb-1 font-semibold">Приём платежей</p>
          <p className="text-sm text-gray-600">
            {me?.stripeOnboardingComplete
              ? "Ваш счёт для выплат подключён."
              : "Подключите счёт для выплат, чтобы получать оплату за аренду."}
          </p>
          <Link
            href="/dashboard/payouts"
            className="mt-3 inline-block rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600"
          >
            {me?.stripeOnboardingComplete ? "Управление выплатами" : "Подключить выплаты"}
          </Link>
        </div>
      </div>
    </div>
  );
}
