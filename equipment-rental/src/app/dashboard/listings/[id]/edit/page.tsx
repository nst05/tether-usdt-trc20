import { eq } from "drizzle-orm";
import { notFound, redirect } from "next/navigation";
import { db } from "@/db";
import { listings } from "@/db/schema";
import { auth } from "@/lib/auth";
import { ListingForm } from "@/components/listing-form";

export default async function EditListingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await auth();
  if (!session?.user?.id) redirect("/auth/sign-in");

  const listing = await db.query.listings.findFirst({
    where: eq(listings.id, id),
    with: { images: { orderBy: (img, { asc }) => asc(img.position) } },
  });

  if (!listing) notFound();
  if (listing.ownerId !== session.user.id) redirect("/dashboard/listings");

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Редактировать объявление</h1>
      <p className="mb-6 text-sm text-gray-500">{listing.title}</p>
      <ListingForm
        listingId={listing.id}
        initialValues={{
          title: listing.title,
          description: listing.description,
          categoryId: listing.categoryId,
          city: listing.city,
          address: listing.address ?? "",
          pricePerDay: listing.pricePerDay,
          pricePerHour: listing.pricePerHour ?? "",
          depositAmount: listing.depositAmount,
          year: listing.year?.toString() ?? "",
          powerHp: listing.powerHp?.toString() ?? "",
          capacityTons: listing.capacityTons ?? "",
          withOperator: listing.withOperator,
          images: listing.images.map((i) => i.url),
        }}
      />
    </div>
  );
}
