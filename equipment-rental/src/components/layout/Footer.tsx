import React from 'react'
import { Link } from 'react-router-dom'
import { Cog, Phone, Mail, MapPin, Clock } from 'lucide-react'

export const Footer: React.FC = () => {
  return (
    <footer className="bg-gray-950 border-t border-gray-800/50 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {/* Brand */}
          <div>
            <Link to="/" className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 bg-gradient-to-br from-amber-400 to-amber-600 rounded-lg flex items-center justify-center">
                <Cog size={18} className="text-gray-900" />
              </div>
              <span className="font-black text-lg tracking-wider text-white">
                ТЕХ<span className="text-amber-400">ПРОКАТ</span>
              </span>
            </Link>
            <p className="text-sm text-gray-500 leading-relaxed mb-4">
              Профессиональная аренда строительной и специальной техники. Более 500 единиц техники в наличии. Работаем по всей России.
            </p>
            <div className="flex gap-3">
              {['ВК', 'ТГ', 'WA'].map((s) => (
                <a
                  key={s}
                  href="#"
                  className="w-8 h-8 bg-gray-800 rounded-md flex items-center justify-center text-xs text-gray-400 hover:bg-amber-500/20 hover:text-amber-400 transition-all"
                >
                  {s}
                </a>
              ))}
            </div>
          </div>

          {/* Navigation */}
          <div>
            <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider mb-4">Навигация</h3>
            <ul className="space-y-2.5">
              {[
                { to: '/catalog', label: 'Каталог техники' },
                { to: '/wizard', label: 'Мастер подбора' },
                { to: '/about', label: 'О компании' },
                { to: '/contact', label: 'Контакты' },
                { to: '/booking', label: 'Оформить заявку' },
              ].map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="text-sm text-gray-500 hover:text-amber-400 transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Categories */}
          <div>
            <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider mb-4">Категории</h3>
            <ul className="space-y-2.5">
              {[
                'Экскаваторы',
                'Краны',
                'Бульдозеры',
                'Погрузчики',
                'Дорожная техника',
                'Буровая техника',
              ].map((cat) => (
                <li key={cat}>
                  <Link
                    to={`/catalog?category=${encodeURIComponent(cat)}`}
                    className="text-sm text-gray-500 hover:text-amber-400 transition-colors"
                  >
                    {cat}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Contacts */}
          <div>
            <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider mb-4">Контакты</h3>
            <ul className="space-y-3">
              <li className="flex items-start gap-3">
                <Phone size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm text-gray-300">+7 (495) 123-45-67</div>
                  <div className="text-xs text-gray-600">Основная линия</div>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Phone size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm text-gray-300">8-800-555-35-35</div>
                  <div className="text-xs text-gray-600">Бесплатно по РФ</div>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Mail size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <span className="text-sm text-gray-300">info@tehprokat.ru</span>
              </li>
              <li className="flex items-start gap-3">
                <MapPin size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <span className="text-sm text-gray-300">Москва, ул. Промышленная, 12</span>
              </li>
              <li className="flex items-start gap-3">
                <Clock size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <span className="text-sm text-gray-300">Пн–Пт: 8:00–19:00</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-gray-800/50 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-600">
            © 2024 ТЕХПРОКАТ. Все права защищены. ООО «ТехПрокат», ИНН 7712345678
          </p>
          <div className="flex gap-6">
            <a href="#" className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Политика конфиденциальности
            </a>
            <a href="#" className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Условия аренды
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
