"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

type Category = { id: string; name: string; slug: string };

export function ListingsFilters({ categories }: { categories: Category[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [city, setCity] = useState(searchParams.get("city") ?? "");
  const [category, setCategory] = useState(searchParams.get("category") ?? "");
  const [minPrice, setMinPrice] = useState(searchParams.get("minPrice") ?? "");
  const [maxPrice, setMaxPrice] = useState(searchParams.get("maxPrice") ?? "");
  const [sort, setSort] = useState(searchParams.get("sort") ?? "newest");

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (city) params.set("city", city);
    if (category) params.set("category", category);
    if (minPrice) params.set("minPrice", minPrice);
    if (maxPrice) params.set("maxPrice", maxPrice);
    if (sort && sort !== "newest") params.set("sort", sort);
    router.push(`/listings?${params.toString()}`);
  }

  return (
    <form
      onSubmit={apply}
      className="mb-6 grid grid-cols-2 gap-3 rounded-lg border border-black/5 bg-white p-4 sm:grid-cols-3 lg:grid-cols-6"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Поиск по названию"
        className="col-span-2 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none lg:col-span-1"
      />
      <input
        value={city}
        onChange={(e) => setCity(e.target.value)}
        placeholder="Город"
        className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
      />
      <select
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
      >
        <option value="">Все категории</option>
        {categories.map((c) => (
          <option key={c.id} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
      <input
        value={minPrice}
        onChange={(e) => setMinPrice(e.target.value)}
        placeholder="Цена от"
        type="number"
        className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
      />
      <input
        value={maxPrice}
        onChange={(e) => setMaxPrice(e.target.value)}
        placeholder="Цена до"
        type="number"
        className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
      />
      <select
        value={sort}
        onChange={(e) => setSort(e.target.value)}
        className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
      >
        <option value="newest">Сначала новые</option>
        <option value="price_asc">Сначала дешевле</option>
        <option value="price_desc">Сначала дороже</option>
      </select>
      <button
        type="submit"
        className="col-span-2 rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600 sm:col-span-1 lg:col-span-6"
      >
        Применить фильтры
      </button>
    </form>
  );
}
