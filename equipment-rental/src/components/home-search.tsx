"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Search } from "lucide-react";

type Category = { id: string; name: string; slug: string };

export function HomeSearch({ categories }: { categories: Category[] }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (city) params.set("city", city);
    if (category) params.set("category", category);
    router.push(`/listings?${params.toString()}`);
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-8 flex flex-col gap-2 rounded-xl bg-white p-2 shadow-lg sm:flex-row"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Что ищете? Например, экскаватор"
        className="flex-1 rounded-md px-3 py-2.5 text-sm text-gray-900 focus:outline-none"
      />
      <input
        value={city}
        onChange={(e) => setCity(e.target.value)}
        placeholder="Город"
        className="rounded-md px-3 py-2.5 text-sm text-gray-900 focus:outline-none sm:w-40"
      />
      <select
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="rounded-md px-3 py-2.5 text-sm text-gray-900 focus:outline-none sm:w-48"
      >
        <option value="">Все категории</option>
        {categories.map((c) => (
          <option key={c.id} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
      <button
        type="submit"
        className="flex items-center justify-center gap-2 rounded-md bg-orange-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-orange-600"
      >
        <Search size={16} />
        Найти
      </button>
    </form>
  );
}
