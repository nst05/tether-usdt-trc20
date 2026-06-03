import React, { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Zap, Shield, Phone, Star, ArrowRight, Wrench, Truck } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { EquipmentCard } from '../components/EquipmentCard'
import { equipmentData } from '../data/equipment'

const stats = [
  { value: '500+', label: 'единиц техники' },
  { value: '1 200+', label: 'завершённых проектов' },
  { value: '15', label: 'лет опыта' },
  { value: '24/7', label: 'поддержка клиентов' },
]

const steps = [
  {
    num: '01',
    title: 'Выберите технику',
    desc: 'Воспользуйтесь каталогом или запустите Мастер подбора — он подберёт оптимальный пакет под ваш проект автоматически.',
  },
  {
    num: '02',
    title: 'Оформите заявку',
    desc: 'Укажите даты аренды, адрес объекта и контактную информацию. Подтверждение придёт в течение 30 минут.',
  },
  {
    num: '03',
    title: 'Получите технику',
    desc: 'Доставим технику на объект в согласованные сроки. Профессиональный оператор при необходимости — в комплекте.',
  },
]

const categoryList = [
  { name: 'Экскаваторы', count: 5, icon: '⛏', color: 'from-amber-500/20 to-amber-600/10', border: 'border-amber-500/20' },
  { name: 'Краны', count: 3, icon: '🏗', color: 'from-blue-500/20 to-blue-600/10', border: 'border-blue-500/20' },
  { name: 'Бульдозеры', count: 2, icon: '🚜', color: 'from-orange-500/20 to-orange-600/10', border: 'border-orange-500/20' },
  { name: 'Погрузчики', count: 4, icon: '🚛', color: 'from-emerald-500/20 to-emerald-600/10', border: 'border-emerald-500/20' },
  { name: 'Дорожная техника', count: 5, icon: '🛣', color: 'from-purple-500/20 to-purple-600/10', border: 'border-purple-500/20' },
  { name: 'Буровая техника', count: 3, icon: '🔩', color: 'from-red-500/20 to-red-600/10', border: 'border-red-500/20' },
]

const testimonials = [
  {
    name: 'Игорь Смирнов',
    company: 'ГК «ПромСтрой»',
    text: 'Арендовали экскаватор CAT 320 на месяц. Техника пришла в идеальном состоянии, оператор — профессионал высокого класса. Все документы оформлены быстро и без лишних вопросов.',
    rating: 5,
  },
  {
    name: 'Анна Белякова',
    company: 'ООО «ДорСервис»',
    text: 'Пользуемся Мастером подбора регулярно — это реально экономит время. Система точно подобрала пакет для дорожного проекта, сэкономили 18% по сравнению с раздельной арендой.',
    rating: 5,
  },
  {
    name: 'Павел Орлов',
    company: 'АО «СтройИнвест»',
    text: 'Арендовали башенный кран на 2 месяца для ЖК. Монтаж, обслуживание, демонтаж — всё включено в стоимость. Никаких скрытых платежей. Рекомендую.',
    rating: 4,
  },
]

