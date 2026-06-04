import React from 'react'
import { Link } from 'react-router-dom'
import { Cog, Phone, Mail, MapPin, Clock, ArrowRight } from 'lucide-react'

export const Footer: React.FC = () => {
  return (
    <footer className="bg-[#0A0A0A] border-t border-white/6 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10">

          {/* Brand */}
          <div className="lg:col-span-1">
            <Link to="/" className="flex items-center gap-3 mb-5 group">
              <div className="w-9 h-9 bg-amber-500 rounded-lg flex items-center justify-center shadow-[0_2px_12px_rgba(245,158,11,0.3)] transition-all group-hover:shadow-[0_4px_20px_rgba(245,158,11,0.5)]">
                <Cog size={20} className="text-black" />
              </div>
              <div>
                <span className="font-black text-base tracking-[0.12em] text-white uppercase block">
                  Тех<span className="text-amber-400">Прокат</span>
                </span>
                <span className="text-[10px] text-gray-600 tracking-widest uppercase">Аренда спецтехники</span>
              </div>
            </Link>
            <p className="text-sm text-gray-600 leading-relaxed mb-6">
              Профессиональная аренда строительной и специальной техники. Более 500 единиц. Работаем по всей России.
            </p>
            <div className="flex gap-2">
              {[{ label: 'ВК', href: '#' }, { label: 'ТГ', href: '#' }, { label: 'WA', href: '#' }].map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  className="w-8 h-8 bg-[#1A1A1A] border border-white/6 rounded-md flex items-center justify-center text-xs text-gray-500 hover:bg-amber-500/10 hover:text-amber-400 hover:border-amber-500/30 transition-all"
                >
                  {s.label}
                </a>
              ))}
            </div>
          </div>

          {/* Navigation */}
          <div>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-[0.15em] mb-5">Навигация</h3>
            <ul className="space-y-3">
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
                    className="group flex items-center gap-1.5 text-sm text-gray-600 hover:text-amber-400 transition-colors"
                  >
                    <ArrowRight size={11} className="opacity-0 group-hover:opacity-100 -ml-3.5 group-hover:ml-0 transition-all" />
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Categories */}
          <div>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-[0.15em] mb-5">Категории</h3>
            <ul className="space-y-3">
              {['Экскаваторы', 'Краны', 'Бульдозеры', 'Погрузчики', 'Дорожная техника', 'Буровая техника'].map((cat) => (
                <li key={cat}>
                  <Link
                    to={`/catalog?category=${encodeURIComponent(cat)}`}
                    className="group flex items-center gap-1.5 text-sm text-gray-600 hover:text-amber-400 transition-colors"
                  >
                    <ArrowRight size={11} className="opacity-0 group-hover:opacity-100 -ml-3.5 group-hover:ml-0 transition-all" />
                    {cat}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Contacts */}
          <div>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-[0.15em] mb-5">Контакты</h3>
            <ul className="space-y-4">
              <li className="flex items-start gap-3">
                <Phone size={13} className="text-amber-500 mt-1 shrink-0" />
                <div>
                  <a href="tel:+74951234567" className="text-sm text-gray-300 hover:text-amber-400 transition-colors font-medium">
                    +7 (495) 123-45-67
                  </a>
                  <div className="text-xs text-gray-600 mt-0.5">Основная линия</div>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Phone size={13} className="text-amber-500 mt-1 shrink-0" />
                <div>
                  <a href="tel:88005553535" className="text-sm text-gray-300 hover:text-amber-400 transition-colors">
                    8-800-555-35-35
                  </a>
                  <div className="text-xs text-gray-600 mt-0.5">Бесплатно по РФ</div>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Mail size={13} className="text-amber-500 mt-1 shrink-0" />
                <a href="mailto:info@tehprokat.ru" className="text-sm text-gray-300 hover:text-amber-400 transition-colors">
                  info@tehprokat.ru
                </a>
              </li>
              <li className="flex items-start gap-3">
                <MapPin size={13} className="text-amber-500 mt-1 shrink-0" />
                <span className="text-sm text-gray-400">Москва, ул. Промышленная, 12</span>
              </li>
              <li className="flex items-start gap-3">
                <Clock size={13} className="text-amber-500 mt-1 shrink-0" />
                <span className="text-sm text-gray-400">Пн–Пт: 8:00–19:00</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-14 pt-6 border-t border-white/6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-700">
            © 2024 ТЕХПРОКАТ. Все права защищены. ООО «ТехПрокат», ИНН 7712345678
          </p>
          <div className="flex gap-6">
            <a href="#" className="text-xs text-gray-700 hover:text-gray-500 transition-colors">Политика конфиденциальности</a>
            <a href="#" className="text-xs text-gray-700 hover:text-gray-500 transition-colors">Условия аренды</a>
          </div>
        </div>
      </div>
    </footer>
  )
}
