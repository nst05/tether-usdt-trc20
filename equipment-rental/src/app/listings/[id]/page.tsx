import { eq } from "drizzle-orm";
import { notFound } from "next/navigation";
import { MapPin, Calendar, Gauge, Weight, UserCheck } from "lucide-react";
import { db } from "@/db";
import { listings } from "@/db/schema";
import { ListingGallery } from "@/components/listing-gallery";
import { BookingWidget } from "@/components/booking-widget";

export default async function ListingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const listing = await db.query.listings.findFirst({
    where: eq(listings.id, id),
    with: {
      images: { orderBy: (img, { asc }) => asc(img.position) },
      category: true,
      owner: { columns: { id: true, name: true, image: true, createdAt: true } },
    },
  });

  if (!listing || listing.status === "archived") notFound();

  const specs = [
    listing.year && { icon: Calendar, label: "Год выпуска", value: listing.year },
    listing.powerHp && { icon: Gauge, label: "Мощность", value: `${listing.powerHp} л.с.` },
    listing.capacityTons && {
      icon: Weight,
      label: "Грузоподъёмность",
      value: `${listing.capacityTons} т`,
    },
    listing.withOperator && { icon: UserCheck, label: "Оператор", value: "В комплекте" },
  ].filter(Boolean) as { icon: typeof Calendar; label: string; value: string | number }[];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <div className="grid gap-8 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ListingGallery images={listing.images} title={listing.title} />

          <div className="mt-6">
            <span className="mb-2 inline-block rounded-full bg-orange-50 px-2.5 py-1 text-xs font-medium text-orange-600">
              {listing.category.name}
            </span>
            <h1 className="text-2xl font-bold">{listing.title}</h1>
            <p className="mt-1 flex items-center gap-1 text-sm text-gray-500">
              <MapPin size={14} />
              {listing.city}
              {listing.address && `, ${listing.address}`}
            </p>
          </div>

          {specs.length > 0 && (
            <div className="mt-6 grid grid-cols-2 gap-4 rounded-xl border border-black/5 bg-white p-5 sm:grid-cols-4">
              {specs.map((s) => (
                <div key={s.label}>
                  <s.icon className="mb-1 text-orange-500" size={18} />
                  <p className="text-xs text-gray-400">{s.label}</p>
                  <p className="text-sm font-semibold">{s.value}</p>
                </div>
              ))}
            </div>
          )}

          <div className="mt-6">
            <h2 className="mb-2 text-lg font-semibold">Описание</h2>
            <p className="whitespace-pre-line text-sm text-gray-600">
              {listing.description || "Владелец пока не добавил описание."}
            </p>
          </div>

          <div className="mt-6 flex items-center gap-3 rounded-xl border border-black/5 bg-white p-5">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-orange-100 font-bold text-orange-600">
              {listing.owner.name.charAt(0).toUpperCase()}
            </div>
            <div>
              <p className="font-semibold">{listing.owner.name}</p>
              <p className="text-xs text-gray-500">
                На платформе с {new Date(listing.owner.createdAt).getFullYear()} года
              </p>
            </div>
          </div>
        </div>

        <div>
          <BookingWidget
            listingId={listing.id}
            pricePerDay={Number(listing.pricePerDay)}
            ownerId={listing.owner.id}
          />
        </div>
      </div>
    </div>
  );
}