export const Home: React.FC = () => {
  const statsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    document.title = 'ТЕХПРОКАТ — Аренда спецтехники'
  }, [])

  const featured = equipmentData.slice(0, 6)

  return (
    <div className="min-h-screen">
      {/* HERO */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
        {/* Background */}
        <div className="absolute inset-0 bg-gray-950">
          <div className="absolute inset-0 bg-grid opacity-30" />
          <div className="absolute inset-0 bg-gradient-radial from-amber-500/5 via-transparent to-transparent" />
        </div>

        {/* Floating shape */}
        <div className="absolute right-10 top-1/2 -translate-y-1/2 hidden lg:block animate-float opacity-20">
          <svg width="400" height="400" viewBox="0 0 400 400" fill="none">
            <rect x="50" y="150" width="300" height="100" rx="8" fill="#F59E0B" opacity="0.6" />
            <rect x="80" y="120" width="60" height="30" rx="4" fill="#F59E0B" opacity="0.8" />
            <rect x="150" y="80" width="180" height="40" rx="6" fill="#F59E0B" opacity="0.5" />
            <circle cx="80" cy="260" r="20" fill="#374151" stroke="#F59E0B" strokeWidth="4" />
            <circle cx="320" cy="260" r="20" fill="#374151" stroke="#F59E0B" strokeWidth="4" />
            <rect x="100" y="250" width="200" height="10" rx="5" fill="#F59E0B" opacity="0.4" />
            <rect x="300" y="130" width="20" height="120" rx="4" fill="#F59E0B" opacity="0.7" />
          </svg>
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-32">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-full px-4 py-1.5 mb-6">
              <Zap size={14} className="text-amber-400" />
              <span className="text-sm text-amber-300 font-medium">Более 500 единиц техники в наличии</span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black mb-6 leading-none tracking-tight">
              <span className="gradient-text">АРЕНДА</span>
              <br />
              <span className="text-white">СПЕЦТЕХНИКИ</span>
              <br />
              <span className="text-gray-600 text-3xl sm:text-4xl font-bold">профессионально</span>
            </h1>

            <p className="text-lg text-gray-400 mb-8 leading-relaxed max-w-xl">
              Экскаваторы, краны, бульдозеры — от мини-погрузчика до тяжёлого кранового комплекса. Доставка на объект, сервис 24/7, опытные операторы.
            </p>

            <div className="flex flex-wrap gap-4">
              <Link to="/catalog">
                <Button size="lg" variant="primary" className="gap-2">
                  Смотреть каталог
                  <ChevronRight size={18} />
                </Button>
              </Link>
              <Link to="/wizard">
                <Button size="lg" variant="secondary" className="gap-2">
                  <Zap size={18} />
                  Мастер подбора
                </Button>
              </Link>
            </div>

            <div className="flex flex-wrap gap-6 mt-10">
              {[
                { icon: Shield, text: 'Полное страхование' },
                { icon: Truck, text: 'Доставка на объект' },
                { icon: Wrench, text: 'Тех. поддержка 24/7' },
              ].map(({ icon: Icon, text }) => (
                <div key={text} className="flex items-center gap-2 text-sm text-gray-500">
                  <Icon size={14} className="text-amber-500" />
                  {text}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-40">
          <span className="text-xs text-gray-500">прокрутите вниз</span>
          <div className="w-5 h-8 border border-gray-600 rounded-full flex items-start justify-center pt-1.5">
            <div className="w-1 h-2 bg-amber-500 rounded-full animate-bounce" />
          </div>
        </div>
      </section>

      {/* STATS */}
      <section ref={statsRef} className="bg-gray-900/50 border-y border-gray-800/50 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-4xl font-black text-amber-400 mb-1">{stat.value}</div>
                <div className="text-sm text-gray-500">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-black text-white mb-3">
              Как это <span className="gradient-text">работает</span>
            </h2>
            <p className="text-gray-500 max-w-xl mx-auto">Три простых шага — и техника уже на вашем объекте</p>
          </div>

          <div className="relative grid md:grid-cols-3 gap-8">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-12 left-1/6 right-1/6 h-px bg-gradient-to-r from-transparent via-amber-500/30 to-transparent" />

            {steps.map((step, i) => (
              <div key={i} className="relative text-center group">
                <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gray-900 border-2 border-amber-500/30 group-hover:border-amber-500 transition-all mb-6 relative">
                  <span className="text-3xl font-black gradient-text">{step.num}</span>
                </div>
                <h3 className="text-xl font-bold text-white mb-3">{step.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CATEGORIES */}
      <section className="py-20 bg-gray-900/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-black text-white mb-3">
              Категории <span className="gradient-text">техники</span>
            </h2>
            <p className="text-gray-500">Широкий выбор для любых строительных задач</p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {categoryList.map((cat) => (
              <Link
                key={cat.name}
                to={`/catalog?category=${encodeURIComponent(cat.name)}`}
                className={`group bg-gradient-to-br ${cat.color} border ${cat.border} rounded-xl p-6 hover:scale-[1.02] transition-all duration-200 cursor-pointer`}
              >
                <div className="text-4xl mb-3">{cat.icon}</div>
                <h3 className="text-base font-bold text-white group-hover:text-amber-400 transition-colors">{cat.name}</h3>
                <p className="text-sm text-gray-500 mt-1">{cat.count} единиц</p>
                <div className="flex items-center gap-1 mt-3 text-xs text-gray-600 group-hover:text-amber-500 transition-colors">
                  Перейти в каталог <ArrowRight size={12} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* FEATURED EQUIPMENT */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between mb-12">
            <div>
              <h2 className="text-3xl sm:text-4xl font-black text-white mb-2">
                Популярная <span className="gradient-text">техника</span>
              </h2>
              <p className="text-gray-500">Топ-позиции в аренде прямо сейчас</p>
            </div>
            <Link to="/catalog" className="hidden md:block">
              <Button variant="secondary" className="gap-2">
                Весь каталог <ArrowRight size={16} />
              </Button>
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {featured.map((eq) => (
              <EquipmentCard key={eq.id} equipment={eq} />
            ))}
          </div>

          <div className="text-center mt-8 md:hidden">
            <Link to="/catalog">
              <Button variant="secondary" className="gap-2">
                Весь каталог <ArrowRight size={16} />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* WIZARD CTA */}
      <section className="py-20 bg-gradient-to-r from-amber-600/10 via-amber-500/5 to-transparent border-y border-amber-500/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row items-center gap-12">
            <div className="flex-1">
              <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-full px-4 py-1.5 mb-6">
                <Zap size={14} className="text-amber-400" />
                <span className="text-sm text-amber-300 font-medium">ИИ-подбор за 30 секунд</span>
              </div>
              <h2 className="text-3xl sm:text-4xl font-black text-white mb-4">
                Мастер подбора <span className="gradient-text">проектной</span> конфигурации
              </h2>
              <p className="text-gray-400 mb-6 leading-relaxed">
                Опишите ваш проект — тип работ, площадь, сроки, рельеф — и система автоматически подберёт оптимальный пакет техники с расчётом стоимости и обоснованием каждого элемента.
              </p>
              <ul className="space-y-2 mb-8">
                {[
                  'Анализ параметров проекта за несколько секунд',
                  'Оптимальный набор техники под конкретные условия',
                  'Экономия до 25% против раздельной аренды',
                  'Мгновенное бронирование всего пакета одним кликом',
                ].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-sm text-gray-400">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
              <Link to="/wizard">
                <Button size="lg" className="gap-2">
                  <Zap size={18} />
                  Запустить мастер подбора
                </Button>
              </Link>
            </div>

            <div className="flex-shrink-0 relative">
              <div className="w-64 h-64 relative">
                {/* Scanner animation */}
                <div className="absolute inset-0 rounded-full border-2 border-amber-500/20 scanner-ping" />
                <div className="absolute inset-4 rounded-full border-2 border-amber-500/30 scanner-ping-2" />
                <div className="absolute inset-8 rounded-full border-2 border-amber-500/40 scanner-ping-3" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-24 h-24 bg-amber-500/10 border border-amber-500/30 rounded-full flex items-center justify-center">
                    <Zap size={40} className="text-amber-400" />
                  </div>
                </div>
                <div className="absolute inset-0 rounded-full border border-amber-500/10 scanner-rotate" style={{ borderTopColor: 'rgba(245, 158, 11, 0.6)' }} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* TESTIMONIALS */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-black text-white mb-3">
              Отзывы <span className="gradient-text">клиентов</span>
            </h2>
            <p className="text-gray-500">Что говорят те, кто уже работал с нами</p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {testimonials.map((t, i) => (
              <div key={i} className="bg-gray-900 border border-gray-700/50 rounded-xl p-6 hover:border-amber-500/30 transition-all">
                <div className="flex items-center gap-1 mb-4">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <Star
                      key={j}
                      size={14}
                      className={j < t.rating ? 'text-amber-400 fill-amber-400' : 'text-gray-700'}
                    />
                  ))}
                </div>
                <p className="text-gray-400 text-sm leading-relaxed mb-5">«{t.text}»</p>
                <div>
                  <div className="text-sm font-semibold text-gray-200">{t.name}</div>
                  <div className="text-xs text-gray-600">{t.company}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 bg-gray-900/50 border-t border-gray-800/50">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <Phone size={40} className="text-amber-500 mx-auto mb-4" />
          <h2 className="text-2xl sm:text-3xl font-black text-white mb-3">
            Нужна консультация?
          </h2>
          <p className="text-gray-500 mb-6">Наши специалисты помогут подобрать технику и ответят на все вопросы</p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/contact">
              <Button size="lg" className="gap-2">
                <Phone size={18} />
                Связаться с нами
              </Button>
            </Link>
            <a href="tel:+74951234567">
              <Button size="lg" variant="secondary">
                +7 (495) 123-45-67
              </Button>
            </a>
          </div>
        </div>
      </section>
    </div>
  )
}
