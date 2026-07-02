"use client";

import { useState } from "react";
import Image from "next/image";
import { Truck } from "lucide-react";

export function ListingGallery({
  images,
  title,
}: {
  images: { url: string }[];
  title: string;
}) {
  const [active, setActive] = useState(0);

  if (images.length === 0) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-xl bg-gray-100 text-gray-300">
        <Truck size={56} />
      </div>
    );
  }

  return (
    <div>
      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-gray-100">
        <Image
          src={images[active].url}
          alt={title}
          fill
          className="object-cover"
          sizes="(max-width: 768px) 100vw, 66vw"
          priority
        />
      </div>
      {images.length > 1 && (
        <div className="mt-3 flex gap-2 overflow-x-auto">
          {images.map((img, i) => (
            <button
              key={img.url}
              onClick={() => setActive(i)}
              className={`relative h-16 w-24 shrink-0 overflow-hidden rounded-md border-2 ${
                i === active ? "border-orange-500" : "border-transparent"
              }`}
            >
              <Image src={img.url} alt="" fill className="object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
