import "dotenv/config";
import bcrypt from "bcryptjs";
import { eq } from "drizzle-orm";
import { mkdir, writeFile } from "fs/promises";
import path from "path";
import { db } from "./index";
import { categories, listings, listingImages, users } from "./schema";

function slugify(text: string) {
  return text
    .toLowerCase()
    .replace(/[^a-zа-я0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "");
}

async function makePlaceholderImage(title: string): Promise<string> {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">
  <rect width="800" height="600" fill="#f97316"/>
  <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"
    font-family="sans-serif" font-size="36" fill="#ffffff">${title}</text>
</svg>`;
  const dir = path.join(process.cwd(), "public", "seed");
  await mkdir(dir, { recursive: true });
  const filename = `${slugify(title)}.svg`;
  await writeFile(path.join(dir, filename), svg);
  return `/seed/${filename}`;
}

const CATEGORIES = [
  { name: "Экскаваторы", slug: "excavators" },
  { name: "Экскаваторы-погрузчики", slug: "backhoe-loaders" },
  { name: "Бульдозеры", slug: "bulldozers" },
  { name: "Автокраны", slug: "cranes" },
  { name: "Фронтальные погрузчики", slug: "loaders" },
  { name: "Самосвалы", slug: "dump-trucks" },
  { name: "Бетононасосы", slug: "concrete-pumps" },
  { name: "Автовышки", slug: "aerial-platforms" },
  { name: "Генераторы", slug: "generators" },
  { name: "Компрессоры", slug: "compressors" },
];

const DEMO_LISTINGS = [
  {
    title: "Экскаватор-погрузчик JCB 3CX",
    categorySlug: "backhoe-loaders",
    city: "Москва",
    pricePerDay: "18000",
    pricePerHour: "2500",
    year: 2020,
    powerHp: 109,
    capacityTons: "8",
    withOperator: true,
    description:
      "Экскаватор-погрузчик JCB 3CX в отличном состоянии. Подходит для земляных и погрузочных работ. Возможна аренда с оператором.",
  },
  {
    title: "Гусеничный экскаватор Komatsu PC200",
    categorySlug: "excavators",
    city: "Санкт-Петербург",
    pricePerDay: "25000",
    pricePerHour: null,
    year: 2019,
    powerHp: 148,
    capacityTons: "20",
    withOperator: false,
    description:
      "Мощный гусеничный экскаватор для крупных объектов. Полное техническое обслуживание, готов к работе.",
  },
  {
    title: "Автокран Ивановец КС-45717",
    categorySlug: "cranes",
    city: "Москва",
    pricePerDay: "22000",
    pricePerHour: "3000",
    year: 2018,
    powerHp: 240,
    capacityTons: "25",
    withOperator: true,
    description:
      "Автокран грузоподъёмностью 25 тонн, вылет стрелы до 21 метра. Опытный крановщик в комплекте.",
  },
  {
    title: "Фронтальный погрузчик XCMG LW300",
    categorySlug: "loaders",
    city: "Екатеринбург",
    pricePerDay: "15000",
    pricePerHour: "2000",
    year: 2021,
    powerHp: 162,
    capacityTons: "5",
    withOperator: false,
    description:
      "Фронтальный погрузчик для складских и строительных работ. Малый расход топлива, удобное управление.",
  },
  {
    title: "Бульдозер Shantui SD16",
    categorySlug: "bulldozers",
    city: "Новосибирск",
    pricePerDay: "27000",
    pricePerHour: null,
    year: 2017,
    powerHp: 160,
    capacityTons: null,
    withOperator: true,
    description:
      "Бульдозер для планировки и перемещения грунта на крупных площадках. Аренда только с оператором.",
  },
  {
    title: "Дизельный генератор Cummins 100 кВт",
    categorySlug: "generators",
    city: "Москва",
    pricePerDay: "6000",
    pricePerHour: null,
    year: 2022,
    powerHp: null,
    capacityTons: null,
    withOperator: false,
    description:
      "Автономный дизельный генератор 100 кВт для строительных площадок и мероприятий. Доставка по городу.",
  },
];

async function main() {
  console.log("Seeding categories...");
  const insertedCategories = await db
    .insert(categories)
    .values(CATEGORIES)
    .onConflictDoNothing({ target: categories.slug })
    .returning();

  const categoryMap = new Map<string, string>();
  const allCategories =
    insertedCategories.length === CATEGORIES.length
      ? insertedCategories
      : await db.select().from(categories);
  for (const c of allCategories) categoryMap.set(c.slug, c.id);

  console.log("Seeding demo owner...");
  const demoEmail = "demo-owner@example.com";
  const passwordHash = await bcrypt.hash("password123", 12);

  await db
    .insert(users)
    .values({
      name: "Демо Владелец",
      email: demoEmail,
      passwordHash,
      phone: "+7 900 123-45-67",
      city: "Москва",
    })
    .onConflictDoNothing({ target: users.email });

  const [owner] = await db
    .select()
    .from(users)
    .where(eq(users.email, demoEmail))
    .limit(1);

  const ownerId = owner?.id;

  console.log("Seeding demo listings...");
  const existingListings = ownerId
    ? await db.select({ title: listings.title }).from(listings).where(eq(listings.ownerId, ownerId))
    : [];
  const existingTitles = new Set(existingListings.map((l) => l.title));

  for (const item of DEMO_LISTINGS) {
    const categoryId = categoryMap.get(item.categorySlug);
    if (!categoryId || !ownerId) continue;
    if (existingTitles.has(item.title)) continue;

    const [listing] = await db
      .insert(listings)
      .values({
        ownerId,
        categoryId,
        title: item.title,
        description: item.description,
        city: item.city,
        pricePerDay: item.pricePerDay,
        pricePerHour: item.pricePerHour,
        depositAmount: "0",
        year: item.year,
        powerHp: item.powerHp,
        capacityTons: item.capacityTons,
        withOperator: item.withOperator,
      })
      .returning();

    if (listing) {
      const imageUrl = await makePlaceholderImage(item.title);
      await db.insert(listingImages).values({
        listingId: listing.id,
        url: imageUrl,
        position: 0,
      });
    }
  }

  console.log("Done. Demo owner login: demo-owner@example.com / password123");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
