"use client";

import { useState } from "react";

export function ConnectPayoutsButton({ isComplete }: { isComplete: boolean }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    setLoading(true);
    setError(null);
    const res = await fetch("/api/stripe/connect", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(data.error ?? "Не удалось начать подключение");
      setLoading(false);
      return;
    }
    window.location.href = data.url;
  }

  return (
    <div>
      <button
        onClick={connect}
        disabled={loading}
        className="rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600 disabled:opacity-60"
      >
        {loading
          ? "Открываем Stripe..."
          : isComplete
            ? "Обновить данные для выплат"
            : "Подключить приём выплат"}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
