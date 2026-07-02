import { eq, desc } from "drizzle-orm";
import { redirect } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { db } from "@/db";
import { bookings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/utils";
import { BookingStatusBadge } from "@/components/booking-status-badge";
import { BookingActions } from "@/components/booking-actions";

export default async function MyBookingsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const rows = await db.query.bookings.findMany({
    where: eq(bookings.renterId, session.user.id),
    with: {
      listing: {
        with: {
          images: { limit: 1, orderBy: (img, { asc }) => asc(img.position) },
          owner: { columns: { name: true, phone: true } },
        },
      },
    },
    orderBy: desc(bookings.createdAt),
  });

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Мои аренды</h1>
      <p className="mb-6 text-sm text-gray-500">
        История ваших заявок и бронирований техники.
      </p>

      {rows.length === 0 ? (
        <p className="text-sm text-gray-500">
          У вас пока нет бронирований.{" "}
          <Link href="/listings" className="font-medium text-orange-500">
            Найти технику
          </Link>
        </p>
      ) : (
        <div className="space-y-3">
          {rows.map((b) => (
            <div
              key={b.id}
              className="flex flex-col gap-3 rounded-lg border border-black/5 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="relative h-14 w-20 shrink-0 overflow-hidden rounded-md bg-gray-100">
                  {b.listing.images[0] && (
                    <Image
                      src={b.listing.images[0].url}
                      alt=""
                      fill
                      className="object-cover"
                    />
                  )}
                </div>
                <div className="min-w-0">
                  <Link
                    href={`/listings/${b.listing.id}`}
                    className="font-medium hover:text-orange-500"
                  >
                    {b.listing.title}
                  </Link>
                  <p className="text-sm text-gray-500">
                    {formatDate(b.startDate)} — {formatDate(b.endDate)} ·{" "}
                    {b.listing.owner.name}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <div className="text-right">
                  <p className="font-semibold">{formatMoney(b.totalAmount)}</p>
                  <BookingStatusBadge status={b.status} />
                </div>
                {b.status === "pending" && (
                  <BookingActions
                    bookingId={b.id}
                    actions={[
                      { status: "cancelled", label: "Отменить", variant: "danger" },
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
