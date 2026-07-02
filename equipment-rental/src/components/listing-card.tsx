import Link from "next/link";
import Image from "next/image";
import { MapPin, Truck } from "lucide-react";
import { formatMoney } from "@/lib/utils";

export type ListingCardData = {
  id: string;
  title: string;
  city: string;
  pricePerDay: string;
  withOperator: boolean;
  category: { name: string } | null;
  images: { url: string }[];
};

export function ListingCard({ listing }: { listing: ListingCardData }) {
  const image = listing.images[0]?.url;

  return (
    <Link
      href={`/listings/${listing.id}`}
      className="group overflow-hidden rounded-xl border border-black/5 bg-white transition hover:shadow-md"
    >
      <div className="relative aspect-[4/3] w-full bg-gray-100">
        {image ? (
          <Image
            src={image}
            alt={listing.title}
            fill
            className="object-cover transition group-hover:scale-105"
            sizes="(max-width: 768px) 100vw, 25vw"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-gray-300">
            <Truck size={40} />
          </div>
        )}
        {listing.category && (
          <span className="absolute left-2 top-2 rounded-full bg-white/90 px-2.5 py-1 text-xs font-medium text-gray-700">
            {listing.category.name}
          </span>
        )}
      </div>
      <div className="p-4">
        <h3 className="mb-1 truncate font-semibold text-gray-900 group-hover:text-orange-500">
          {listing.title}
        </h3>
        <p className="mb-2 flex items-center gap-1 text-sm text-gray-500">
          <MapPin size={14} />
          {listing.city}
          {listing.withOperator && " · с оператором"}
        </p>
        <p className="font-bold text-orange-500">
          {formatMoney(listing.pricePerDay)}
          <span className="text-xs font-normal text-gray-400"> / сутки</span>
        </p>
      </div>
    </Link>
  );
}
