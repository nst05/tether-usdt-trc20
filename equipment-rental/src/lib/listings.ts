import { and, asc, desc, eq, gte, ilike, lte, type SQL } from "drizzle-orm";
import { db } from "@/db";
import { categories, listings } from "@/db/schema";

export type ListingFilters = {
  category?: string | null;
  city?: string | null;
  q?: string | null;
  minPrice?: string | null;
  maxPrice?: string | null;
  sort?: string | null;
  ownerId?: string | null;
};

export async function findListings(filters: ListingFilters) {
  const { category, city, q, minPrice, maxPrice, sort, ownerId } = filters;

  const conditions: SQL[] = ownerId ? [] : [eq(listings.status, "active")];

  if (category) {
    const [cat] = await db
      .select({ id: categories.id })
      .from(categories)
      .where(eq(categories.slug, category))
      .limit(1);
    if (cat) conditions.push(eq(listings.categoryId, cat.id));
  }

  if (city) conditions.push(ilike(listings.city, `%${city}%`));
  if (q) conditions.push(ilike(listings.title, `%${q}%`));
  if (minPrice) conditions.push(gte(listings.pricePerDay, minPrice));
  if (maxPrice) conditions.push(lte(listings.pricePerDay, maxPrice));
  if (ownerId) conditions.push(eq(listings.ownerId, ownerId));

  const orderBy =
    sort === "price_asc"
      ? asc(listings.pricePerDay)
      : sort === "price_desc"
        ? desc(listings.pricePerDay)
        : desc(listings.createdAt);

  return db.query.listings.findMany({
    where: and(...conditions),
    orderBy,
    with: {
      images: { orderBy: (img, { asc }) => asc(img.position) },
      category: true,
      owner: { columns: { id: true, name: true, image: true } },
    },
    limit: 60,
  });
}
