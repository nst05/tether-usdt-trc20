import React, { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Wrench, ClipboardList, Users, BarChart3, Settings, Cog, ChevronLeft, ChevronRight, Home } from 'lucide-react'

const navItems = [
  { to: '/admin', label: 'Дашборд', icon: LayoutDashboard, exact: true },
  { to: '/admin/equipment', label: 'Техника', icon: Wrench },
  { to: '/admin/orders', label: 'Заказы', icon: ClipboardList },
  { to: '/admin/clients', label: 'Клиенты', icon: Users },
  { to: '/admin/analytics', label: 'Аналитика', icon: BarChart3 },
  { to: '/admin/settings', label: 'Настройки', icon: Settings },
]

export const AdminLayout: React.FC = () => {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const isActive = (to: string, exact?: boolean) =>
    exact ? location.pathname === to : location.pathname.startsWith(to)

  return (
    <div className="min-h-screen flex bg-gray-950">
      {/* Sidebar */}
      <aside className={`${collapsed ? 'w-16' : 'w-56'} transition-all duration-300 bg-gray-900 border-r border-gray-800/50 flex flex-col shrink-0`}>
        {/* Logo */}
        <div className={`flex items-center gap-2.5 p-4 border-b border-gray-800/50 ${collapsed ? 'justify-center' : ''}`}>
          <div className="w-8 h-8 bg-gradient-to-br from-blue-400 to-blue-600 rounded-lg flex items-center justify-center shrink-0">
            <Cog size={16} className="text-gray-900" />
          </div>
          {!collapsed && (
            <span className="font-black text-sm tracking-wider text-white">
              ТЕХ<span className="text-blue-400">ПРОКАТ</span>
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon, exact }) => (
            <Link
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                isActive(to, exact)
                  ? 'bg-blue-500/15 text-blue-400 font-medium'
                  : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
              } ${collapsed ? 'justify-center' : ''}`}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          ))}
        </nav>

        {/* Bottom */}
        <div className="p-2 border-t border-gray-800/50 space-y-1">
          <Link
            to="/"
            title={collapsed ? 'На сайт' : undefined}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-800 hover:text-gray-400 transition-all ${collapsed ? 'justify-center' : ''}`}
          >
            <Home size={18} />
            {!collapsed && <span>На сайт</span>}
          </Link>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-800 hover:text-gray-400 transition-all cursor-pointer ${collapsed ? 'justify-center' : ''}`}
          >
            {collapsed ? <ChevronRight size={18} /> : <><ChevronLeft size={18} /><span>Свернуть</span></>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto min-w-0">
        <Outlet />
      </main>
    </div>
  )
}
