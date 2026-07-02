import Link from "next/link";
import { desc } from "drizzle-orm";
import {
  Construction,
  HandCoins,
  ShieldCheck,
  Search,
  ClipboardCheck,
  Truck,
} from "lucide-react";
import { db } from "@/db";
import { categories, listings } from "@/db/schema";
import { ListingCard } from "@/components/listing-card";
import { HomeSearch } from "@/components/home-search";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [cats, featured] = await Promise.all([
    db.select().from(categories).orderBy(categories.name),
    db.query.listings.findMany({
      orderBy: desc(listings.createdAt),
      limit: 8,
      with: {
        images: { orderBy: (img, { asc }) => asc(img.position), limit: 1 },
        category: true,
      },
    }),
  ]);

  return (
    <div>
      <section className="bg-gradient-to-b from-gray-900 to-gray-800 py-16 text-white">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h1 className="max-w-2xl text-3xl font-bold sm:text-4xl">
            Аренда спецтехники напрямую от владельцев
          </h1>
          <p className="mt-4 max-w-xl text-gray-300">
            Экскаваторы, краны, погрузчики, бетономешалки и другая техника —
            найдите подходящую единицу в вашем городе или разместите свою и
            начните зарабатывать.
          </p>

          <HomeSearch categories={cats} />

          <div className="mt-6 flex flex-wrap gap-3 text-sm">
            <Link
              href="/dashboard/listings/new"
              className="rounded-md border border-white/30 px-4 py-2 font-medium hover:bg-white/10"
            >
              Разместить свою технику
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <h2 className="mb-5 text-xl font-bold">Категории техники</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {cats.map((c) => (
            <Link
              key={c.id}
              href={`/listings?category=${c.slug}`}
              className="flex items-center gap-3 rounded-lg border border-black/5 bg-white p-4 hover:border-orange-300 hover:bg-orange-50"
            >
              <Construction className="shrink-0 text-orange-500" size={22} />
              <span className="text-sm font-medium">{c.name}</span>
            </Link>
          ))}
        </div>
      </section>

      {featured.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-xl font-bold">Новые объявления</h2>
            <Link href="/listings" className="text-sm font-medium text-orange-500">
              Смотреть все →
            </Link>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {featured.map((l) => (
              <ListingCard key={l.id} listing={l} />
            ))}
          </div>
        </section>
      )}

      <section className="bg-white py-14">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="mb-8 text-xl font-bold">Как это работает</h2>
          <div className="grid gap-8 sm:grid-cols-3">
            <div>
              <Search className="mb-3 text-orange-500" size={28} />
              <p className="mb-1 font-semibold">1. Найдите технику</p>
              <p className="text-sm text-gray-500">
                Используйте поиск и фильтры, чтобы найти нужную технику в
                вашем городе.
              </p>
            </div>
            <div>
              <ClipboardCheck className="mb-3 text-orange-500" size={28} />
              <p className="mb-1 font-semibold">2. Забронируйте и оплатите</p>
              <p className="text-sm text-gray-500">
                Отправьте заявку владельцу и оплатите аренду онлайн — деньги
                поступят владельцу после подтверждения.
              </p>
            </div>
            <div>
              <Truck className="mb-3 text-orange-500" size={28} />
              <p className="mb-1 font-semibold">3. Получите технику</p>
              <p className="text-sm text-gray-500">
                Заберите технику или дождитесь доставки — по договорённости с
                владельцем.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <div className="rounded-2xl bg-orange-500 p-8 text-white sm:p-12">
          <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="mb-2 text-2xl font-bold">
                Есть спецтехника? Сдавайте её в аренду
              </h2>
              <p className="flex items-center gap-2 text-orange-50">
                <HandCoins size={18} />
                Мы берём небольшую комиссию только с успешных сделок — без
                скрытых платежей.
              </p>
              <p className="mt-1 flex items-center gap-2 text-orange-50">
                <ShieldCheck size={18} />
                Оплата проходит через защищённый платёжный шлюз.
              </p>
            </div>
            <Link
              href="/dashboard/listings/new"
              className="shrink-0 rounded-md bg-white px-5 py-3 font-semibold text-orange-600 hover:bg-orange-50"
            >
              Разместить объявление
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
