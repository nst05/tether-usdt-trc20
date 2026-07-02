"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession, signOut } from "next-auth/react";
import { Menu, X, Truck, LayoutDashboard, LogOut } from "lucide-react";

export function Navbar() {
  const { status } = useSession();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-black/5 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-orange-500 text-white">
            <Truck size={20} />
          </span>
          <span>
            Спец<span className="text-orange-500">Аренда</span>
          </span>
        </Link>

        <nav className="hidden items-center gap-6 text-sm font-medium text-gray-700 sm:flex">
          <Link href="/listings" className="hover:text-orange-500">
            Каталог техники
          </Link>
          <Link href="/how-it-works" className="hover:text-orange-500">
            Как это работает
          </Link>
          {status === "authenticated" && (
            <Link href="/dashboard/listings/new" className="hover:text-orange-500">
              Разместить технику
            </Link>
          )}
        </nav>

        <div className="hidden items-center gap-3 sm:flex">
          {status === "authenticated" ? (
            <>
              <Link
                href="/dashboard"
                className="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                <LayoutDashboard size={16} />
                Кабинет
              </Link>
              <button
                onClick={() => signOut({ callbackUrl: "/" })}
                className="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-gray-500 hover:bg-gray-100"
              >
                <LogOut size={16} />
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link
                href="/auth/sign-in"
                className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                Войти
              </Link>
              <Link
                href="/auth/sign-up"
                className="rounded-md bg-orange-500 px-4 py-2 text-sm font-semibold text-white hover:bg-orange-600"
              >
                Регистрация
              </Link>
            </>
          )}
        </div>

        <button
          className="sm:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Меню"
        >
          {open ? <X /> : <Menu />}
        </button>
      </div>

      {open && (
        <div className="border-t border-black/5 bg-white px-4 py-3 sm:hidden">
          <div className="flex flex-col gap-3 text-sm font-medium text-gray-700">
            <Link href="/listings" onClick={() => setOpen(false)}>
              Каталог техники
            </Link>
            <Link href="/how-it-works" onClick={() => setOpen(false)}>
              Как это работает
            </Link>
            {status === "authenticated" ? (
              <>
                <Link href="/dashboard" onClick={() => setOpen(false)}>
                  Кабинет
                </Link>
                <Link href="/dashboard/listings/new" onClick={() => setOpen(false)}>
                  Разместить технику
                </Link>
                <button
                  className="text-left text-gray-500"
                  onClick={() => signOut({ callbackUrl: "/" })}
                >
                  Выйти
                </button>
              </>
            ) : (
              <>
                <Link href="/auth/sign-in" onClick={() => setOpen(false)}>
                  Войти
                </Link>
                <Link href="/auth/sign-up" onClick={() => setOpen(false)}>
                  Регистрация
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
