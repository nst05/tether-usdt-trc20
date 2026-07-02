import Link from "next/link";
import {
  LayoutDashboard,
  ListPlus,
  ListChecks,
  CalendarClock,
  Wallet,
  Truck,
} from "lucide-react";

const links = [
  { href: "/dashboard", label: "Обзор", icon: LayoutDashboard },
  { href: "/dashboard/listings", label: "Мои объявления", icon: ListChecks },
  { href: "/dashboard/listings/new", label: "Разместить технику", icon: ListPlus },
  { href: "/dashboard/bookings", label: "Заявки на мою технику", icon: CalendarClock },
  { href: "/dashboard/my-bookings", label: "Мои аренды", icon: Truck },
  { href: "/dashboard/payouts", label: "Выплаты", icon: Wallet },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-6xl gap-8 px-4 py-8 sm:px-6">
      <aside className="hidden w-56 shrink-0 sm:block">
        <nav className="sticky top-20 space-y-1">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-gray-600 hover:bg-orange-50 hover:text-orange-600"
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
