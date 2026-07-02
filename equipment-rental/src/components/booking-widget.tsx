"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { formatMoney, PLATFORM_COMMISSION_PERCENT } from "@/lib/utils";

export function BookingWidget({
  listingId,
  pricePerDay,
  ownerId,
}: {
  listingId: string;
  pricePerDay: number;
  ownerId: string;
}) {
  const router = useRouter();
  const { data: session, status } = useSession();
  const isOwner = session?.user?.id === ownerId;

  const today = new Date().toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const days = useMemo(() => {
    if (!startDate || !endDate) return 0;
    const ms = new Date(endDate).getTime() - new Date(startDate).getTime();
    return Math.max(0, Math.round(ms / (1000 * 60 * 60 * 24)));
  }, [startDate, endDate]);

  const subtotal = days * pricePerDay;
  const commission = Math.round(subtotal * (PLATFORM_COMMISSION_PERCENT / 100));
  const total = subtotal + commission;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (status !== "authenticated") {
      router.push(`/auth/sign-in?callbackUrl=/listings/${listingId}`);
      return;
    }
    if (days <= 0) {
      setError("Выберите корректные даты аренды");
      return;
    }

    setLoading(true);

    const res = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ listingId, startDate, endDate, message }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      setError(data.error ?? "Не удалось создать заявку");
      setLoading(false);
      return;
    }

    const checkoutRes = await fetch("/api/stripe/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bookingId: data.id }),
    });
    const checkoutData = await checkoutRes.json().catch(() => ({}));
    setLoading(false);

    if (!checkoutRes.ok) {
      setError(
        checkoutData.error ??
          "Не удалось перейти к оплате. Заявка сохранена в разделе «Мои аренды»."
      );
      return;
    }

    window.location.href = checkoutData.url;
  }

  if (isOwner) {
    return (
      <div className="rounded-xl border border-black/5 bg-white p-5 text-sm text-gray-500">
        Это ваше собственное объявление.
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="sticky top-24 space-y-4 rounded-xl border border-black/5 bg-white p-5"
    >
      <p className="text-lg font-bold text-orange-500">
        {formatMoney(pricePerDay)}
        <span className="text-sm font-normal text-gray-400"> / сутки</span>
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium">С даты</label>
          <input
            type="date"
            required
            min={today}
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">По дату</label>
          <input
            type="date"
            required
            min={startDate || today}
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium">
          Сообщение владельцу (необязательно)
        </label>
        <textarea
          rows={3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-orange-500 focus:outline-none"
        />
      </div>

      {days > 0 && (
        <div className="space-y-1 border-t border-black/5 pt-3 text-sm">
          <div className="flex justify-between text-gray-500">
            <span>
              {formatMoney(pricePerDay)} × {days} сут.
            </span>
            <span>{formatMoney(subtotal)}</span>
          </div>
          <div className="flex justify-between text-gray-500">
            <span>Сервисный сбор ({PLATFORM_COMMISSION_PERCENT}%)</span>
            <span>{formatMoney(commission)}</span>
          </div>
          <div className="flex justify-between font-bold">
            <span>Итого</span>
            <span>{formatMoney(total)}</span>
          </div>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-md bg-orange-500 py-2.5 text-sm font-semibold text-white hover:bg-orange-600 disabled:opacity-60"
      >
        {loading ? "Обработка..." : "Забронировать и оплатить"}
      </button>
      <p className="text-center text-xs text-gray-400">
        Оплата спишется после подтверждения через безопасный платёжный шлюз
      </p>
    </form>
  );
}
