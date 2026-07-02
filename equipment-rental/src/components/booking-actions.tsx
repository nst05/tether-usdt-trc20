"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function BookingActions({
  bookingId,
  actions,
}: {
  bookingId: string;
  actions: { status: string; label: string; variant?: "danger" }[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function act(status: string) {
    setBusy(status);
    await fetch(`/api/bookings/${bookingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    setBusy(null);
    router.refresh();
  }

  if (actions.length === 0) return null;

  return (
    <div className="flex gap-2">
      {actions.map((a) => (
        <button
          key={a.status}
          disabled={busy !== null}
          onClick={() => act(a.status)}
          className={`rounded-md px-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${
            a.variant === "danger"
              ? "bg-red-50 text-red-600 hover:bg-red-100"
              : "bg-orange-50 text-orange-600 hover:bg-orange-100"
          }`}
        >
          {busy === a.status ? "..." : a.label}
        </button>
      ))}
    </div>
  );
}
