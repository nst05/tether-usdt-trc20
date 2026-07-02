import { Suspense } from "react";
import { db } from "@/db";
import { categories } from "@/db/schema";
import { findListings } from "@/lib/listings";
import { ListingCard } from "@/components/listing-card";
import { ListingsFilters } from "@/components/listings-filters";

export default async function ListingsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) =>
    Array.isArray(v) ? v[0] : v;

  const [cats, rows] = await Promise.all([
    db.select().from(categories).orderBy(categories.name),
    findListings({
      category: one(sp.category) ?? null,
      city: one(sp.city) ?? null,
      q: one(sp.q) ?? null,
      minPrice: one(sp.minPrice) ?? null,
      maxPrice: one(sp.maxPrice) ?? null,
      sort: one(sp.sort) ?? null,
    }),
  ]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 text-2xl font-bold">Каталог спецтехники</h1>

      <Suspense fallback={null}>
        <ListingsFilters categories={cats} />
      </Suspense>

      {rows.length === 0 ? (
        <p className="py-12 text-center text-sm text-gray-500">
          Ничего не найдено. Попробуйте изменить параметры поиска.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {rows.map((l) => (
            <ListingCard key={l.id} listing={l} />
          ))}
        </div>
      )}
    </div>
  );
}
