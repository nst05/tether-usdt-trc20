"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { X } from "lucide-react";

type Category = { id: string; name: string; slug: string };

export type ListingFormValues = {
  title: string;
  description: string;
  categoryId: string;
  city: string;
  address: string;
  pricePerDay: string;
  pricePerHour: string;
  depositAmount: string;
  year: string;
  powerHp: string;
  capacityTons: string;
  withOperator: boolean;
  images: string[];
};

const emptyValues: ListingFormValues = {
  title: "",
  description: "",
  categoryId: "",
  city: "",
  address: "",
  pricePerDay: "",
  pricePerHour: "",
  depositAmount: "0",
  year: "",
  powerHp: "",
  capacityTons: "",
  withOperator: false,
  images: [],
};

export function ListingForm({
  listingId,
  initialValues,
}: {
  listingId?: string;
  initialValues?: Partial<ListingFormValues>;
}) {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [values, setValues] = useState<ListingFormValues>({
    ...emptyValues,
    ...initialValues,
  });
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/categories")
      .then((r) => r.json())
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  function set<K extends keyof ListingFormValues>(
    key: K,
    value: ListingFormValues[K]
  ) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);

    try {
      const uploaded: string[] = [];
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? "Ошибка загрузки");
        uploaded.push(data.url);
      }
      set("images", [...values.images, ...uploaded]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  function removeImage(url: string) {
    set(
      "images",
      values.images.filter((i) => i !== url)
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);

    const payload = {
      title: values.title,
      description: values.description,
      categoryId: values.categoryId,
      city: values.city,
      address: values.address,
      pricePerDay: values.pricePerDay,
      pricePerHour: values.pricePerHour || undefined,
      depositAmount: values.depositAmount || 0,
      year: values.year || undefined,
      powerHp: values.powerHp || undefined,
      capacityTons: values.capacityTons || undefined,
      withOperator: values.withOperator,
      images: values.images,
    };

    const res = await fetch(
      listingId ? `/api/listings/${listingId}` : "/api/listings",
      {
        method: listingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );

    const data = await res.json().catch(() => ({}));
    setSaving(false);

    if (!res.ok) {
      setError(data.error ?? "Не удалось сохранить объявление");
      return;
    }

    router.push("/dashboard/listings");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6 max-w-2xl">
      <div>
        <label className="mb-1 block text-sm font-medium">Название</label>
        <input
          required
          value={values.title}
          onChange={(e) => set("title", e.target.value)}
          placeholder="Экскаватор-погрузчик JCB 3CX"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Категория</label>
        <select
          required
          value={values.categoryId}
          onChange={(e) => set("categoryId", e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
        >
          <option value="">Выберите категорию</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Описание</label>
        <textarea
          rows={4}
          value={values.description}
          onChange={(e) => set("description", e.target.value)}
          placeholder="Состояние, комплектация, условия аренды..."
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Город</label>
          <input
            required
            value={values.city}
            onChange={(e) => set("city", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Адрес (необязательно)</label>
          <input
            value={values.address}
            onChange={(e) => set("address", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Цена/сутки, ₽</label>
          <input
            required
            type="number"
            min={0}
            value={values.pricePerDay}
            onChange={(e) => set("pricePerDay", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Цена/час, ₽</label>
          <input
            type="number"
            min={0}
            value={values.pricePerHour}
            onChange={(e) => set("pricePerHour", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Залог, ₽</label>
          <input
            type="number"
            min={0}
            value={values.depositAmount}
            onChange={(e) => set("depositAmount", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium">Год выпуска</label>
          <input
            type="number"
            value={values.year}
            onChange={(e) => set("year", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Мощность, л.с.</label>
          <input
            type="number"
            value={values.powerHp}
            onChange={(e) => set("powerHp", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Грузоподъемность, т</label>
          <input
            type="number"
            step="0.1"
            value={values.capacityTons}
            onChange={(e) => set("capacityTons", e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={values.withOperator}
          onChange={(e) => set("withOperator", e.target.checked)}
        />
        Сдаётся с оператором
      </label>

      <div>
        <label className="mb-1 block text-sm font-medium">Фотографии</label>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          onChange={onFileChange}
          disabled={uploading}
          className="block w-full text-sm"
        />
        {uploading && (
          <p className="mt-1 text-xs text-gray-500">Загружаем фото...</p>
        )}
        {values.images.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-3">
            {values.images.map((url) => (
              <div key={url} className="relative h-20 w-28 overflow-hidden rounded-md border">
                <Image src={url} alt="" fill className="object-cover" />
                <button
                  type="button"
                  onClick={() => removeImage(url)}
                  className="absolute right-1 top-1 rounded-full bg-black/60 p-0.5 text-white"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={saving || uploading}
        className="rounded-md bg-orange-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-orange-600 disabled:opacity-60"
      >
        {saving ? "Сохраняем..." : listingId ? "Сохранить изменения" : "Опубликовать объявление"}
      </button>
    </form>
  );
}
