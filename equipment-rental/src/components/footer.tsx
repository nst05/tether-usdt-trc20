import Link from "next/link";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-black/5 bg-white">
      <div className="mx-auto max-w-6xl px-4 py-10 text-sm text-gray-500 sm:px-6">
        <div className="grid gap-8 sm:grid-cols-3">
          <div>
            <p className="mb-2 font-bold text-gray-900">СпецАренда</p>
            <p>
              Платформа для аренды спецтехники: экскаваторы, краны, погрузчики
              и другая техника от проверенных владельцев.
            </p>
          </div>
          <div>
            <p className="mb-2 font-semibold text-gray-900">Платформа</p>
            <ul className="space-y-1">
              <li>
                <Link href="/listings" className="hover:text-orange-500">
                  Каталог техники
                </Link>
              </li>
              <li>
                <Link href="/how-it-works" className="hover:text-orange-500">
                  Как это работает
                </Link>
              </li>
              <li>
                <Link href="/dashboard/listings/new" className="hover:text-orange-500">
                  Разместить объявление
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <p className="mb-2 font-semibold text-gray-900">Аккаунт</p>
            <ul className="space-y-1">
              <li>
                <Link href="/auth/sign-in" className="hover:text-orange-500">
                  Войти
                </Link>
              </li>
              <li>
                <Link href="/auth/sign-up" className="hover:text-orange-500">
                  Регистрация
                </Link>
              </li>
            </ul>
          </div>
        </div>
        <p className="mt-8 border-t border-black/5 pt-6 text-xs text-gray-400">
          © {new Date().getFullYear()} СпецАренда. Все права защищены.
        </p>
      </div>
    </footer>
  );
}
