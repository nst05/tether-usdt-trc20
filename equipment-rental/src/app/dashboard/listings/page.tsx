import Link from "next/link";
import { desc, eq } from "drizzle-orm";
import { redirect } from "next/navigation";
import { db } from "@/db";
import { listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { OwnerListingRow } from "@/components/owner-listing-row";

export default async function MyListingsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const rows = await db.query.listings.findMany({
    where: eq(listings.ownerId, session.user.id),
    orderBy: desc(listings.createdAt),
    with: { images: { orderBy: (img, { asc }) => asc(img.position), limit: 1 } },
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Мои объявления</h1>
        <Link
          href="/dashboard/listings/new"
          className="rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600"
        >
          + Разместить технику
        </Link>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-gray-500">
          У вас пока нет объявлений. Разместите первую единицу техники, чтобы
          начать получать заявки на аренду.
        </p>
      ) : (
        <div className="space-y-3">
          {rows.map((l) => (
            <OwnerListingRow
              key={l.id}
              listing={{
                id: l.id,
                title: l.title,
                city: l.city,
                pricePerDay: l.pricePerDay,
                status: l.status,
                imageUrl: l.images[0]?.url ?? null,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
