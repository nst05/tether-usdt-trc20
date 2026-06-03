import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Settings, ShoppingCart, Menu, X, Cog } from 'lucide-react'
import { useCartStore } from '../../store/cartStore'

export const Header: React.FC = () => {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()
  const { getTotalItems } = useCartStore()
  const cartCount = getTotalItems()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    setMobileOpen(false)
  }, [location])

  const navLinks = [
    { to: '/catalog', label: 'Каталог' },
    { to: '/wizard', label: 'Мастер подбора' },
    { to: '/about', label: 'О нас' },
    { to: '/contact', label: 'Контакты' },
  ]

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + '/')

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'bg-gray-950/95 backdrop-blur-md shadow-lg shadow-black/30 border-b border-gray-800/50' : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 bg-gradient-to-br from-amber-400 to-amber-600 rounded-lg flex items-center justify-center group-hover:shadow-[0_0_15px_rgba(245,158,11,0.5)] transition-all">
              <Cog size={18} className="text-gray-900" />
            </div>
            <span className="font-black text-lg tracking-wider text-white">
              ТЕХ<span className="text-amber-400">ПРОКАТ</span>
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive(link.to)
                    ? 'text-amber-400 bg-amber-500/10'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {/* Right side */}
          <div className="flex items-center gap-2">
            {/* Cart */}
            <Link
              to="/booking"
              className="relative flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              <ShoppingCart size={18} />
              {cartCount > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-amber-500 text-gray-900 text-xs font-bold rounded-full flex items-center justify-center">
                  {cartCount}
                </span>
              )}
              <span className="hidden sm:block text-sm">Корзина</span>
            </Link>

            {/* Admin */}
            <Link
              to="/admin"
              className="hidden md:flex items-center gap-1.5 px-3 py-2 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-all text-sm"
            >
              <Settings size={14} />
              Админ
            </Link>

            {/* Mobile menu toggle */}
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-gray-950/98 backdrop-blur-md border-t border-gray-800/50">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`block px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive(link.to)
                    ? 'text-amber-400 bg-amber-500/10'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <Link
              to="/admin"
              className="block px-4 py-2.5 rounded-lg text-sm font-medium text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-all"
            >
              Панель администратора
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
