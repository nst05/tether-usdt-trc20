"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Pencil, Trash2, Pause, Play } from "lucide-react";
import { formatMoney } from "@/lib/utils";

type Row = {
  id: string;
  title: string;
  city: string;
  pricePerDay: string;
  status: string;
  imageUrl: string | null;
};

export function OwnerListingRow({ listing }: { listing: Row }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function toggleStatus() {
    setBusy(true);
    await fetch(`/api/listings/${listing.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: listing.status === "active" ? "paused" : "active",
      }),
    });
    setBusy(false);
    router.refresh();
  }

  async function remove() {
    if (!confirm("Удалить объявление безвозвратно?")) return;
    setBusy(true);
    await fetch(`/api/listings/${listing.id}`, { method: "DELETE" });
    setBusy(false);
    router.refresh();
  }

  return (
    <div className="flex items-center gap-4 rounded-lg border border-black/5 bg-white p-3">
      <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-md bg-gray-100">
        {listing.imageUrl && (
          <Image src={listing.imageUrl} alt="" fill className="object-cover" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <Link
          href={`/listings/${listing.id}`}
          className="block truncate font-medium hover:text-orange-500"
        >
          {listing.title}
        </Link>
        <p className="text-sm text-gray-500">
          {listing.city} · {formatMoney(listing.pricePerDay)}/сутки
        </p>
      </div>
      <span
        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
          listing.status === "active"
            ? "bg-green-100 text-green-700"
            : "bg-gray-100 text-gray-600"
        }`}
      >
        {listing.status === "active" ? "Активно" : "На паузе"}
      </span>
      <div className="flex items-center gap-1">
        <button
          disabled={busy}
          onClick={toggleStatus}
          title={listing.status === "active" ? "Приостановить" : "Возобновить"}
          className="rounded-md p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-50"
        >
          {listing.status === "active" ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <Link
          href={`/dashboard/listings/${listing.id}/edit`}
          className="rounded-md p-2 text-gray-500 hover:bg-gray-100"
        >
          <Pencil size={16} />
        </Link>
        <button
          disabled={busy}
          onClick={remove}
          className="rounded-md p-2 text-red-500 hover:bg-red-50 disabled:opacity-50"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}
