import { eq, inArray, desc } from "drizzle-orm";
import { redirect } from "next/navigation";
import Link from "next/link";
import { db } from "@/db";
import { bookings, listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/utils";
import { BookingStatusBadge } from "@/components/booking-status-badge";
import { BookingActions } from "@/components/booking-actions";

export default async function OwnerBookingsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const ownedListings = await db
    .select({ id: listings.id })
    .from(listings)
    .where(eq(listings.ownerId, session.user.id));

  const listingIds = ownedListings.map((l) => l.id);

  const rows = listingIds.length
    ? await db.query.bookings.findMany({
        where: inArray(bookings.listingId, listingIds),
        with: {
          listing: { columns: { id: true, title: true } },
          renter: { columns: { name: true, phone: true } },
        },
        orderBy: desc(bookings.createdAt),
      })
    : [];

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Заявки на мою технику</h1>
      <p className="mb-6 text-sm text-gray-500">
        Здесь появляются заявки арендаторов на вашу технику.
      </p>

      {rows.length === 0 ? (
        <p className="text-sm text-gray-500">Пока нет заявок.</p>
      ) : (
        <div className="space-y-3">
          {rows.map((b) => (
            <div
              key={b.id}
              className="flex flex-col gap-3 rounded-lg border border-black/5 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <Link
                  href={`/listings/${b.listing.id}`}
                  className="font-medium hover:text-orange-500"
                >
                  {b.listing.title}
                </Link>
                <p className="text-sm text-gray-500">
                  {formatDate(b.startDate)} — {formatDate(b.endDate)} ·{" "}
                  {b.renter.name}
                  {b.renter.phone ? ` · ${b.renter.phone}` : ""}
                </p>
                {b.message && (
                  <p className="mt-1 text-sm text-gray-400">«{b.message}»</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <div className="text-right">
                  <p className="font-semibold">{formatMoney(b.subtotalAmount)}</p>
                  <BookingStatusBadge status={b.status} />
                </div>
                {b.status === "paid" && (
                  <BookingActions
                    bookingId={b.id}
                    actions={[
                      { status: "completed", label: "Завершить" },
                      { status: "declined", label: "Отменить", variant: "danger" },
                    ]}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
