import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Settings, ShoppingCart, Menu, X, Cog, Phone, Heart } from 'lucide-react'
import { useCartStore } from '../../store/cartStore'
import { useFavoritesStore } from '../../store/favoritesStore'

export const Header: React.FC = () => {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()
  const { getTotalItems } = useCartStore()
  const cartCount = getTotalItems()
  const { ids: favoriteIds } = useFavoritesStore()
  const favCount = favoriteIds.length

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
        scrolled
          ? 'bg-[#0A0A0A]/96 backdrop-blur-md shadow-xl shadow-black/60 border-b border-white/5'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-18 py-3">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-9 h-9 bg-amber-500 rounded-lg flex items-center justify-center shadow-[0_2px_12px_rgba(245,158,11,0.4)] transition-all group-hover:shadow-[0_4px_20px_rgba(245,158,11,0.6)] group-hover:scale-105">
              <Cog size={20} className="text-black" />
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-black text-base tracking-[0.12em] text-white uppercase">
                Тех<span className="text-amber-400">Прокат</span>
              </span>
              <span className="text-[10px] text-gray-600 tracking-widest uppercase font-medium">
                Аренда спецтехники
              </span>
            </div>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
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
            {/* Phone */}
            <a
              href="tel:+74951234567"
              className="hidden lg:flex items-center gap-2 px-3 py-2 rounded-md text-gray-400 hover:text-white hover:bg-white/5 transition-all text-sm"
            >
              <Phone size={14} className="text-amber-400" />
              +7 (495) 123-45-67
            </a>

            {/* Favorites */}
            <Link
              to="/favorites"
              className="relative flex items-center gap-2 px-3 py-2 rounded-md text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              <Heart size={18} className={isActive('/favorites') ? 'text-amber-400' : ''} />
              {favCount > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-amber-500 text-black text-xs font-bold rounded-full flex items-center justify-center">
                  {favCount}
                </span>
              )}
              <span className="hidden sm:block text-sm">Избранное</span>
            </Link>

            {/* Cart */}
            <Link
              to="/booking"
              className="relative flex items-center gap-2 px-3 py-2 rounded-md text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              <ShoppingCart size={18} />
              {cartCount > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-amber-500 text-black text-xs font-bold rounded-full flex items-center justify-center">
                  {cartCount}
                </span>
              )}
              <span className="hidden sm:block text-sm">Корзина</span>
            </Link>

            <Link
              to="/admin"
              className="hidden md:flex items-center gap-1.5 px-3 py-2 rounded-md text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-all text-sm"
            >
              <Settings size={14} />
              Админ
            </Link>

            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-md text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-[#0A0A0A]/98 backdrop-blur-md border-t border-white/5">
          <div className="px-4 py-4 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`block px-4 py-3 rounded-md text-sm font-medium transition-all ${
                  isActive(link.to)
                    ? 'text-amber-400 bg-amber-500/10'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.label}
              </Link>
            ))}
            <Link
              to="/favorites"
              className="flex items-center gap-2 px-4 py-3 rounded-md text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 transition-all"
            >
              <Heart size={14} className="text-amber-400" />
              Избранное
              {favCount > 0 && (
                <span className="ml-auto w-5 h-5 bg-amber-500 text-black text-xs font-bold rounded-full flex items-center justify-center">
                  {favCount}
                </span>
              )}
            </Link>
            <a
              href="tel:+74951234567"
              className="flex items-center gap-2 px-4 py-3 rounded-md text-sm font-medium text-amber-400"
            >
              <Phone size={14} />
              +7 (495) 123-45-67
            </a>
            <Link
              to="/admin"
              className="block px-4 py-3 rounded-md text-sm font-medium text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-all"
            >
              Панель администратора
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
