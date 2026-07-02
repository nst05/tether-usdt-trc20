import { z } from "zod";

export const registerSchema = z.object({
  name: z.string().min(2, "Введите имя").max(100),
  email: z.string().email("Некорректный email"),
  password: z.string().min(8, "Минимум 8 символов"),
  phone: z.string().min(5).max(30).optional().or(z.literal("")),
});

export const listingSchema = z.object({
  title: z.string().min(3, "Слишком короткое название").max(150),
  description: z.string().max(5000).optional().default(""),
  categoryId: z.string().uuid("Выберите категорию"),
  city: z.string().min(2, "Укажите город").max(100),
  address: z.string().max(200).optional().or(z.literal("")),
  pricePerDay: z.coerce.number().positive("Цена должна быть больше нуля"),
  pricePerHour: z.coerce.number().positive().optional().nullable(),
  depositAmount: z.coerce.number().min(0).optional().default(0),
  year: z.coerce.number().int().min(1950).max(2100).optional().nullable(),
  powerHp: z.coerce.number().int().positive().optional().nullable(),
  capacityTons: z.coerce.number().positive().optional().nullable(),
  withOperator: z.boolean().optional().default(false),
  images: z.array(z.string().url()).max(10).optional().default([]),
});

export const bookingSchema = z
  .object({
    listingId: z.string().uuid(),
    startDate: z.coerce.date(),
    endDate: z.coerce.date(),
    message: z.string().max(1000).optional().or(z.literal("")),
  })
  .refine((data) => data.endDate > data.startDate, {
    message: "Дата окончания должна быть позже даты начала",
    path: ["endDate"],
  });
